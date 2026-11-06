"""Shared dashboard helpers. The app reads only the committed snapshot, so it needs no API keys."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pei.config import load_yaml  # noqa: E402
from pei.intelligence import stage_label  # noqa: E402, F401
from pei.metrics.registry import connect_snapshot, load_registry  # noqa: E402

# Validated default palette: one highlight series over recessive gray context.
HIGHLIGHT = "#2a78d6"
CONTEXT = "#c3c2b7"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
SURFACE = "#fcfcfb"
FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif'

DISCLAIMER = (
    "Independent proposal and prototype. Not affiliated with or endorsed by Anthropic. "
    "Uses no Anthropic internal data."
)
EVIDENCE_LABELS = {
    "sponsor": "Sponsor",
    "cosponsor": "Cosponsor",
    "final_passage_vote": "Final passage vote",
    "procedural_vote": "Procedural vote",
    "amendment_vote": "Amendment vote",
    "unclassified": "Vote (type unclassified)",
}


@st.cache_resource
def database() -> duckdb.DuckDBPyConnection:
    return connect_snapshot(ROOT / "data" / "snapshot")


def query(sql: str, params: list | None = None) -> pd.DataFrame:
    # DuckDB connections are not thread-safe. A cursor gives each Streamlit session its own.
    return database().cursor().execute(sql, params or []).df()


def table_exists(name: str) -> bool:
    return (ROOT / "data" / "snapshot" / f"{name}.parquet").exists()


@st.cache_data
def pillars() -> dict[str, str]:
    return {key: value["name"] for key, value in load_yaml("pillars.yaml")["pillars"].items()}


@st.cache_data
def registry() -> list[dict]:
    return load_registry(ROOT / "metrics" / "registry.yaml")


@st.cache_data
def flagship_results() -> dict:
    return json.loads((ROOT / "analysis" / "results" / "flagship.json").read_text("utf-8"))


def eval_results() -> dict | None:
    path = ROOT / "eval" / "results.json"
    return json.loads(path.read_text("utf-8")) if path.exists() else None


def style(fig: go.Figure, height: int = 400, y_title: str = "", x_title: str = "") -> go.Figure:
    """One recessive look for every chart: hairline grid, muted axes, no chart junk."""
    fig.update_layout(
        height=height,
        margin={"l": 8, "r": 28, "t": 12, "b": 8},
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        font={"family": FONT, "color": INK_2, "size": 13},
        showlegend=False,
        hoverlabel={"bgcolor": "white", "font": {"color": INK, "family": FONT}},
    )
    axis = {
        "gridcolor": GRID,
        "zerolinecolor": CONTEXT,
        "linecolor": CONTEXT,
        "tickfont": {"color": MUTED},
        "title_font": {"color": INK_2, "size": 12},
    }
    fig.update_xaxes(**axis, title_text=x_title)
    fig.update_yaxes(**axis, title_text=y_title)
    return fig


def show_chart(fig: go.Figure, source: str) -> None:
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    st.caption(f"Source: {source}")


def forest(rows: pd.DataFrame, x_title: str, height: int | None = None) -> go.Figure:
    """Point estimates with intervals. Expects label, coef, ci_low, ci_high."""
    rows = rows.iloc[::-1]
    fig = go.Figure()
    fig.add_vline(x=0, line_color=MUTED, line_width=1)
    for _, row in rows.iterrows():
        fig.add_trace(
            go.Scatter(
                x=[row["ci_low"], row["ci_high"]],
                y=[row["label"]] * 2,
                mode="lines",
                line={"color": HIGHLIGHT, "width": 2},
                hoverinfo="skip",
            )
        )
    fig.add_trace(
        go.Scatter(
            x=rows["coef"],
            y=rows["label"],
            mode="markers",
            marker={"color": HIGHLIGHT, "size": 10, "line": {"color": SURFACE, "width": 2}},
            customdata=rows[["ci_low", "ci_high"]].to_numpy(),
            hovertemplate="%{y}<br>%{x:.3f} (95%: %{customdata[0]:.3f} to %{customdata[1]:.3f})"
            "<extra></extra>",
        )
    )
    fig = style(fig, height or 70 + 44 * len(rows), x_title=x_title)
    fig.update_yaxes(automargin=True, tickfont={"color": INK_2})
    return fig


def footer() -> None:
    st.divider()
    st.caption(DISCLAIMER)
