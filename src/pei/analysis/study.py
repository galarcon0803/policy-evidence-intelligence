"""Run the pre-registered flagship study and save every result for the brief and dashboard.

Run: python -m pei.analysis.study
Specification: analysis/pre_analysis_plan.md
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy.stats import chi2 as chi2_dist
from scipy.stats import spearmanr

from pei.analysis import estimators as est
from pei.config import ROOT, SNAPSHOT_DIR

RESULTS_DIR = ROOT / "analysis" / "results"
PRIMARY_THRESHOLD = 0.10
FALLBACK_THRESHOLD = 0.075
MIN_TREATED = 8
SWEEP = (0.05, 0.075, 0.10, 0.15)
NAMED_STATES = ("VA", "TX")
ATLAS_REFERENCE_YEAR = 2015


def load_tables(source: Path = SNAPSHOT_DIR) -> dict[str, pd.DataFrame]:
    con = duckdb.connect()
    return {
        name: con.execute(f"SELECT * FROM '{(source / name).as_posix()}.parquet'").df()
        for name in ("state_year_panel", "atlas_state", "epoch_us_sites")
    }


def prepare(panel: pd.DataFrame) -> pd.DataFrame:
    frame = panel.sort_values(["state", "year"]).copy()
    frame = frame[frame["year"].between(2001, 2025)]
    frame["ln_price"] = np.log(frame["res_price"])
    frame["ln_bill"] = np.log(frame["res_revenue"] * 1e6 / frame["res_customers"])
    frame["ln_ci"] = np.log(frame["ci_sales"])
    frame["ln_com"] = np.log(frame["com_sales"])
    grouped = frame.groupby("state")
    frame["ln_ci_lag1"] = grouped["ln_ci"].shift(1)
    frame["ln_com_lag1"] = grouped["ln_com"].shift(1)
    frame["ln_ci_lead3"] = grouped["ln_ci"].shift(-3)
    return frame


def fuel_mix_controls(frame: pd.DataFrame) -> tuple[pd.DataFrame, tuple[str, ...]]:
    """Baseline 2001 to 2005 gas and coal shares, interacted with year effects."""
    base = (
        frame[frame["year"].between(2001, 2005)]
        .groupby("state")[["gas_share", "coal_share"]]
        .mean()
    )
    merged = frame.merge(base.add_prefix("base_"), left_on="state", right_index=True, how="left")
    names = []
    for year in sorted(merged["year"].unique())[1:]:
        for fuel in ("gas", "coal"):
            name = f"mix_{fuel}_{year}"
            merged[name] = merged[f"base_{fuel}_share"] * (merged["year"] == year)
            names.append(name)
    return merged, tuple(names)


def customer_weights(frame: pd.DataFrame) -> pd.DataFrame:
    """Each state's earliest reported customer count, so weighting does not shrink the sample."""
    fixed = frame.dropna(subset=["res_customers"]).groupby("state")["res_customers"].first()
    return frame.assign(customer_weight=frame["state"].map(fixed))


def long_difference(frame: pd.DataFrame) -> dict:
    """EXPLORATORY, not pre-registered. Each state's 2015 to 2025 change, so every state counts.

    The same load growth is also set against price change from 2005 to 2015, before that growth
    happened. A relationship there would point to pre-existing differences between states.
    """
    price = frame.pivot(index="state", columns="year", values="ln_price")
    ci = frame.pivot(index="state", columns="year", values="ln_ci")
    com = frame.pivot(index="state", columns="year", values="ln_com")
    data = pd.DataFrame(
        {
            "price_change": price[2025] - price[2015],
            "price_change_before": price[2015] - price[2005],
            "ci_growth": ci[2025] - ci[2015],
            "com_growth": com[2025] - com[2015],
        }
    ).join(frame.drop_duplicates("state").set_index("state")["division"])

    def fit(formula: str, term: str) -> dict:
        model = smf.ols(formula, data).fit(cov_type="HC3")
        low, high = model.conf_int().loc[term]
        return {
            "coef": float(model.params[term]),
            "se": float(model.bse[term]),
            "ci_low": float(low),
            "ci_high": float(high),
            "n": int(model.nobs),
        }

    states = data.drop(columns="division").reset_index(names="state").round(4)
    return {
        "ci": fit("price_change ~ ci_growth", "ci_growth"),
        "ci_division": fit("price_change ~ ci_growth + C(division)", "ci_growth"),
        "commercial": fit("price_change ~ com_growth", "com_growth"),
        "commercial_division": fit("price_change ~ com_growth + C(division)", "com_growth"),
        "ci_placebo_before": fit("price_change_before ~ ci_growth", "ci_growth"),
        "commercial_placebo_before": fit("price_change_before ~ com_growth", "com_growth"),
        "states": states.to_dict("records"),
    }


