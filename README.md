# Policy Evidence & Intelligence

**Work in progress.** An independent proposal and prototype, not affiliated with or endorsed by
Anthropic. It uses no Anthropic internal data.

A prototype of how a policy team could track legislation, keep externally shared numbers consistent,
and evaluate policy questions honestly, using electricity affordability and data center
accountability as the flagship case.

## Current status

| Part | Status |
|---|---|
| Flagship causal study | Complete: [brief](analysis/flagship_case_study.md), [pre-analysis plan](analysis/pre_analysis_plan.md) |
| Metrics registry and claims ledger | Working, except one metric that needs classifier output |
| Ingest and SQL transforms | Written; legislative tables are not in the demo snapshot yet |
| Bill classifier and evaluation | Written; not yet run, and hand labels are pending |
| Dashboard | Metrics and flagship pages work; Intelligence and Members pages show as pending |

## Run the dashboard

Requires [uv](https://docs.astral.sh/uv/). No API keys are needed.

```bash
uv sync
```

```bash
uv run streamlit run app/streamlit_app.py
```

Data sources and licenses are listed in [data/snapshot/NOTICE.md](data/snapshot/NOTICE.md).
