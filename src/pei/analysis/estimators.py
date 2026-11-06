"""Estimators for the flagship study, kept free of any data access so they can be tested alone.

The staggered estimator is written here because the project's stack has no Callaway and Sant'Anna
implementation. It is checked against simulated data with a known answer in the tests.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

NEVER = np.inf


@dataclass(frozen=True)
class Estimate:
    coef: float
    se: float
    ci_low: float
    ci_high: float
    n_obs: int
    n_clusters: int

    @property
    def mde(self) -> float:
        """Minimum detectable effect at 80% power and 5% two-sided size."""
        return 2.8 * self.se


def twfe(
    panel: pd.DataFrame,
    outcome: str,
    exposure: str,
    controls: str = "",
    time_effects: str = "C(year)",
    weights: str | None = None,
) -> Estimate:
    """OLS with state and time effects, clustered by state. Rows with missing values are dropped."""
    formula = f"{outcome} ~ {exposure} + C(state) + {time_effects}"
    if controls:
        formula += f" + {controls}"
    needed = [outcome, exposure, "state", "year", "division"]
    for column in panel.columns:
        if column in controls and column not in needed:
            needed.append(column)
    if weights:
        needed.append(weights)
    data = panel[needed].replace([np.inf, -np.inf], np.nan).dropna().copy()
    groups = data["state"].astype("category").cat.codes
    cluster = {"cov_type": "cluster", "cov_kwds": {"groups": groups}}
    if weights:
        fit = smf.wls(formula, data, weights=data[weights]).fit(**cluster)
    else:
        fit = smf.ols(formula, data).fit(**cluster)
    low, high = fit.conf_int().loc[exposure]
    return Estimate(
        coef=float(fit.params[exposure]),
        se=float(fit.bse[exposure]),
        ci_low=float(low),
        ci_high=float(high),
        n_obs=int(fit.nobs),
        n_clusters=int(data["state"].nunique()),
    )


def surge_onsets(
    sales: pd.DataFrame,
    column: str,
    threshold: float,
    window: tuple[int, int] = (2012, 2023),
    lookback: int = 3,
) -> pd.Series:
    """First year of excess trailing load growth, by state.

    Returns the onset year, +inf for never-treated states, and NaN for states already over the
    threshold before the window opens. Uses only data up to each year, so no look-ahead.
    """
    wide = sales.pivot(index="year", columns="state", values=column).sort_index()
    national = np.log(wide.sum(axis=1))
    excess = np.log(wide).diff(lookback).sub(national.diff(lookback), axis=0)
    onset = {}
    for state in wide.columns:
        crossed = excess.index[excess[state] >= threshold]
        early = crossed[crossed < window[0]]
        in_window = crossed[(crossed >= window[0]) & (crossed <= window[1])]
        if len(early):
            onset[state] = np.nan
        elif len(in_window):
            onset[state] = float(in_window[0])
        else:
            onset[state] = NEVER
    return pd.Series(onset, name="onset")


@dataclass(frozen=True)
class StaggeredData:
    """Balanced outcome matrix (states by years) and onset years, with no missing cells."""

    outcome: np.ndarray
    years: np.ndarray
    states: list[str]
    onset: np.ndarray


def to_staggered(panel: pd.DataFrame, outcome: str, onset: pd.Series) -> StaggeredData:
    """Align outcome and onset. States already treated (NaN onset) are dropped."""
    keep = onset.dropna()
    wide = panel[panel["state"].isin(keep.index)].pivot(
        index="state", columns="year", values=outcome
    )
    wide = wide.replace([np.inf, -np.inf], np.nan).dropna(axis=0)
    keep = keep.loc[wide.index]
    return StaggeredData(
        wide.to_numpy(), wide.columns.to_numpy(), list(wide.index), keep.to_numpy()
    )


def _cells(data: StaggeredData, ramp: int) -> list[tuple[float, int, int, int]]:
    """List valid (group, base index, time index, event time) cells."""
    cells = []
    positions = {int(year): index for index, year in enumerate(data.years)}
    for group in np.unique(data.onset[np.isfinite(data.onset)]):
        base_year = int(group) - ramp - 1
        if base_year not in positions:
            continue
        for year, position in positions.items():
            if year != base_year:
                cells.append((group, positions[base_year], position, year - int(group)))
    return cells


def group_time_att(
    data: StaggeredData, weights: np.ndarray | None = None, ramp: int = 3
) -> pd.DataFrame:
    """ATT(g,t) from long differences against the base period g-ramp-1.

    Comparison states are never treated or have not yet entered their own ramp by max(t, base).
    A cell with no comparison states is omitted.
    """
    w = np.ones(len(data.states)) if weights is None else weights
    rows = []
    for group, base, time, event in _cells(data, ramp):
        change = data.outcome[:, time] - data.outcome[:, base]
        latest = data.years[max(time, base)]
        treated = data.onset == group
        comparison = data.onset > latest + ramp
        if not comparison.any() or not treated.any():
            continue
        att = np.average(change[treated], weights=w[treated]) - np.average(
            change[comparison], weights=w[comparison]
        )
        rows.append({"group": group, "event": event, "att": att, "weight": w[treated].sum()})
    return pd.DataFrame(rows, columns=["group", "event", "att", "weight"])


def aggregate_att(cells: pd.DataFrame, first: int = 0, last: int = 5) -> float:
    """Group-size weighted mean of ATT(g,t) over a span of event times."""
    use = cells[(cells["event"] >= first) & (cells["event"] <= last)]
    if use.empty:
        return float("nan")
    return float(np.average(use["att"], weights=use["weight"]))


def event_profile(cells: pd.DataFrame) -> pd.Series:
    """Group-size weighted ATT at each event time."""
    return cells.groupby("event").apply(
        lambda x: np.average(x["att"], weights=x["weight"]), include_groups=False
    )


@dataclass(frozen=True)
class StaggeredResult:
    att: float
    se: float
    ci_low: float
    ci_high: float
    n_states: int
    n_treated: int
    n_never: int
    events: pd.DataFrame
    pretrend_chi2: float
    pretrend_df: int

    @property
    def mde(self) -> float:
        return 2.8 * self.se


def staggered(
    data: StaggeredData,
    draws: int = 999,
    seed: int = 20261106,
    first: int = 0,
    last: int = 5,
    event_window: tuple[int, int] = (-8, 6),
    pre_window: tuple[int, int] = (-8, -5),
) -> StaggeredResult:
    """Point estimates plus Bayesian bootstrap inference, drawing weights by state."""
    point_cells = group_time_att(data)
    att = aggregate_att(point_cells, first, last)
    profile = event_profile(point_cells)
    events = [e for e in profile.index if event_window[0] <= e <= event_window[1]]

    rng = np.random.default_rng(seed)
    draws_att = np.empty(draws)
    draws_events = np.empty((draws, len(events)))
    for index in range(draws):
        weights = rng.exponential(size=len(data.states))
        cells = group_time_att(data, weights)
        draws_att[index] = aggregate_att(cells, first, last)
        draws_events[index] = event_profile(cells).reindex(events).to_numpy()

    se_events = np.nanstd(draws_events, axis=0, ddof=1)
    point_events = profile.loc[events].to_numpy()
    deviations = np.abs(draws_events - np.nanmean(draws_events, axis=0)) / se_events
    critical = float(np.nanquantile(np.nanmax(deviations, axis=1), 0.95))
    table = pd.DataFrame(
        {
            "event": events,
            "att": point_events,
            "se": se_events,
            "ci_low": np.nanpercentile(draws_events, 2.5, axis=0),
            "ci_high": np.nanpercentile(draws_events, 97.5, axis=0),
            "band_low": point_events - critical * se_events,
            "band_high": point_events + critical * se_events,
        }
    )

    pre = [i for i, e in enumerate(events) if pre_window[0] <= e <= pre_window[1]]
    chi2 = float("nan")
    if pre:
        complete = draws_events[:, pre]
        complete = complete[~np.isnan(complete).any(axis=1)]
        cov = np.atleast_2d(np.cov(complete, rowvar=False))
        vector = point_events[pre]
        chi2 = float(vector @ np.linalg.pinv(cov) @ vector)
    return StaggeredResult(
        att=att,
        se=float(np.nanstd(draws_att, ddof=1)),
        ci_low=float(np.nanpercentile(draws_att, 2.5)),
        ci_high=float(np.nanpercentile(draws_att, 97.5)),
        n_states=len(data.states),
        n_treated=int(np.isfinite(data.onset).sum()),
        n_never=int(np.isinf(data.onset).sum()),
        events=table,
        pretrend_chi2=chi2,
        pretrend_df=len(pre),
    )


def randomization_p(data: StaggeredData, draws: int = 999, seed: int = 7) -> tuple[float, float]:
    """Permute onset years across states. Returns the observed ATT and a two-sided p-value."""
    observed = aggregate_att(group_time_att(data))
    rng = np.random.default_rng(seed)
    extreme = 0
    valid = 0
    for _ in range(draws):
        shuffled = StaggeredData(data.outcome, data.years, data.states, rng.permutation(data.onset))
        value = aggregate_att(group_time_att(shuffled))
        if np.isnan(value):
            continue
        valid += 1
        extreme += abs(value) >= abs(observed)
    return observed, (extreme + 1) / (valid + 1)


def fake_onset_placebo(data: StaggeredData, shift: int = 5, ramp: int = 3) -> float:
    """Move onsets earlier and use only years before each state's true ramp began.

    Years at or after the earliest true ramp are removed, so any 'effect' here is a pre-existing
    difference and not the real treatment.
    """
    finite = data.onset[np.isfinite(data.onset)]
    cutoff = finite.min() - ramp
    keep = data.years < cutoff
    moved = np.where(np.isfinite(data.onset), data.onset - shift, data.onset)
    sub = StaggeredData(data.outcome[:, keep], data.years[keep], data.states, moved)
    return aggregate_att(group_time_att(sub))
