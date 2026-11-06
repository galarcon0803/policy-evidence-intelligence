import pandas as pd
import streamlit as st
from common import ROOT, eval_results, footer, pillars, query, table_exists

from pei.metrics.registry import check_claims, load_claims

st.title("Methods & evaluation")
names = pillars()

st.header("Classifier against human labels")
results = eval_results()
if results is None:
    st.info("Hand labels have not been scored yet, so no accuracy figures exist.")
else:
    st.markdown(
        f"One person labeled {results['labels_total']} bills blind, before seeing any classifier "
        "output, using the same definitions the classifier is given. "
        f"{results['labels_scored']} of them passed the title filter and are scored here, and the "
        f"other {results['labels_total'] - results['labels_scored']} measure the filter itself. "
        "This is a small sample with one labeler, drawn to balance the pillars rather than to mirror "
        "all bills, so intervals are wide, inter-rater agreement is not measured, and these rates "
        "should not be read as population estimates."
    )
    table = pd.DataFrame(results["classifier"])
    table["Pillar"] = table["pillar"].map({**names, "all_pillars": "All pillars (micro-average)"})

    def formatted(row, name):
        if pd.isna(row[name]):
            return "n/a"
        return f"{row[name]:.0%} ({row[name + '_low']:.0%} to {row[name + '_high']:.0%})"

    table["Precision (95% CI)"] = table.apply(formatted, axis=1, name="precision")
    table["Recall (95% CI)"] = table.apply(formatted, axis=1, name="recall")
    st.dataframe(
        table[["Pillar", "n", "tp", "fp", "fn", "Precision (95% CI)", "Recall (95% CI)"]],
        hide_index=True,
        use_container_width=True,
    )
    st.caption(
        "Wilson score intervals. Source: eval/labels.csv and classifier output. Computed in this project."
    )

    if results.get("disagreements"):
        st.subheader("Where the classifier and the human disagree")
        differ = pd.DataFrame(results["disagreements"])
        differ["Pillar"] = differ["pillar"].map(names)
        differ["Human"] = differ["label"].map({1: "Relevant", 0: "Not relevant"})
        differ["Model score (0 to 3, relevant at 2+)"] = differ["relevance"]
        st.dataframe(
            differ.rename(columns={"bill_id": "Bill", "title": "Title"})[
                ["Bill", "Title", "Pillar", "Human", "Model score (0 to 3, relevant at 2+)"]
            ],
            hide_index=True,
            use_container_width=True,
        )

    st.subheader("What the title filter misses")
    misses = pd.DataFrame(results["filter_misses"])
    if not misses.empty:
        misses["Stratum"] = misses["stratum"].map(
            {
                "rejected_near_miss": "Rejected, adjacent word in title",
                "rejected_other": "Rejected, everything else",
            }
        )
        misses["Rate (95% CI)"] = misses.apply(
            lambda r: f"{r['relevant']} of {r['n']} ({r['rate_low']:.0%} to {r['rate_high']:.0%})",
            axis=1,
        )
        st.dataframe(
            misses[["Stratum", "Rate (95% CI)"]], hide_index=True, use_container_width=True
        )
        st.caption(
            "Bills the title filter rejected, then labeled by hand. A sample this small can only flag a "
            "large problem, and it cannot certify that few relevant bills are missed."
        )
    estimate = results.get("filter_estimate")
    if estimate:
        st.markdown(
            f"**This is a real gap.** Scaled to the {estimate['near_miss_size']:,} rejected bills with "
            f"an adjacent title word, the sample implies roughly {estimate['near_miss_missed']:,} "
            f"relevant bills missed (range {estimate['near_miss_missed_low']:,} to "
            f"{estimate['near_miss_missed_high']:,}), against {estimate['relevant_found']:,} the "
            f"pipeline found. Counting only that group, the filter would catch about "
            f"{estimate['filter_recall_near_miss_only']:.0%} of relevant bills (range "
            f"{estimate['filter_recall_low']:.0%} to {estimate['filter_recall_high']:.0%}). The other "
            f"{estimate['other_size']:,} rejected bills had no relevant bill in the sample, but a "
            f"sample of 10 still allows a rate up to {estimate['other_rate_high']:.0%}, so true "
            "coverage could be lower. Treat tracked bills as a useful set, not a complete one."
        )

    if results.get("retest"):
        retest = results["retest"]
        st.subheader("Repeat-run consistency")
        st.markdown(
            f"Classifying the labeled bills a second time matched on {retest['agreement']:.0%} of "
            f"{retest['n']} bill-pillar decisions. The model has no seed, so repeat runs can differ. "
            "The pipeline's cache pins each result, so what you see here won't change unless the bill or "
            "prompt does."
        )

