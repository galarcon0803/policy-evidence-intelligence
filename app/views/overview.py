import streamlit as st
from common import DISCLAIMER, footer, query, registry, table_exists

st.title("Policy Evidence & Intelligence")
st.markdown(
    "A working prototype of how a policy team could track legislation, keep externally shared "
    "numbers consistent, and evaluate policy questions honestly. The flagship use case is "
    "electricity affordability and data center accountability."
)
st.info(DISCLAIMER)

tracked = (
    query("SELECT count(DISTINCT bill_id) AS n FROM bill_pillars WHERE is_relevant")["n"].iloc[0]
    if table_exists("bill_pillars")
    else 0
)
computable = sum(m["status"] == "computable" for m in registry())
schema_only = sum(m["status"] == "requires_internal" for m in registry())
years = query("SELECT min(year) AS a, max(year) AS b FROM state_year_panel").iloc[0]

first, second, third = st.columns(3)
first.metric("Bills tracked", f"{tracked:,}" if table_exists("bill_pillars") else "Pending")
second.metric(
    "Live metrics",
    computable,
    f"+{schema_only} proposed",
    delta_color="off",
    delta_arrow="off",
)
third.metric("State energy panel", f"{years['a']}-{str(years['b'])[-2:]}")

st.header("Three connected capabilities")
left, middle, right = st.columns(3)
with left:
    st.subheader("1. Policy intelligence")
    st.markdown(
        "Ingests real congressional records, classifies each bill against four policy pillars, and "
        "produces alerts and a digest. Every model claim must quote its source, and code checks that "
        "the quote exists. The classifier is scored against hand labels."
    )
with middle:
    st.subheader("2. Evidence infrastructure")
    st.markdown(
        "A governed registry gives each metric one definition, its provenance, version history, and "
        "how it can be misread. A claims ledger recomputes every published number, and CI fails if "
        "one drifts."
    )
with right:
    st.subheader("3. Impact evaluation")
    st.markdown(
        "A pre-registered study of large-load growth and residential prices. It reports its "
        "assumptions, uncertainty, failed designs, and mixed results as found."
    )

st.header("How they connect")
st.markdown(
    "The **registry** defines the numbers used in the **study**. The **study** page lists tracked bills "
    "from **intelligence**, so evidence and legislation sit side by side. The **claims ledger** ties "
    "the brief's numbers back to their source, so a change anywhere is caught before it is published."
)

st.header("What's real, and what isn't")
st.markdown(
    """
| Item | Status |
|---|---|
| Bills, sponsors, cosponsors, actions, summaries | Real, from Congress.gov |
| House roll call votes | Real, from the House Clerk |
| Senate roll call votes | Real, from Voteview (UCLA), a secondary source, because senate.gov refused this client |
| Electricity prices and sales | Real, from EIA |
| Data center locations | Real but incomplete, from the IM3 Atlas (OpenStreetMap) and Epoch AI |
| Claude usage metrics | Real public release, the Anthropic Economic Index, not internal data |
| Pillar relevance, lens flags, questions | Model output, evaluated against hand labels on the Methods page |
| Internal metrics (energy per workload, grid costs covered) | **Schema only. No value exists or is shown.** |
"""
)
st.markdown(
    "**Out of scope:** state legislation and utility commission dockets (where most rate decisions "
    "happen), news, non-US policy, and any prediction of how a legislator will vote."
)
footer()
