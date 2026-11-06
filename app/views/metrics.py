import plotly.graph_objects as go
import streamlit as st
from common import (
    CONTEXT,
    HIGHLIGHT,
    INK_2,
    SURFACE,
    footer,
    query,
    registry,
    show_chart,
    stage_label,
    style,
)

st.title("Metrics registry")
st.markdown(
    "Each metric has one governed definition. It lists what the number should inform, how it can be "
    "misread, and what it does not show."
)

metrics = {m["id"]: m for m in registry()}
computable = [i for i, m in metrics.items() if m["status"] == "computable"]
internal = [i for i, m in metrics.items() if m["status"] == "requires_internal"]
chosen = st.selectbox(
    "Metric",
    computable + internal,
    format_func=lambda i: (
        metrics[i]["name"] + (" (proposed, requires internal data)" if i in internal else "")
    ),
)
metric = metrics[chosen]
source_text = "; ".join(s["name"] for s in metric["sources"])

st.header(metric["name"])
st.markdown(metric["definition"])
info = st.columns(4)
info[0].markdown(f"**Unit**  \n{metric['unit']}")
info[1].markdown(f"**Geography**  \n{metric['geography']}")
info[2].markdown(f"**Refresh**  \n{metric['refresh_cadence']}")
info[3].markdown(f"**Version**  \n{metric['version']}")


def state_lines(rows, unit: str) -> None:
    """Every state in gray for context, with the selected states highlighted and labeled."""
    states = sorted(rows["state"].unique())
    defaults = [s for s in ("VA", "TX", "CA") if s in states]
    selected = st.multiselect("Highlight states", states, default=defaults)
    latest_year = int(rows["year"].max())
    latest = rows[rows["year"] == latest_year].sort_values("value")
    fig = go.Figure()
    for state in states:
        group = rows[rows["state"] == state].sort_values("year")
        if state not in selected:
            fig.add_trace(
                go.Scatter(
                    x=group["year"],
                    y=group["value"],
                    mode="lines",
                    line={"color": CONTEXT, "width": 1},
                    opacity=0.6,
                    hovertemplate=f"{state} %{{x}}: %{{y:.2f}}<extra></extra>",
                )
            )
    for state in selected:
        group = rows[rows["state"] == state].sort_values("year")
        fig.add_trace(
            go.Scatter(
                x=group["year"],
                y=group["value"],
                mode="lines",
                line={"color": HIGHLIGHT, "width": 2},
                hovertemplate=f"{state} %{{x}}: %{{y:.2f}}<extra></extra>",
            )
        )
        end = group.iloc[-1]
        fig.add_annotation(
            x=end["year"],
            y=end["value"],
            text=state,
            showarrow=False,
            xanchor="left",
            xshift=6,
            font={"color": INK_2, "size": 12},
        )
    show_chart(style(fig, 420, y_title=unit), source_text)
    if selected:
        columns = st.columns(min(len(selected), 4))
        for column, state in zip(columns, selected[:4], strict=False):
            value = latest.loc[latest["state"] == state, "value"]
            if not value.empty:
                column.metric(f"{state}, {latest_year}", f"{value.iloc[0]:.2f}")
    with st.expander("Table"):
        st.dataframe(
            rows.pivot(index="state", columns="year", values="value").round(2),
            use_container_width=True,
        )


def ranked_bars(rows, label: str, value: str, top: int, unit: str, title: str) -> None:
    top_rows = rows.sort_values(value, ascending=False).head(top).iloc[::-1]
    fig = go.Figure(
        go.Bar(
            x=top_rows[value],
            y=top_rows[label],
            orientation="h",
            marker={"color": HIGHLIGHT, "line": {"color": SURFACE, "width": 2}},
            text=top_rows[value].round(2),
            textposition="outside",
            cliponaxis=False,
            hovertemplate="%{y}: %{x:.2f}<extra></extra>",
        )
    )
    fig = style(fig, 60 + 26 * len(top_rows), x_title=unit)
    fig.update_yaxes(showgrid=False, tickfont={"color": INK_2}, automargin=True, type="category")
    st.subheader(title)
    show_chart(fig, source_text)
    with st.expander("Table"):
        st.dataframe(
            rows.sort_values(value, ascending=False), hide_index=True, use_container_width=True
        )


if metric["status"] == "requires_internal":
    st.warning(
        "**Requires Anthropic internal data.** This prototype has no such data, so no value exists or "
        "is shown. Only the proposed schema is listed."
    )
    st.subheader("Proposed schema")
    st.table(metric["schema"])
    if metric.get("paired_with"):
        partner = metrics[metric["paired_with"]]
        st.markdown(
            f"**Always reported with:** {partner['name']}. Efficiency per workload can improve while "
            "total consumption rises. Reported alone, an efficiency number can imply a shrinking "
            "footprint even as demand on the grid grows, so the two are defined as a pair."
        )
else:
    rows = query(metric["sql"])
    if {"state", "year"} <= set(rows.columns):
        state_lines(rows, metric["unit"])
    elif chosen == "tracked_bills_by_pillar_stage":
        rows["stage"] = rows["stage"].map(stage_label)
        st.subheader("Current value")
        st.dataframe(rows, hide_index=True, use_container_width=True)
        st.caption(f"Source: {source_text}")
    elif "period_start" in rows.columns:
        period = rows["period_start"].max()
        latest = rows[rows["period_start"] == period]
        ranked_bars(
            latest,
            "state",
            "value",
            15,
            metric["unit"],
            f"Top 15 states, period from {period:%Y-%m-%d}",
        )
    elif "occ_code" in rows.columns:
        ranked_bars(rows, "title", "value", 15, metric["unit"], "Top 15 occupations")
    else:
        ranked_bars(rows, "state", "value", 15, metric["unit"], "Top 15 states")

    with st.expander("Canonical SQL"):
        st.code(metric["sql"], language="sql")

st.subheader("Reading this metric")
reading = st.columns(3)
reading[0].markdown(f"**Use it to**  \n{metric['decision_use']}")
reading[1].markdown(f"**Likely misreading**  \n{metric['misread_risk']}")
reading[2].markdown(f"**It does not show**  \n{metric['does_not_show']}")

st.subheader("Provenance and limits")
for source in metric["sources"]:
    st.markdown(
        f"- [{source['name']}]({source['url']})"
        if source["url"].startswith("http")
        else f"- {source['name']}"
    )
st.markdown(f"**Limitations:** {metric['limitations']}")
st.markdown(f"**Uncertainty:** {metric['uncertainty']}")
st.markdown(f"**Owner:** {metric['owner']}")
st.markdown("**Version history**")
st.table(metric["version_history"])
st.caption("Registry source of truth: metrics/registry.yaml")
footer()
