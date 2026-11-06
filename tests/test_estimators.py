"""The staggered estimator must recover known answers on simulated data."""

import numpy as np
import pandas as pd
import pytest

from pei.analysis import estimators as est


def simulate(effect=0.05, dynamic=0.0, trend_gap=0.0, seed=1, states=60, noise=0.01):
    """A staggered panel with a known treatment effect beginning at each state's onset."""
    rng = np.random.default_rng(seed)
    years = np.arange(2001, 2026)
    onset_choices = [2014, 2017, 2020, np.inf]
    rows = []
    for index in range(states):
        onset = onset_choices[index % len(onset_choices)]
        state_level = rng.normal(0, 0.2)
        for year in years:
            shock = 0.02 * (year - 2001)
            value = state_level + shock + rng.normal(0, noise)
            if np.isfinite(onset):
                value += trend_gap * (year - 2001)
                if year >= onset:
                    value += effect + dynamic * (year - onset)
            rows.append(
                {"state": f"S{index}", "division": "d", "year": year, "y": value, "onset": onset}
            )
    return pd.DataFrame(rows)


def staggered_from(frame):
    onset = frame.groupby("state")["onset"].first()
    return est.to_staggered(frame, "y", onset)


def test_recovers_constant_effect():
    result = est.staggered(staggered_from(simulate(effect=0.05)), draws=150)
    assert result.att == pytest.approx(0.05, abs=0.005)
    assert result.ci_low < 0.05 < result.ci_high


def test_recovers_zero_effect_and_covers_it():
    result = est.staggered(staggered_from(simulate(effect=0.0)), draws=150)
    assert abs(result.att) < 0.005
    assert result.ci_low < 0 < result.ci_high


def test_recovers_dynamic_effect_at_each_event_time():
    cells = est.group_time_att(staggered_from(simulate(effect=0.02, dynamic=0.01)))
    profile = est.event_profile(cells)
    for event in range(6):
        assert profile.loc[event] == pytest.approx(0.02 + 0.01 * event, abs=0.006)


def test_pre_event_estimates_are_near_zero_with_parallel_trends():
    result = est.staggered(staggered_from(simulate()), draws=100)
    pre = result.events[result.events["event"].between(-8, -5)]
    assert (pre["att"].abs() < 0.01).all()


def test_pretrend_statistic_detects_violated_parallel_trends():
    clean = est.staggered(staggered_from(simulate(trend_gap=0.0)), draws=100)
    broken = est.staggered(staggered_from(simulate(trend_gap=0.01)), draws=100)
    assert broken.pretrend_chi2 > clean.pretrend_chi2 * 5


def test_twfe_is_biased_with_dynamic_effects_but_staggered_design_is_not():
    """The reason for the staggered design: already-treated units contaminate TWFE comparisons."""
    frame = simulate(effect=0.0, dynamic=0.02)
    frame["treated"] = (frame["year"] >= frame["onset"]).astype(float)
    pooled = est.twfe(frame, "y", "treated")
    cells = est.group_time_att(staggered_from(frame))
    truth = est.event_profile(cells).loc[0:5].mean()
    assert truth == pytest.approx(0.05, abs=0.01)
    assert abs(pooled.coef - truth) > abs(est.aggregate_att(cells) - truth)


def test_twfe_recovers_elasticity_and_counts_clusters():
    rng = np.random.default_rng(2)
    rows = []
    for state in range(40):
        level = rng.normal()
        for year in range(2001, 2021):
            x = level + 0.1 * year + rng.normal()
            rows.append(
                {
                    "state": f"S{state}",
                    "division": "d",
                    "year": year,
                    "x": x,
                    "y": 0.3 * x + level + 0.05 * year + rng.normal(0, 0.1),
                }
            )
    result = est.twfe(pd.DataFrame(rows), "y", "x")
    assert result.coef == pytest.approx(0.3, abs=0.02)
    assert result.n_clusters == 40
    assert result.mde == pytest.approx(2.8 * result.se)


def test_onset_uses_no_future_data_and_labels_groups():
    years = list(range(2001, 2026))
    frame = []
    paths = {
        "EARLY": lambda y: 100 * (1.3 if y >= 2006 else 1.0),
        "LATE": lambda y: 100 * (1.3 if y >= 2018 else 1.0),
        "FLAT": lambda y: 100.0,
    }
    paths.update({f"F{i}": (lambda y: 100.0) for i in range(30)})
    for state, path in paths.items():
        frame += [{"state": state, "year": y, "load": path(y)} for y in years]
    frame = pd.DataFrame(frame)
    onset = est.surge_onsets(frame, "load", threshold=0.10)
    assert np.isnan(onset["EARLY"])
    assert onset["LATE"] == 2018
    assert np.isinf(onset["FLAT"])

    # Changing data after the onset year must not change the onset.
    changed = frame.copy()
    changed.loc[(changed["state"] == "LATE") & (changed["year"] > 2018), "load"] = 50.0
    assert est.surge_onsets(changed, "load", threshold=0.10)["LATE"] == 2018


def test_randomization_inference_separates_real_effect_from_noise():
    _, real = est.randomization_p(staggered_from(simulate(effect=0.08, noise=0.02)), draws=99)
    _, null = est.randomization_p(staggered_from(simulate(effect=0.0, noise=0.02)), draws=99)
    assert real < 0.05
    assert null > 0.05


def test_fake_onset_placebo_is_near_zero_when_real_effect_exists():
    placebo = est.fake_onset_placebo(staggered_from(simulate(effect=0.10)))
    assert abs(placebo) < 0.01


def test_division_year_spec_matches_within_estimate_and_survives_missing_rows():
    """Real data is unbalanced, and the standard error must stay finite with missing rows."""
    rng = np.random.default_rng(3)
    rows = []
    for state in range(40):
        division = f"D{state % 5}"
        level = rng.normal()
        for year in range(2001, 2021):
            x = level + (state % 5) * 0.01 * year + rng.normal()
            y = 0.4 * x + level + (state % 5) * 0.03 * year + rng.normal(0, 0.1)
            rows.append({"state": f"S{state}", "division": division, "year": year, "x": x, "y": y})
    frame = pd.DataFrame(rows)
    fit = est.twfe(frame, "y", "x", division_year=True)

    within = frame.copy()
    for column in ("x", "y"):
        within[column] -= within.groupby("state")[column].transform("mean")
        within[column] -= within.groupby(["division", "year"])[column].transform("mean")
    direct = (within["x"] * within["y"]).sum() / (within["x"] ** 2).sum()
    assert fit.coef == pytest.approx(direct, abs=1e-5)
    assert np.isfinite(fit.se) and fit.se > 0

    unbalanced = frame.drop(index=frame.sample(frac=0.05, random_state=1).index)
    assert np.isfinite(est.twfe(unbalanced, "y", "x", division_year=True).se)
