# Large-load growth and residential electricity prices

*Policy brief. Independent analysis of public data, not affiliated with or endorsed by Anthropic.
Data through 2025. Specification committed in advance: [pre-analysis plan](pre_analysis_plan.md).*

## Question
Is growth in large commercial and industrial (C&I) electricity load, a proxy for data center
buildout, associated with changes in residential electricity prices? How much does the answer depend
on design choices?

## Bottom line
**This state-level data shows no evidence that faster large-load growth came with higher residential
prices through 2025. It also does not support the claim that load growth lowered them.**

- The baseline association is negative: a 10% larger load the year before goes with about 1.5% lower
  residential prices. It loses statistical significance under several reasonable changes in design.
- The negative association does not look like an effect of past load. Once future load is included,
  the coefficient on past load is close to zero, and the association sits on load that had not yet
  arrived. That fits low-price states attracting load, which is reverse causality.
- The pre-registered staggered design could not answer the question. Only 3 states qualified as
  treated, and Virginia, the largest data center market, was excluded because its load surge began
  before the design's window.
- The data ends in 2025, so it misses much of the AI-era buildout still under way. State averages
  also cannot show effects on a single utility's customers or across a regional market.

## Method in plain language
1. **The data.** Annual EIA retail sales for the 50 states and DC, 2001 to 2025. Price is residential
   revenue divided by residential kilowatt-hours.
2. **The proxy.** No public source gives dated data center capacity across all states over this
   period, so C&I sales stand in for large load. They also capture manufacturing, crypto mining, and
   oil and gas electrification. Across states, footprint in the IM3 Atlas has a moderate rank
   correlation with 2015 to 2025 growth: 0.43 for C&I sales, and 0.57 for commercial sales.
3. **Baseline (P1).** Compares each state with itself over time, net of nationwide changes in each
   year (two-way fixed effects, clustered by state).
