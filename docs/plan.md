# Plan: Policy Evidence & Intelligence prototype

## Context
An independent proposal for a policy data science function, with a public, clone-and-run prototype behind it. Electricity affordability and data center accountability are the flagship case.

Decisions:
- A person hand-labels the eval set blind.
- API spend is capped at $15, with a 20-bill pilot first.

## Job posting check: brief vs. posting
| Posting asks for | Brief today | Plan |
|---|---|---|
| Turning internal **product usage and survey data** into evidence | Not mentioned | Metric cards from Anthropic's public Economic Index (MIT license); survey data appears as a labeled schema only |
| Choosing metrics that **faithfully represent** the company | Internal metric schemas | Add `decision_use`, `misread_risk`, and `does_not_show` fields to the registry |
| Keeping **externally shared numbers consistent** (IR standards preferred) | Code-level duplicate check | Add a published claims ledger enforced in CI |
| AI aggregation of **news and regulatory developments** | Congress only | Add Federal Register after the core flow works; news and state utility commissions go on the roadmap, stated as gaps |
| Measurement for **comms, paid media, and public affairs** | Stretch item, no paid media | Required design doc that includes paid media (no build, no invented data) |
| Policy analysis with **quasi-experimental methods** | Covered | Flagship study |

This prototype is US-only, while the role covers policymakers worldwide. The README says so.

## What the source checks changed
| Finding | Consequence |
|---|---|
| Congress.gov's bill list docs show no keyword search; the 119th Congress has 19,841 bills | Page through all bills, filter locally on title and policy area, then fetch detail for candidates. The eval sample includes filter-rejected bills so missed bills can be measured |
| `house-vote` endpoint works and links to Clerk XML | House votes are straightforward |
| `senate-vote` returns 404, and senate.gov refuses this client | Senate votes come from Voteview, labeled as a secondary source. No block workarounds |
| Congress.gov docs reviewed so far don't show committee assignments on the member endpoint | Check at build time; candidate sources are Clerk member data and `congress-legislators` |
| The 119th Congress ends Jan 3, 2027, and today is after the 2026 election | Congress number is configurable; the app shows that unenacted bills die with this Congress |
| EIA `retail-sales` runs 2001-01 to 2026-08 with price, sales, revenue, customers | Metadata is confirmed. Data rows confirmed with a real key |
| EIA operational data has `generation`, `cost-per-btu` by location and fuel; units came back blank | Confirm units and state coverage before using as controls |
| IM3 Atlas (ODbL, from OpenStreetMap): state, county, sqft, but **no dates or MW** | Can't set treatment timing. Use it for cross-sectional intensity and to validate the proxy; committed aggregates carry ODbL attribution and share-alike |
| Epoch Frontier Data Centers (CC BY 4.0): dated MW timelines, but only **96 AI sites worldwide** | Too few sites and too little post-period for a staggered panel. Descriptive overlay only |

So the brief's fallback applies: **load growth is the continuous exposure, and the study says so plainly.**

## Repo structure
Follows the brief, with one change: code lives in `src/pei/{ingest,transform,classify,metrics,analysis}` so it installs as a proper package and tests and the app import it the same way. SQL models live in `src/pei/transform/sql/`. Other additions: `metrics/published_claims.yaml`, `analysis/pre_analysis_plan.md`, `eval/codebook.md`.

## Milestones
Tests run after each one and I show what works. Commits are logical and scanned for secrets first.

**M0: Scaffold.** `uv` project, `.env.example`, `.gitignore`, ruff, pytest, CI, `docs/plan.md`, config file for keywords.

**M1: Ingest.** Store raw JSON/XML with fetch timestamps. Include retries, rate limiting, and resumable runs.
- Congress.gov: bills, cosponsors, committees, actions, summaries, text versions, members
- House votes
- Senate votes per the rule above
- EIA: retail sales and operational data
- IM3 Atlas, Epoch, Economic Index
- Federal Register is added at the end of M4, once the core flow works

**M2: SQL transforms (DuckDB).** Clean tables for bills, members, cosponsorships, actions, votes, and `state_year_panel`. Evidence type (sponsor, cosponsor, procedural vote, final passage vote) is a column. Procedural vs. passage is derived from the official vote question and type; anything ambiguous stays "unclassified". Change detection compares snapshots. Take a real early snapshot so the alerts diff is real, and label the snapshot dates.