def atlas_intensity(frame: pd.DataFrame, atlas: pd.DataFrame) -> pd.DataFrame:
    sales_2015 = frame.loc[frame["year"] == 2015, ["state", "total_sales"]]
    merged = atlas.merge(sales_2015, on="state")
    merged["intensity"] = np.log1p(merged["building_sqft"] / merged["total_sales"])
    return merged[["state", "atlas_records", "building_sqft", "intensity"]]


def atlas_event_study(frame: pd.DataFrame, intensity: pd.DataFrame) -> dict:
    """Intensity x year with reference 2015, then the mean of the 2019 to 2025 coefficients."""
    data = frame.merge(intensity[["state", "intensity"]], on="state")[
        ["ln_price", "intensity", "state", "year"]
    ].dropna()
    years = [year for year in sorted(data["year"].unique()) if year != ATLAS_REFERENCE_YEAR]
    terms = {int(year): f"ix_{year}" for year in years}
    for year, name in terms.items():
        data[name] = data["intensity"] * (data["year"] == year)
    formula = "ln_price ~ C(state) + C(year) + " + " + ".join(terms.values())
    fit = smf.ols(formula, data).fit(
        cov_type="cluster", cov_kwds={"groups": data["state"].astype("category").cat.codes}
    )
    weights = pd.Series(0.0, index=fit.params.index)
    post = [terms[year] for year in range(2019, 2026)]
    weights[post] = 1 / len(post)
    test = fit.t_test(weights.to_numpy())
    low, high = test.conf_int()[0]
    return {
        "coef": float(np.squeeze(test.effect)),
        "se": float(np.squeeze(test.sd)),
        "ci_low": float(low),
        "ci_high": float(high),
        "by_year": [
            {"year": year, "coef": float(fit.params[name]), "se": float(fit.bse[name])}
            for year, name in terms.items()
        ],
    }


def proxy_validation(frame: pd.DataFrame, intensity: pd.DataFrame, epoch: pd.DataFrame) -> dict:
    wide = frame[frame["year"].isin([2015, 2025])].pivot(
        index="state", columns="year", values=["ln_ci", "ln_com"]
    )
    growth = pd.DataFrame(
        {
            "ci_growth": wide[("ln_ci", 2025)] - wide[("ln_ci", 2015)],
            "com_growth": wide[("ln_com", 2025)] - wide[("ln_com", 2015)],
        }
    ).merge(intensity.set_index("state"), left_index=True, right_index=True)
    ci = spearmanr(growth["intensity"], growth["ci_growth"])
    com = spearmanr(growth["intensity"], growth["com_growth"])
    sites = epoch.dropna(subset=["state"])
    sites = sites[sites["state"] != ""]
    return {
        "spearman_ci": {"rho": float(ci.statistic), "p": float(ci.pvalue)},
        "spearman_com": {"rho": float(com.statistic), "p": float(com.pvalue)},
        "n_states": len(growth),
        "states": growth.reset_index(names="state").round(4).to_dict("records"),
        "epoch_us_sites": len(sites),
        "epoch_states": int(sites["state"].nunique()),
    }


def select_threshold(frame: pd.DataFrame) -> tuple[float, pd.Series]:
    """Apply the plan's rule using treatment counts only, before any outcome is touched."""
    onset = est.surge_onsets(frame, "ci_sales", PRIMARY_THRESHOLD)
    if np.isfinite(onset.dropna()).sum() >= MIN_TREATED:
        return PRIMARY_THRESHOLD, onset
    return FALLBACK_THRESHOLD, est.surge_onsets(frame, "ci_sales", FALLBACK_THRESHOLD)


def _staggered_row(result: est.StaggeredResult) -> dict:
    row = {
        "att": result.att,
        "se": result.se,
        "ci_low": result.ci_low,
        "ci_high": result.ci_high,
        "mde": result.mde,
        "n_states": result.n_states,
        "n_treated": result.n_treated,
        "n_never": result.n_never,
    }
    row["pretrend_chi2"] = result.pretrend_chi2
    row["pretrend_df"] = result.pretrend_df
    row["pretrend_p"] = float(chi2_dist.sf(result.pretrend_chi2, result.pretrend_df))
    return row


def _twfe_row(result: est.Estimate) -> dict:
    return {**asdict(result), "mde": result.mde}