4. **Staggered design (P2).** Marks the first year a state's 3-year load growth beat the nation by a
   set threshold, then compares its later price path with states not yet in a surge (Callaway and
   Sant'Anna style). This avoids a known bias in the baseline when timing varies, which the project's
   tests show on simulated data.
5. **Checks.** Pre-trends, three placebos, and nine robustness checks, all specified in advance.

## Results

### Primary estimates

| Estimate | Result | 95% interval | Read |
|---|---|---|---|
| P1: baseline elasticity | **−0.153** | −0.294 to −0.011 | Negative; detectable at 5% |
| P2: staggered ATT, event years 0 to +5 | **+0.012** (log points) | −0.022 to +0.043 | Uninformative: 3 treated states |

The two primaries disagree in sign. Under the plan's reporting rule, that disagreement is itself a
finding. It is not resolved by choosing one.

P2's interval is probably too narrow, because bootstrap intervals are unreliable with so few treated
clusters. Randomization inference is the better guide for P2: permuting onset years gives p = 0.827.
Its treated states are Iowa (2017), Oregon (2020), and Texas (2020).

### Is the baseline an effect of past load?

| Added to the baseline | Coefficient | 95% interval |
|---|---|---|
| Load 3 years **ahead** (placebo) | −0.150 | −0.336 to +0.035 |
| Load 1 year **before**, with future load included | +0.036 | −0.144 to +0.216 |

Future load cannot cause today's price. A coefficient this size, next to a near-zero coefficient on
past load, suggests the baseline reflects where load goes or shared trends. The placebo's own interval
includes zero and the sample is smaller, so this is a warning and not proof.

### Sensitivity of the baseline

| Specification | Coefficient | 95% interval | States |
|---|---|---|---|
| Baseline (P1) | −0.153 | −0.294 to −0.011 | 51 |
| Commercial load only | −0.115 | −0.258 to +0.028 | 51 |
| Census division-by-year effects | −0.086 | −0.192 to +0.020 | 51 |
| Baseline fuel mix by year | −0.150 | −0.288 to −0.013 | 47 |
| Generation shares (possible bad control) | −0.133 | −0.313 to +0.048 | 48 |
| Weighted by residential customers | −0.394 | −0.611 to −0.177 | 51 |
| Outcome: average bill (2008-09, 2016-25 only) | −0.051 | −0.172 to +0.070 | 51 |

No specification gives a positive estimate. Dropping any single state keeps the baseline between
−0.243 and −0.134. Comparing states only within their census division cuts the estimate by nearly
half, which suggests that much of the baseline is regional.

### Sensitivity of the staggered design

| Specification | ATT | 95% interval | Treated | Pre-trend p |
|---|---|---|---|---|
| Threshold 5 log points | +0.015 | −0.044 to +0.097 | 3 | 0.005 |
| **Threshold 7.5 (used)** | +0.012 | −0.022 to +0.043 | 3 | 0.33 |
| Threshold 10 | −0.049 | −0.113 to +0.011 | 4 | 0.148 |
| Threshold 15 | +0.117 | +0.081 to +0.152 | 1 | <0.001 |
| Commercial load only | +0.043 | −0.059 to +0.120 | 6 | 0.008 |

Estimates change sign across thresholds, treated groups are very small, and three of the five rows
fail the pre-trend check. The fake-onset placebo is also large (+0.067). Together these say this
design is not credible on this data. Its point estimates should not be quoted as findings, including
the one row whose interval excludes zero, which rests on a single state.

The average-bill version of P2 is omitted from the table. Customer counts are missing from 2010 to
2015, which leaves only the 2020 cohort of Oregon and Texas, so no pre-trend test is possible.

### Data center footprint (suggestive)
States with more mapped data center footprint saw slightly lower price growth after 2019, compared
with 2015: −0.015 per log unit (95% interval −0.025 to −0.006). However, the same comparison is already
negative in the years before 2012, including −0.021 in 2008, which points to pre-existing differences.
Footprint is also measured in 2026, after the fact. This check does not establish an effect.

### Exploratory, not pre-registered
Added after P2 turned out to exclude Virginia. Each state's 2015 to 2025 price change against its
load growth:

| Comparison | Coefficient | 95% interval |
|---|---|---|
| Across all 51 states | −0.255 | −0.439 to −0.071 |
| Within census division | −0.086 | −0.249 to +0.077 |
| Same load growth, against **earlier** 2005 to 2015 price change | −0.154 | −0.339 to +0.031 |

The last row is a warning: states with faster 2015 to 2025 load growth may already have had slower
price growth in the prior decade, though the interval includes zero.

## How this compares with other work
- **[Watten, Bistline, and Blanford (EPRI, 2026)](https://restservice.epri.com/publicattachment/98650)**
  address the same selection concern using an instrument: the state's length of the 1947 interstate
  highway plan. They report that doubling data center capacity lowered residential prices by 3.5%, from
  2015 to 2024. This brief cannot test that claim. It uses no such instrument and, unlike that study,
  has no dated capacity data. EPRI is a power-sector research institute, and its authors caution that
  the result may not extend to larger AI-era facilities. The instrument's exclusion restriction also
  needs scrutiny, since highways shaped where population and industry went, and the study says it
  controls for these separately.
- **[Garimella (Rutgers, 2026)](https://policylab.rutgers.edu/?p=11153)** uses household bill data and
  2,277 dated data centers. The evidence is described as weak, mixed, and small, with no significant
  effect at the utility level, through 2024. The author also notes that this design does not isolate
  regional market effects, and points to sharply higher PJM capacity prices.

All three share a limit: their data ends by 2025, before much of the announced AI-era buildout.

## Threats to identification
- **Reverse causality.** Large loads seek cheap power. This is the main threat, and the future-load
  test suggests it matters here.
- **Regional spillovers.** States share wholesale markets. If one state's load raises regional capacity
  costs, its neighbors bear them too, which biases state comparisons toward zero. This design would
  miss that channel entirely.
- **Utility regulation and rate cases.** Costs reach bills with lags that vary by state. Effects may come
  after this data ends.
- **Fuel price shocks.** Year effects absorb national shocks, but states differ in exposure. Baseline
  fuel mix helps only in part, and EIA withholds too much state fuel cost data to use directly.
- **Measurement.** Average price moves when usage changes even if no rate changes. Sector labels can
  also shift, and C&I load is a noisy proxy for data centers.
- **Power.** The minimum detectable elasticity for P1 is about 0.20, so moderate effects could be missed.

## What this does and doesn't tell a policymaker
**It does:**
- Weigh against a simple claim that states with faster large-load growth saw higher residential prices
  through 2025.
- Show that the negative association is too fragile, and too tied to future load, to support claims
  that large loads lower bills.
- Show that a credible answer needs dated, utility-level data on capacity and costs.

**It doesn't:**
- Isolate data centers from other large loads.
- Address local effects, a specific utility's customers, or how costs are allocated in a given rate case.
- Capture regional capacity market effects, or forecast the effect of hyperscale AI campuses.
- Say anything about tariffs or cost-allocation policy. A flat average in this data would not show
  those policies are unnecessary.

## What internal data would sharpen it
A company with its own facilities could add what public data lacks. This prototype has none of it.

- **Metered load and energization dates by facility**, to replace the proxy and give true treatment timing.
- **Interconnection and grid upgrade payments by utility**, to study cost allocation directly.
- **Curtailment records**, to study effects at peak, when system costs are set.
- **A utility-level design**: matching those dates to rate cases and to utility-level bills and tariffs.

Paired with public data, these could turn a state-level association into a utility-level evaluation.

## Deviations from the pre-analysis plan
1. **Threshold rule.** 10 log points gave 4 treated states, which is below the plan's minimum of 8, so
   the plan's fallback of 7.5 applied. That gave 3, and the plan had no further fallback. The result is
   reported as is and not tuned.
2. **Customer series gaps.** EIA's API has no customer counts for 2001 to 2007 or 2010 to 2015. The
   average-bill analyses use only available years, and customer weights use each state's earliest count.
3. **Alaska.** EIA leaves its 2016 residential values blank. No value was filled in, and that one state-year
   drops from the baseline. Alaska was already excluded from P2.
4. **Additions after seeing results.** The lagged coefficient with future load included, and the
   long-difference comparison. Both are labeled above.
5. **Code fixes after the first run.** Fixes were made for a failed standard error in the division-by-year
   specification and for customer weights that reduced the sample. No specification changed.

## Sources
- US Energy Information Administration, API v2: `electricity/retail-sales` and
  `electricity/electric-power-operational-data`.
- IM3 Open Source Data Center Atlas v2026.11.02, Pacific Northwest National Laboratory via MSD-LIVE,
  derived from OpenStreetMap. Open Database License (ODbL).
- Epoch AI, Frontier Data Centers, retrieved November 2026. CC BY 4.0. Used for context only.
- Callaway and Sant'Anna (2021), "Difference-in-Differences with Multiple Time Periods", *Journal of
  Econometrics*.