if table_exists("classifier_runs"):
    st.header("Pipeline health")
    runs = query(
        """
        SELECT count(*) AS bills,
            count(*) FILTER (status = 'ok') AS valid,
            count(*) FILTER (first_attempt_status <> 'ok') AS first_failed,
            string_agg(bill_id, ', ') FILTER (status <> 'ok') AS still_failed,
            sum(quote_count) AS quotes,
            sum(quote_failures) AS failed_quotes,
            count(*) FILTER (bill_text_truncated) AS truncated,
            count(*) FILTER (NOT has_bill_text) AS no_text,
            count(*) FILTER (NOT has_summary) AS no_summary,
            string_agg(DISTINCT model_served, ', ') AS models,
            string_agg(DISTINCT prompt_version, ', ') AS prompts
        FROM classifier_runs
        """
    ).iloc[0]
    columns = st.columns(3)
    columns[0].metric("Bills sent to the classifier", f"{runs['bills']:,}")
    columns[1].metric("Valid structured output", f"{runs['valid']:,}")
    rate = 1 - runs["failed_quotes"] / runs["quotes"] if runs["quotes"] else float("nan")
    columns[2].metric(
        "Quotes found in cited source",
        f"{rate:.1%}",
        f"{int(runs['failed_quotes'])} not found",
        delta_color="off",
    )
    st.markdown(
        f"Model: `{runs['models']}`. Prompt: `{runs['prompts']}`. {int(runs['truncated'])} bills had text "
        f"cut to the first 24,000 characters, {int(runs['no_text'])} had no published text, and "
        f"{int(runs['no_summary'])} had no CRS summary. A quote that fails the check stays visible and "
        "is flagged in the bill explorer."
    )
    if runs["first_failed"]:
        st.markdown(
            f"{int(runs['first_failed'])} outputs failed validation on the first attempt, because "
            "they scored a bill relevant but gave no questions. Each was retried once. "
            + (
                f"Still failing, so absent from every page: {runs['still_failed']}."
                if runs["still_failed"]
                else "All passed on retry."
            )
        )

if table_exists("source_freshness"):
    st.header("Source coverage and freshness")
    freshness = query("SELECT * FROM source_freshness")
    st.dataframe(
        freshness.rename(
            columns={
                "source": "Source",
                "tier": "Tier",
                "latest_official_date": "Latest record",
                "fetched_on": "Fetched",
                "records": "Records",
            }
        ),
        hide_index=True,
        use_container_width=True,
    )
    st.caption(
        "The demo is a committed snapshot, so it does not update on its own. Latest record is the newest date "
        "in the source's own data."
    )

st.header("Published numbers")
claims = load_claims(ROOT / "metrics" / "published_claims.yaml")
problems = check_claims(ROOT)
if problems:
    st.error(f"{len(problems)} published numbers have drifted.")
    for problem in problems:
        st.write(problem)
else:
    st.success(
        f"All {len(claims)} pinned numbers match their sources, checked as this page loaded."
    )
with st.expander("Claims ledger"):
    st.dataframe(
        pd.DataFrame(
            [
                {"Claim": c.id, "Source": c.source, "As of": c.as_of, "Data hash": c.source_hash}
                for c in claims
            ]
        ),
        hide_index=True,
        use_container_width=True,
    )

st.header("Known limitations")
st.markdown(
    """
- **Federal only.** Most electricity rate decisions happen at state commissions, which aren't covered.
- **Title filter.** The bill list can only be filtered by title, and the hand-labeled sample above shows it misses a meaningful share of relevant bills.
- **Single labeler.** Labels come from one person, in a small sample.
- **Senate votes are secondary.** Voteview lags official records, and its site states no data license.
- **Alerts use a reconstructed baseline.** They rely on dated official records, not on two saved copies of the data.
- **Regulatory documents are keyword-matched.** Their precision was not measured.
- **US only.** The role covers policymakers worldwide, and this prototype doesn't.
"""
)

st.header("Roadmap")
st.markdown(
    """
1. Add state legislation and utility commission dockets, where cost allocation is actually decided.
2. Move the flagship study to utility level, with dated capacity data.
3. Add news ingestion, and evaluate coverage accuracy per the communications measurement design.
4. Add a second labeler and report inter-rater agreement.
5. Run scheduled refreshes, with alerts built from true snapshot diffs.
"""
)
footer()
