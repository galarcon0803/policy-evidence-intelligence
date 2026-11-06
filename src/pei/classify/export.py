"""Turn cached classifications into tables, using only records that pass validation."""

from __future__ import annotations

import json

import duckdb
import pandas as pd

from pei.classify.documents import render_for_model
from pei.classify.run import cache_path, candidate_documents, content_hash, load_prompt
from pei.classify.schemas import RELEVANT_AT

COLUMNS = {
    "pillars": ["bill_id", "pillar", "relevance", "is_relevant", "rationale"],
    "lenses": ["bill_id", "lens", "applies", "rationale"],
    "questions": ["bill_id", "question_index", "question"],
    "evidence": ["bill_id", "item", "source_field", "quote", "verified"],
    "runs": [
        "bill_id",
        "status",
        "model_served",
        "prompt_version",
        "effort",
        "classified_at",
        "input_tokens",
        "output_tokens",
        "quote_count",
        "quote_failures",
        "bill_text_truncated",
        "has_bill_text",
        "has_summary",
    ],
}


def flatten(record: dict, document: dict) -> dict[str, list[dict]]:
    """Flatten one cached record. Quote failures are carried along so they can be shown."""
    bill_id = record["bill_id"]
    failed = {(f["where"], f["quote"]) for f in record.get("quote_failures", [])}
    rows: dict[str, list[dict]] = {key: [] for key in COLUMNS}
    rows["runs"].append(
        {
            "bill_id": bill_id,
            "status": record["status"],
            "model_served": record["model_served"],
            "prompt_version": record["prompt_version"],
            "effort": record["effort"],
            "classified_at": record["classified_at"],
            "input_tokens": record["usage"]["input_tokens"],
            "output_tokens": record["usage"]["output_tokens"],
            "quote_count": record.get("quote_count", 0),
            "quote_failures": len(failed),
            "bill_text_truncated": document["bill_text_truncated"],
            "has_bill_text": bool(document["bill_text"]),
            "has_summary": bool(document["crs_summary"]),
        }
    )
    result = record.get("result")
    if not result:
        return rows

    def add_evidence(item: str, proofs: list[dict]) -> None:
        for proof in proofs:
            rows["evidence"].append(
                {
                    "bill_id": bill_id,
                    "item": item,
                    "source_field": proof["source_field"],
                    "quote": proof["quote"],
                    "verified": (item, proof["quote"]) not in failed,
                }
            )

    for item in result["pillars"]:
        rows["pillars"].append(
            {
                "bill_id": bill_id,
                "pillar": item["pillar"],
                "relevance": item["relevance"],
                "is_relevant": item["relevance"] >= RELEVANT_AT,
                "rationale": item["rationale"],
            }
        )
        add_evidence(f"pillar:{item['pillar']}", item["evidence"])
    for lens in ("safety", "equity", "governance"):
        rows["lenses"].append(
            {
                "bill_id": bill_id,
                "lens": lens,
                "applies": result[lens]["applies"],
                "rationale": result[lens]["rationale"],
            }
        )
        add_evidence(f"lens:{lens}", result[lens]["evidence"])
    for index, question in enumerate(result["questions"]):
        rows["questions"].append(
            {"bill_id": bill_id, "question_index": index, "question": question["question"]}
        )
        add_evidence(f"question:{index}", question["evidence"])
    return rows


def load_classifications(con: duckdb.DuckDBPyConnection) -> int:
    prompt = load_prompt()
    tables: dict[str, list[dict]] = {key: [] for key in COLUMNS}
    for document in candidate_documents():
        path = cache_path(content_hash(render_for_model(document), prompt))
        if not path.exists():
            continue
        record = json.loads(path.read_text(encoding="utf-8"))
        for key, rows in flatten(record, document).items():
            tables[key].extend(rows)
    for key, rows in tables.items():
        frame = pd.DataFrame(rows, columns=COLUMNS[key])  # noqa: F841
        name = "classifier_runs" if key == "runs" else f"bill_{key}"
        con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM frame")
    return len(tables["runs"])
