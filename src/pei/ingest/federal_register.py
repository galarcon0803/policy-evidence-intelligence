"""Federal Register API: regulatory developments relevant to the pillars. No key needed.

Documents are keyword-matched, not classified, and the app labels them that way.
Run: python -m pei.ingest.federal_register
"""

from __future__ import annotations

import duckdb
import pandas as pd

from pei.config import RAW_DIR, load_yaml
from pei.ingest.http import Client, raw_path, read_payload, write_json

BASE = "https://www.federalregister.gov/api/v1/documents.json"
FIELDS = (
    "title",
    "type",
    "abstract",
    "document_number",
    "html_url",
    "publication_date",
    "agencies",
)
RAW_FILE = ("federal_register", "documents.json")
EARLIEST = "2025-01-03"


def is_routine(title: str | None) -> bool:
    """Drop routine docket filing notices, which match keywords but carry no policy content."""
    configured = load_yaml("federal_register.yaml")["exclude_title_contains"]
    lowered = (title or "").lower()
    return any(term.lower() in lowered for term in configured)


def fetch_documents(client: Client | None = None) -> int:
    client = client or Client(min_interval=0.5)
    config = load_yaml("federal_register.yaml")
    found: dict[str, dict] = {}
    for query in config["queries"]:
        params = [
            ("conditions[term]", f'"{query["term"]}"'),
            ("conditions[publication_date][gte]", EARLIEST),
            ("order", "newest"),
            ("per_page", 100),
        ]
        params += [("fields[]", field) for field in FIELDS]
        params += [("conditions[type][]", kind) for kind in config["document_types"]]
        for agency in query.get("agencies", []):
            params.append(("conditions[agencies][]", agency))
        payload = client.get_json(BASE, params)
        for item in payload.get("results", []):
            if is_routine(item.get("title")):
                continue
            entry = found.setdefault(item["document_number"], {**item, "pillars": [], "terms": []})
            if query["pillar"] not in entry["pillars"]:
                entry["pillars"].append(query["pillar"])
            entry["terms"].append(query["term"])
    write_json(raw_path(*RAW_FILE), list(found.values()), BASE)
    return len(found)


def to_rows(documents: list[dict]) -> pd.DataFrame:
    rows = []
    for item in documents:
        agencies = "; ".join(a.get("name", "") for a in item.get("agencies", []) if a.get("name"))
        for pillar in item["pillars"]:
            rows.append(
                {
                    "document_number": item["document_number"],
                    "pillar": pillar,
                    "title": item.get("title"),
                    "document_type": item.get("type"),
                    "abstract": item.get("abstract"),
                    "agencies": agencies,
                    "publication_date": item.get("publication_date"),
                    "url": item.get("html_url"),
                    "matched_terms": "; ".join(sorted(set(item["terms"]))),
                }
            )
    return pd.DataFrame(
        rows,
        columns=[
            "document_number",
            "pillar",
            "title",
            "document_type",
            "abstract",
            "agencies",
            "publication_date",
            "url",
            "matched_terms",
        ],
    )


def load_regulatory(con: duckdb.DuckDBPyConnection) -> None:
    path = RAW_DIR.joinpath(*RAW_FILE)
    frame = to_rows(read_payload(path) if path.exists() else [])  # noqa: F841
    con.execute(
        "CREATE OR REPLACE TABLE regulatory_documents AS "
        "SELECT * REPLACE (publication_date::DATE AS publication_date) FROM frame"
    )


if __name__ == "__main__":
    print(fetch_documents())
