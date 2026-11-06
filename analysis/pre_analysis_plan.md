# Pre-analysis plan: large-load growth and residential electricity prices

**Status:** committed before any outcome estimates were run. Git history is the timestamp. Before
writing this I had inspected data availability, data structure, and coverage, including the sparse
fuel-cost fields and the count of Atlas records by state. I had not regressed or compared prices
against load. Any change after this commit goes in the "Deviations" section of the case study.

## Question
Is growth in large commercial and industrial (C&I) electricity load, a proxy for data center
buildout, associated with changes in residential electricity prices, and how sensitive is the
answer to design choices?

This is an association study with a stated design. It does not identify the causal effect of data
centers specifically. The proxy also captures manufacturing, crypto mining, oil and gas
electrification, and general commercial growth.

## Why no dated data center treatment
- IM3 Atlas (ODbL): state and footprint, but no dates or capacity.
- Epoch Frontier Data Centers (CC BY 4.0): dated megawatt timelines, but 96 AI sites worldwide,
  mostly recent. Too few states and too little post-period for a staggered panel.

Load growth is therefore the exposure, and the study says so plainly.

## Data
EIA retail sales (annual, 2001 to 2025) for the 50 states and DC: `state_year_panel`. Prices are
nominal; year fixed effects absorb national inflation.

- **Primary outcome:** `ln(residential price)`.
- **Secondary outcome:** `ln(residential revenue per residential customer)`, an average bill measure,
  because price is average revenue per kWh and moves mechanically when household usage changes.

## Primary estimates
Two primary estimates are designated in advance. Everything else is a sensitivity analysis and is
not used to claim significance.

### P1. Baseline two-way fixed effects
`ln(res_price[s,t]) = b * ln(ci_sales[s,t-1]) + state FE + year FE + e`, with standard errors
clustered by state. `b` is an elasticity.

### P2. Staggered load-surge design
Group-time average treatment effects in the style of Callaway and Sant'Anna (2021).

- **Excess growth:** the state's 3-year log change in C&I sales minus the same change for the
  national total of the panel states. Trailing only, so onset never uses future data.
- **Onset:** the first year in 2012 to 2023 with excess growth of at least **10 log points**.
- **Dropped as already treated:** states that crossed the threshold from 2004 to 2011.
- **Never treated:** states with no crossing through 2023.
- **Treatment is treated as absorbing.** This is a simplification, and it is stated in the brief.
- **Rule if groups are thin:** if fewer than 8 states have an onset at 10 log points, use 7.5. This
  is checked on treatment counts only, before any outcome is used.
- **Base period:** `g-4`, the last year before the 3-year window that defines onset. Load is already
  rising in `g-3` to `g-1`, so those years are a ramp and not clean pre-treatment.
- **Comparison group:** never-treated states plus states not yet in their own ramp, meaning onset
  later than `t+3`.
- **Aggregation:** ATT over event times 0 to +5, with group-time cells weighted by group size.
- **Inference:** Bayesian bootstrap over states, 999 draws, seed fixed. 95% interval is percentile.
  The event study also reports sup-t simultaneous bands.

## Pre-trend check
Event times -8 to -5, relative to base `g-4`. Report a joint Wald test using the bootstrap covariance.
A passing test does not prove parallel trends, and low power will be stated. Ramp years -3 to -1 are
shown and labeled as a ramp.

## Placebos
1. **Randomization inference:** permute onset years across states, 999 times. Report the share of
   permutations with an ATT at least as large in magnitude.
2. **Fake earlier onset:** move each onset back 5 years and use only data before the true ramp.
3. **Future load:** add `ln(ci_sales[s,t+3])` to P1. A sizable coefficient on future load suggests
   reverse causality or shared trends. Report it either way.

## Robustness checks
Descriptive only.

1. Threshold sweep for P2: 5, 7.5, 10, 15 log points.
2. Commercial-only exposure, since data centers are often billed as commercial, for P1 and P2.
3. Census division-by-year effects in P1, to absorb regional shocks.
4. Baseline fuel mix (2001 to 2005 mean gas and coal generation shares) interacted with year
   effects, in P1.
5. Time-varying generation shares in P1, flagged as a possible bad control because load can change
   the generation mix.
6. Residential-customer weights in P1.
7. Leave-one-state-out for P1 and P2, reporting Virginia and Texas by name.
8. Secondary outcome (average bill) for P1 and P2.
9. Atlas intensity: `ln(1 + building sqft per 2015 GWh of total sales)` interacted with year, reference
   2015, with state and year effects. Report the mean 2019 to 2025 coefficient. Footprint is measured
   in 2026, after the fact, and from crowd-sourced data, so this is suggestive at most.

State-level fuel cost is **not** used as a control. EIA withholds it for many state-years, and years
2011 to 2013 and 2021 have no values for gas or coal. Baseline fuel mix (check 4) stands in for it.

## Proxy validation
Spearman correlation across states between Atlas intensity and 2015 to 2025 log growth in C&I sales,
and separately in commercial sales. If this is weak, the study must say the proxy tracks data centers
poorly. Epoch's US sites are shown as a descriptive overlay only.

## Reporting rules
- Report the point estimate, 95% interval, and minimum detectable effect (2.8 x SE) for both primaries.
- If an interval includes zero, say "no detectable association at this design's power", not "no effect".
- If P1 and P2 disagree, report the disagreement as a finding and do not choose the more convenient.
- Use "associated with" throughout. Use causal language only when describing what would be needed to
  claim it.
- Name the threats: reverse causality (cheap power attracts load), regional market spillovers (for
  example, shared capacity costs across a regional grid bias state comparisons toward zero), utility
  regulation and rate case lags, fuel shocks, weather, average-revenue measurement, and proxy error.
