import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from common import (
    HIGHLIGHT,
    INK_2,
    MUTED,
    ROOT,
    SURFACE,
    flagship_results,
    footer,
    forest,
    query,
    show_chart,
    stage_label,
    style,
    table_exists,
)

EIA = "EIA API v2, retail sales, 2001 to 2025. Computed in this project."
results = flagship_results()

st.title("Flagship study")
brief, charts, legislation, plan = st.tabs(
    ["Policy brief", "Charts", "Linked legislation", "Pre-analysis plan"]
)

with brief:
    text = (ROOT / "analysis" / "flagship_case_study.md").read_text(encoding="utf-8")
    text = text.replace(
        "[pre-analysis plan](pre_analysis_plan.md)", "pre-analysis plan (see its tab)"
    )
    st.markdown(text)

with charts:
    st.subheader("The baseline changes with the design")
    baseline = results["p1_twfe"]
    rows = [
        {
            "label": "Baseline (P1)",
            "coef": baseline["coef"],
            "ci_low": baseline["ci_low"],
            "ci_high": baseline["ci_high"],
        }
    ]
    names = {
        "Commercial-only exposure": "Commercial load only",
        "Division-by-year effects": "Division-by-year effects",
        "Baseline fuel mix x year": "Baseline fuel mix by year",
        "Time-varying generation shares (possible bad control)": "Generation shares (possible bad control)",
        "Residential-customer weights": "Customer-weighted",
        "Secondary outcome: average bill": "Average bill (partial years)",
    }
    for key, label in names.items():
        item = results["twfe_robustness"][key]
        rows.append(
            {
                "label": label,
                "coef": item["coef"],
                "ci_low": item["ci_low"],
                "ci_high": item["ci_high"],
            }
        )
    show_chart(
        forest(pd.DataFrame(rows), "Elasticity of residential price to prior-year load (95% CI)"),
        EIA,
    )

    st.subheader("Past load fades once future load is included")
    future = results["placebos"]["future_load"]
    past = results["placebos"]["lagged_load_with_future_control"]
    timing = pd.DataFrame(
        [
            {
                "label": "Load 1 year before",
                "coef": past["coef"],
                "ci_low": past["ci_low"],
                "ci_high": past["ci_high"],
            },
            {
                "label": "Load 3 years ahead (placebo)",
                "coef": future["coef"],
                "ci_low": future["ci_low"],
                "ci_high": future["ci_high"],
            },
        ]
    )
    show_chart(forest(timing, "Coefficient, both terms in one model (95% CI)"), EIA)
    st.markdown(
        "Future load cannot cause today's price. This pattern suggests the baseline reflects where load "
        "goes, or shared trends, though both intervals include zero."
    )

    st.subheader("Staggered design: event study")
    st.markdown(
        f"Based on only **{results['p2_staggered']['n_treated']} treated states**, and therefore "
        "uninformative. Later event years rest on fewer states. Shown for transparency."
    )
    events = pd.DataFrame(results["event_study"])
    fig = go.Figure()
    fig.add_vrect(
        x0=-3.5,
        x1=-0.5,
        fillcolor="#f0efec",
        line_width=0,
        annotation_text="Ramp",
        annotation_position="top left",
        annotation_font_color=MUTED,
    )
    fig.add_hline(y=0, line_color=MUTED, line_width=1)
    for _, row in events.iterrows():
        fig.add_trace(
            go.Scatter(
                x=[row["event"], row["event"]],
                y=[row["band_low"], row["band_high"]],
                mode="lines",
                line={"color": HIGHLIGHT, "width": 2},
                hoverinfo="skip",
            )
        )
    fig.add_trace(
        go.Scatter(
            x=events["event"],
            y=events["att"],
            mode="markers",
            marker={"color": HIGHLIGHT, "size": 9, "line": {"color": SURFACE, "width": 2}},
            customdata=events[["band_low", "band_high"]].to_numpy(),
            hovertemplate="Event year %{x}<br>%{y:.3f} (band %{customdata[0]:.3f} to "
            "%{customdata[1]:.3f})<extra></extra>",
        )
    )
    fig = style(
        fig, 380, y_title="ATT, log points (simultaneous 95% band)", x_title="Years from onset"
    )
    show_chart(fig, EIA)
    with st.expander("Table"):
        st.dataframe(events.round(4), hide_index=True, use_container_width=True)

    st.subheader("Exploratory: 2015 to 2025 load growth and price change")
    st.markdown("**Not pre-registered.** Added because the staggered design excludes Virginia.")
    states = pd.DataFrame(results["exploratory_long_difference"]["states"])
    fig = go.Figure(
        go.Scatter(
            x=states["ci_growth"],
            y=states["price_change"],
            mode="markers",
            text=states["state"],
            marker={"color": HIGHLIGHT, "size": 9, "line": {"color": SURFACE, "width": 2}},
            hovertemplate="%{text}<br>Load growth %{x:.3f}<br>Price change %{y:.3f}<extra></extra>",
        )
    )
    for _, row in states[states["state"].isin(["VA", "TX", "CA", "ND"])].iterrows():
        fig.add_annotation(
            x=row["ci_growth"],
            y=row["price_change"],
            text=row["state"],
            showarrow=False,
            yshift=12,
            font={"color": INK_2, "size": 12},
        )
    show_chart(
        style(
            fig, 420, y_title="Change in log residential price", x_title="Change in log C&I sales"
        ),
        EIA,
    )
    with st.expander("Table"):
        st.dataframe(states, hide_index=True, use_container_width=True)

with legislation:
    if not table_exists("bill_pillars"):
        st.info("Bill data is still being processed, so this list is not available yet.")
    else:
        st.markdown(
            "**Tracked bills tagged to Electricity & affordability**, so the evidence and the legislation "
            "sit side by side. Relevance comes from the classifier. Listing a bill makes no claim about its "
            "effects, and this study does not evaluate any of them."
        )
        bills = query(
            """
            SELECT b.label AS Bill, b.title AS Title, p.relevance AS Relevance, s.stage AS Stage,
                p.rationale AS "Why tracked", b.latest_action_date AS "Latest action",
                b.congress_gov_url AS Source
            FROM bill_pillars AS p
            JOIN bills AS b USING (bill_id)
            JOIN bill_stage AS s USING (bill_id)
            WHERE p.pillar = 'electricity_affordability' AND p.is_relevant
            ORDER BY p.relevance DESC, s.stage_rank DESC, b.latest_action_date DESC
            """
        )
        bills["Stage"] = bills["Stage"].map(stage_label)
        st.write(f"{len(bills)} bills")
        st.dataframe(
            bills,
            hide_index=True,
            use_container_width=True,
            column_config={"Source": st.column_config.LinkColumn(display_text="Congress.gov")},
        )


with plan:
    st.markdown((ROOT / "analysis" / "pre_analysis_plan.md").read_text(encoding="utf-8"))
footer()