**M3: Metrics registry.**
- `registry.yaml` with the brief's fields plus the three faithful-representation fields
- Computable metrics: residential price, YoY change, C&I load growth, tracked bills by pillar and stage, Economic Index metrics
- Schema-only metrics marked "requires Anthropic internal data", including energy per quality-adjusted workload (with absolute consumption alongside, to show why they must be separate) and share of attributable grid costs covered, linked to [Anthropic's Feb 2026 public commitment](https://www.anthropic.com/news/covering-electricity-price-increases)
- Validator: entries are complete and every SQL query runs
- Consistency check: metric SQL lives only in the registry, and a test flags hardcoded duplicates of canonical logic. This is pattern-based, and the docs will say so rather than imply full static proof
- Claims ledger: pins each published number to metric ID, version, as-of date, and source hash. CI recomputes from the snapshot and fails on drift

**M4: Classifier and eval.**
- `claude-sonnet-5-5` via `MODEL` env var, using `messages.parse` with Pydantic. Before writing the code, read the skill's Python docs and confirm the current `parse` signature.
- Batch API at 50% off, cache keyed on hash of content + prompt version + model. Server-side refusal fallback is enabled (per Claude API guidance); record the model that actually served each result.
- Prompt in `prompts/classify_v1.md`.
- Output: pillars with relevance and rationale, cross-cutting flags, questions, each claim with a source field and verbatim quote.
- **A deterministic check confirms each quote exists in the cited source field**, and failures are flagged and counted. Change type is computed in SQL, not by the LLM.
- Pilot 20 bills, project cost, and stop if it exceeds $15.
- **Hard gate:** sample and codebook go to the labeler before they see any classifier output for the labeled sample. About 60 bills, stratified by pillar with filter-rejected negatives, labeled in about an hour.
- Report precision and recall per pillar with Wilson intervals, filter recall estimated from the rejected sample, quote-check pass rate, repeat-run agreement, source coverage, and freshness. Small-sample width stays visible.
- Outputs: ranked alerts, pillar-organized digest with primary links, member view with evidence types and no vote predictions.

**M5: Flagship study.**
- **Commit `analysis/pre_analysis_plan.md` before estimating**, so git history shows the specification came first. Any later deviation is listed in the brief.
- Panel: 50 states + DC, annual 2001-2025; log price, so year fixed effects absorb national inflation.
- Proxy validation: does C&I load growth track Atlas data center intensity? Report this honestly, since manufacturing, crypto, and oil and gas also drive load.
- Baseline: TWFE of log residential price on lagged log C&I sales, clustered by state.
- Staggered design: trailing-only load-surge onset (no look-ahead), Callaway-Sant'Anna group-time ATTs with not-yet-treated controls and a bootstrap, plus an event study and pre-trend test. Hand-written because no statsmodels or linearmodels equivalent is in the stack, and **a test must recover a known effect on simulated data before it touches real data**.
- Robustness: threshold sweep, commercial-only exposure, census division-by-year effects, leave-one-state-out (including VA and TX), with and without fuel and generation controls (flagged as possible mediators), Atlas intensity x post-period DiD.
- Placebos: fake onset in the pre-AI window and randomization inference on timing. Report minimum detectable effect.
- Threats: reverse causality, regional market spillovers (e.g. shared PJM capacity costs, which would bias state comparisons toward zero), utility regulation differences, fuel shocks, rate case lags, price being average revenue per kWh, and the proxy's measurement error.
- `analysis/flagship_case_study.md` in the brief's policy format, with results as found, including null or ambiguous ones. Set against the [EPRI](https://letsdatascience.com/news/epri-study-finds-data-centers-lowered-us-power-rates-through-a35af114) and [Rutgers](https://policylab.rutgers.edu/?p=11153) work only after reading the primary papers.

**M6: Dashboard.** The six specified pages run from committed snapshot files in demo mode, loaded into DuckDB at startup. Restrained design, a source line on every chart, the independence disclaimer on the Overview page and in the footer. Use the `dataviz` skill for chart design. Check every page in the browser pane at desktop and phone widths.

**M7: Docs.** `docs/comms_measurement.md` (required: content analysis, surveys, pre/post, paid media geo holdouts), architecture, roadmap. README per brief, including screenshots, what's real vs. synthetic, findings only after the study is done, and an accurate AI-use note saying Claude Code built it, a person labeled the data, and Claude is the classifier.

**M8: Fresh-clone test, then GitHub.** Clone to a temp folder and time demo mode from the README's three commands (target under 2 minutes). Run ruff, pytest, and a secret scan. **Then ask before creating the repo or pushing.** Afterward, optional scheduled refresh and Streamlit Community Cloud walkthrough.

If time gets tight, cut in this order: Federal Register, scheduled refresh, Epoch overlay, Streamlit Cloud. The cuts get documented, never faked.

## Verification
- `ruff check` and `pytest` pass locally and in CI: API parsers against recorded fixtures, SQL transforms, registry validator, claims ledger including a deliberate-drift test, quote check, simulated-data recovery for the estimator
- Live small call for each source before building on it, with differences noted in `docs/`
- App runs with no keys present, every page loads, no console or runtime errors
- Spot-check a sample of displayed bills and votes and all headline numbers against primary sources
- Fresh-clone timing as in M8

## Sources checked
[IM3 Atlas](https://www.osti.gov/dataexplorer/biblio/dataset/2550666) · [Epoch Frontier Data Centers](https://epoch.ai/data/data-centers) · [Congress.gov bill endpoint docs](https://github.com/LibraryOfCongress/api.congress.gov/blob/main/Documentation/BillEndpoint.md) · [Anthropic electricity commitment](https://www.anthropic.com/news/covering-electricity-price-increases) · [EIA API docs](https://www.eia.gov/opendata/documentation/APIv2.1.0.pdf) · [Economic Index](https://huggingface.co/datasets/Anthropic/EconomicIndex)
