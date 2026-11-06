import plotly.graph_objects as go
import streamlit as st
from common import EVIDENCE_LABELS, HIGHLIGHT, footer, pillars, query, show_chart, style

st.title("Members: documented positions")
st.markdown(
    "**Documented actions only:** sponsorship, cosponsorship, and recorded votes on tracked bills. "
    "**Nothing here predicts how anyone will vote.** A cosponsorship or a vote on one bill is not a "
    "general position on an issue. Procedural votes often reflect party strategy, not support for the "
    "bill's content, so each evidence type is labeled."
)

names = pillars()
pillar_col, evidence_col, party_col, committee_col = st.columns(4)
chosen = pillar_col.selectbox("Pillar", list(names), format_func=names.get)

evidence = query(
    """
    SELECT e.bioguide_id, m.name AS Member, m.party AS Party, m.state AS State, m.chamber AS Chamber,
        b.label AS Bill, b.title AS Title, e.evidence_type, e.vote_cast AS "Vote cast",
        e.evidence_date AS Date, e.source_tier AS "Source tier", e.source_url AS Source
    FROM member_evidence AS e
    JOIN bill_pillars AS p USING (bill_id)
    JOIN bills AS b USING (bill_id)
    JOIN members AS m ON e.bioguide_id = m.bioguide_id
    WHERE p.pillar = ? AND p.is_relevant
    """,
    [chosen],
)
evidence["Evidence type"] = evidence["evidence_type"].map(EVIDENCE_LABELS)

types = sorted(evidence["Evidence type"].dropna().unique())
type_filter = evidence_col.multiselect("Evidence type", types)
party_filter = party_col.multiselect("Party", sorted(evidence["Party"].dropna().unique()))
committees = query(
    """
    SELECT DISTINCT committee_name, bioguide_id FROM committee_assignments
    WHERE committee_name NOT LIKE '%:%'
    """
)
committee_filter = committee_col.selectbox(
    "Committee (current rosters)",
    ["All", *sorted(committees["committee_name"].unique())],
)

shown = evidence
if type_filter:
    shown = shown[shown["Evidence type"].isin(type_filter)]
if party_filter:
    shown = shown[shown["Party"].isin(party_filter)]
if committee_filter != "All":
    roster = committees.loc[committees["committee_name"] == committee_filter, "bioguide_id"]
    shown = shown[shown["bioguide_id"].isin(roster)]

if shown.empty:
    st.write("No documented evidence matches these filters.")
else:
    left, right = st.columns(2)
    left.metric("Members with documented evidence", f"{shown['bioguide_id'].nunique():,}")
    right.metric("Evidence records", f"{len(shown):,}")

    st.subheader("Evidence records by type and party")
    counts = (
        shown.groupby(["Evidence type", "Party"])
        .size()
        .reset_index(name="Records")
        .sort_values(["Evidence type", "Records"], ascending=[True, False])
    )
    for evidence_type in counts["Evidence type"].unique():
        group = counts[counts["Evidence type"] == evidence_type].iloc[::-1]
        st.markdown(f"**{evidence_type}**")
        fig = go.Figure(
            go.Bar(
                x=group["Records"],
                y=group["Party"],
                orientation="h",
                marker={"color": HIGHLIGHT},
                text=group["Records"],
                textposition="outside",
                cliponaxis=False,
                hovertemplate="%{y}: %{x} records<extra></extra>",
            )
        )
        fig = style(fig, height=60 + 34 * len(group))
        fig.update_xaxes(visible=False)
        fig.update_yaxes(showgrid=False)
        show_chart(
            fig,
            "Congress.gov (sponsorship), House Clerk and Voteview (votes). Counts actions, not people: "
            "a member can appear once per bill.",
        )

    if {"Yea", "Nay"} & set(shown["Vote cast"].dropna()):
        st.subheader("How members voted, by evidence type")
        votes = (
            shown.dropna(subset=["Vote cast"])
            .pivot_table(
                index=["Evidence type", "Party"],
                columns="Vote cast",
                values="Member",
                aggfunc="count",
                fill_value=0,
            )
            .reset_index()
        )
        st.dataframe(votes, hide_index=True, use_container_width=True)
    else:
        st.write("No recorded votes on tracked bills match these filters.")

    st.subheader("All records")
    st.dataframe(
        shown[
            [
                "Member",
                "Party",
                "State",
                "Chamber",
                "Bill",
                "Title",
                "Evidence type",
                "Vote cast",
                "Date",
                "Source tier",
                "Source",
            ]
        ].sort_values(["Date"], ascending=False),
        hide_index=True,
        use_container_width=True,
        column_config={"Source": st.column_config.LinkColumn(display_text="Primary record")},
    )

st.caption(
    "Committee filter uses current rosters from the congress-legislators project, so former members "
    "have no committee. Senate vote casts come from Voteview, a secondary source, and links go to the "
    "official Senate record."
)
footer()
