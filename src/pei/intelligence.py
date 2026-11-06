"""Generate the digest from tables. Pure formatting: no model call, and no number typed by hand.

Run: python -m pei.intelligence   (writes docs/digest_latest.md from the snapshot)
"""

from __future__ import annotations

import duckdb

from pei.config import ROOT, load_yaml
from pei.metrics.registry import connect_snapshot

STAGE_LABELS = {
    "became_law": "Became law",
    "vetoed": "Vetoed",
    "to_president": "Sent to the President",
    "passed_both": "Passed both chambers",
    "passed_one_chamber": "Passed one chamber",
    "reported_from_committee": "Committee: ordered reported or reported",
    "introduced": "Introduced",
}
PER_PILLAR = 8


def stage_label(stage: str) -> str:
    return STAGE_LABELS.get(stage, stage)


def build_digest(con: duckdb.DuckDBPyConnection, per_pillar: int = PER_PILLAR) -> str:
    pillars = load_yaml("pillars.yaml")["pillars"]
    baseline = con.execute("SELECT baseline_date FROM change_baseline").fetchone()[0]
    lines = [
        "# Policy intelligence digest",
        "",
        f"Changes in official records since {baseline}, organized by pillar. Relevance comes from a "
        "model classifier, evaluated on the Methods page, so check the linked primary source before "
        "relying on any item. This is not a forecast, and no item predicts how anyone will vote.",
        "",
        "*Independent prototype. Not affiliated with or endorsed by Anthropic.*",
        "",
    ]
    for key, pillar in pillars.items():
        total = con.execute("SELECT count(*) FROM alerts WHERE pillar = ?", [key]).fetchone()[0]
        lines += [f"## {pillar['name']}", ""]
        if not total:
            lines += ["No tracked bill in this pillar changed in this period.", ""]
        else:
            rows = con.execute(
                """
                SELECT label, title, congress_gov_url, stage, latest_change, latest_detail, rationale
                FROM alerts WHERE pillar = ? AND pillar_rank <= ? ORDER BY pillar_rank
                """,
                [key, per_pillar],
            ).fetchall()
            shown = f"Top {len(rows)} of {total}" if total > len(rows) else f"{total}"
            lines += [f"**{shown} changed bills, ranked by relevance.**", ""]
            for label, title, url, stage, changed, detail, rationale in rows:
                lines += [
                    f"- **[{label}]({url}): {title}**  ",
                    f"  {stage_label(stage)}. Latest ({changed}): {detail}  ",
                    f"  *Why tracked:* {rationale}",
                ]
            lines.append("")
        regulatory = con.execute(
            """
            SELECT title, agencies, publication_date, url
            FROM regulatory_documents
            WHERE pillar = ? AND publication_date > ?
            ORDER BY publication_date DESC, document_number LIMIT 5
            """,
            [key, baseline],
        ).fetchall()
        if regulatory:
            lines += ["**Regulatory documents (keyword-matched, not classified)**", ""]
            for title, agencies, published, url in regulatory:
                lines.append(f"- [{title}]({url}), {agencies}, {published}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


if __name__ == "__main__":
    target = ROOT / "docs" / "digest_latest.md"
    target.write_text(build_digest(connect_snapshot()), encoding="utf-8")
    print(target)
