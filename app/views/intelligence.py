import streamlit as st
from common import ROOT, footer, pillars, query, stage_label

from pei.intelligence import build_digest
from pei.metrics.registry import connect_snapshot

st.title("Policy intelligence")
names = pillars()
baseline = query("SELECT baseline_date FROM change_baseline")["baseline_date"].iloc[0]
st.caption(
    "Bill facts come from Congress.gov. Relevance and rationale come from a model classifier, whose "
    "accuracy is on the Methods page. Check the linked primary source before relying on any item."
)

alerts_tab, digest_tab, explorer_tab, regulatory_tab = st.tabs(
    ["Alerts", "Digest", "Bill explorer", "Regulatory documents"]
)

with alerts_tab:
    st.markdown(
        f"**Tracked bills with official activity after {baseline.strftime('%B')} "
        f"{baseline.day}, {baseline.year}**, ranked by relevance. Changes are read from dated "
        "official records, so this baseline is reconstructed from those dates and is not an "
        "earlier saved copy of the data."
    )
    chosen = st.selectbox("Pillar", list(names), format_func=names.get, key="alert_pillar")
    alerts = query(
        """
        SELECT label AS Bill, title AS Title, relevance AS Relevance, stage AS Stage,
            change_types AS Changes, latest_change AS "Latest change", latest_detail AS Detail,
            congress_gov_url AS Source
        FROM alerts WHERE pillar = ? ORDER BY pillar_rank
        """,
        [chosen],
    )
    alerts["Stage"] = alerts["Stage"].map(stage_label)
    if alerts.empty:
        st.write("No tracked bill in this pillar changed in this period.")
    else:
        st.write(f"{len(alerts)} bills")
        st.dataframe(
            alerts,
            hide_index=True,
            use_container_width=True,
            column_config={"Source": st.column_config.LinkColumn(display_text="Congress.gov")},
        )

with digest_tab:
    st.markdown(build_digest(connect_snapshot(ROOT / "data" / "snapshot")))

with explorer_tab:
    pillar_col, chamber_col, stage_col, party_col = st.columns(4)
    pillar_filter = pillar_col.multiselect("Pillar", list(names), format_func=names.get)
    chamber_filter = chamber_col.multiselect("Origin chamber", ["House", "Senate"])
    stage_rows = query("SELECT DISTINCT stage, stage_rank FROM bill_stage ORDER BY stage_rank DESC")
    stage_filter = stage_col.multiselect(
        "Stage", stage_rows["stage"].tolist(), format_func=stage_label
    )
    party_rows = query("SELECT DISTINCT party FROM members WHERE party IS NOT NULL ORDER BY 1")
    party_filter = party_col.multiselect("Sponsor party", party_rows["party"].tolist())

    bills = query(
        """
        SELECT b.bill_id, b.label AS Bill, b.title AS Title, b.origin_chamber AS Chamber,
            s.stage AS stage, m.party AS "Sponsor party", m.name AS Sponsor,
            b.latest_action_date AS "Latest action", b.congress_gov_url AS Source,
            string_agg(p.pillar, ',') AS pillar_keys, max(p.relevance) AS Relevance
        FROM bill_pillars AS p
        JOIN bills AS b USING (bill_id)
        JOIN bill_stage AS s USING (bill_id)
        LEFT JOIN members AS m ON b.sponsor_bioguide = m.bioguide_id
        WHERE p.is_relevant
        GROUP BY ALL
        ORDER BY Relevance DESC, s.stage DESC, b.latest_action_date DESC
        """
    )
    if pillar_filter:
        bills = bills[
            bills["pillar_keys"].apply(lambda v: bool(set(v.split(",")) & set(pillar_filter)))
        ]
    if chamber_filter:
        bills = bills[bills["Chamber"].isin(chamber_filter)]
    if stage_filter:
        bills = bills[bills["stage"].isin(stage_filter)]
    if party_filter:
        bills = bills[bills["Sponsor party"].isin(party_filter)]
    bills["Pillars"] = bills["pillar_keys"].apply(
        lambda v: "; ".join(names[key] for key in sorted(v.split(",")))
    )
    bills["Stage"] = bills["stage"].map(stage_label)
    st.write(f"{len(bills)} bills")
    st.dataframe(
        bills[
            [
                "Bill",
                "Title",
                "Pillars",
                "Stage",
                "Chamber",
                "Sponsor",
                "Sponsor party",
                "Latest action",
                "Source",
            ]
        ],
        hide_index=True,
        use_container_width=True,
        column_config={"Source": st.column_config.LinkColumn(display_text="Congress.gov")},
    )

    labels = {row["bill_id"]: f"{row['Bill']}: {row['Title']}" for _, row in bills.iterrows()}
    if labels:
        picked = st.selectbox("See the evidence for a bill", list(labels), format_func=labels.get)
        for _, row in query(
            "SELECT * FROM bill_pillars WHERE bill_id = ? AND relevance > 0 ORDER BY relevance DESC",
            [picked],
        ).iterrows():
            st.markdown(
                f"**{names[row['pillar']]}** (relevance {row['relevance']} of 3): {row['rationale']}"
            )
        lenses = query("SELECT * FROM bill_lenses WHERE bill_id = ? AND applies", [picked])
        if not lenses.empty:
            st.markdown("**Cross-cutting lenses**")
            for _, row in lenses.iterrows():
                st.markdown(f"- *{row['lens'].title()}:* {row['rationale']}")
        questions = query(
            "SELECT question FROM bill_questions WHERE bill_id = ? ORDER BY question_index",
            [picked],
        )
        if not questions.empty:
            st.markdown("**Questions for the policy team**")
            for question in questions["question"]:
                st.markdown(f"- {question}")
        evidence = query(
            """
            SELECT item AS "Supports", source_field AS "Source field", quote AS Quote,
                CASE WHEN verified THEN 'Found in source' ELSE 'NOT found in source' END
                    AS "Quote check"
            FROM bill_evidence WHERE bill_id = ?
            """,
            [picked],
        )
        with st.expander(f"Source quotes ({len(evidence)})"):
            st.dataframe(evidence, hide_index=True, use_container_width=True)

with regulatory_tab:
    st.markdown(
        "Federal Register documents that match pillar search terms. These are **keyword-matched and not "
        "classified**, so many will be only loosely related, and precision was not measured."
    )
    chosen = st.selectbox("Pillar", list(names), format_func=names.get, key="reg_pillar")
    documents = query(
        """
        SELECT publication_date AS Published, title AS Title, document_type AS Type,
            agencies AS Agencies, matched_terms AS "Matched terms", url AS Source
        FROM regulatory_documents WHERE pillar = ? ORDER BY publication_date DESC
        """,
        [chosen],
    )
    st.write(f"{len(documents)} documents since January 2025")
    st.dataframe(
        documents,
        hide_index=True,
        use_container_width=True,
        column_config={"Source": st.column_config.LinkColumn(display_text="FederalRegister.gov")},
    )
footer()