def leave_one_out(frame: pd.DataFrame, onset: pd.Series) -> pd.DataFrame:
    rows = []
    for state in sorted(frame["state"].unique()):
        rest = frame[frame["state"] != state]
        p1 = est.twfe(rest, "ln_price", "ln_ci_lag1")
        data = est.to_staggered(rest, "ln_price", onset.drop(state))
        p2 = est.aggregate_att(est.group_time_att(data))
        rows.append({"dropped": state, "twfe": p1.coef, "att": p2})
    return pd.DataFrame(rows)


def run() -> dict:
    tables = load_tables()
    frame = prepare(tables["state_year_panel"])
    threshold, onset = select_threshold(frame)
    intensity = atlas_intensity(frame, tables["atlas_state"])

    primary_data = est.to_staggered(frame, "ln_price", onset)
    p1 = est.twfe(frame, "ln_price", "ln_ci_lag1")
    p2 = est.staggered(primary_data)

    observed, ri_p = est.randomization_p(primary_data)
    fake = est.fake_onset_placebo(primary_data)
    lead_fit = est.twfe(frame, "ln_price", "ln_ci_lead3", controls=("ln_ci_lag1",))
    lag_with_lead = est.twfe(frame, "ln_price", "ln_ci_lag1", controls=("ln_ci_lead3",))

    with_mix, mix_terms = fuel_mix_controls(frame)
    twfe_checks = {
        "Commercial-only exposure": est.twfe(frame, "ln_price", "ln_com_lag1"),
        "Division-by-year effects": est.twfe(frame, "ln_price", "ln_ci_lag1", division_year=True),
        "Baseline fuel mix x year": est.twfe(
            with_mix, "ln_price", "ln_ci_lag1", controls=mix_terms
        ),
        "Time-varying generation shares (possible bad control)": est.twfe(
            frame, "ln_price", "ln_ci_lag1", controls=("gas_share", "coal_share", "renewable_share")
        ),
        "Residential-customer weights": est.twfe(
            customer_weights(frame), "ln_price", "ln_ci_lag1", weights="customer_weight"
        ),
        "Secondary outcome: average bill": est.twfe(frame, "ln_bill", "ln_ci_lag1"),
    }

    staggered_checks = {}
    for value in SWEEP:
        onsets = est.surge_onsets(frame, "ci_sales", value)
        data = est.to_staggered(frame, "ln_price", onsets)
        staggered_checks[f"Threshold {value * 100:g} log points"] = est.staggered(data, draws=499)
    commercial = est.surge_onsets(frame, "com_sales", threshold)
    staggered_checks["Commercial-only exposure"] = est.staggered(
        est.to_staggered(frame, "ln_price", commercial), draws=499
    )
    staggered_checks["Secondary outcome: average bill"] = est.staggered(
        est.to_staggered(frame, "ln_bill", onset), draws=499
    )

    loo = leave_one_out(frame, onset)
    results = {
        "threshold_used": threshold,
        "sample": {
            "years": [int(frame["year"].min()), int(frame["year"].max())],
            "states": int(frame["state"].nunique()),
        },
        "onsets": [
            {"state": state, "onset": None if not np.isfinite(year) else int(year)}
            for state, year in onset.dropna().items()
        ],
        "already_treated": sorted(onset[onset.isna()].index),
        "p1_twfe": _twfe_row(p1),
        "p2_staggered": _staggered_row(p2),
        "event_study": p2.events.to_dict("records"),
        "placebos": {
            "randomization": {"observed_att": observed, "p": ri_p, "draws": 999},
            "fake_onset_att": fake,
            "future_load": _twfe_row(lead_fit),
            "lagged_load_with_future_control": _twfe_row(lag_with_lead),
        },
        "twfe_robustness": {name: _twfe_row(result) for name, result in twfe_checks.items()},
        "staggered_robustness": {
            name: _staggered_row(result) for name, result in staggered_checks.items()
        },
        "leave_one_out": {
            "twfe_range": [float(loo["twfe"].min()), float(loo["twfe"].max())],
            "att_range": [float(loo["att"].min()), float(loo["att"].max())],
            "named": loo[loo["dropped"].isin(NAMED_STATES)].to_dict("records"),
            "all": loo.to_dict("records"),
        },
        "atlas_intensity": atlas_event_study(frame, intensity),
        "exploratory_long_difference": long_difference(frame),
        "proxy_validation": proxy_validation(frame, intensity, tables["epoch_us_sites"]),
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "flagship.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    return results


if __name__ == "__main__":
    output = run()
    print(
        json.dumps({k: output[k] for k in ("threshold_used", "p1_twfe", "p2_staggered")}, indent=1)
    )
