"""Assemble the source document for each bill, from saved raw data only.

Run: python -m pei.classify.documents   (fetches the newest published text of each saved bill)
"""

from __future__ import annotations

import html
import json
import re

from pei.config import CONGRESS, RAW_DIR
from pei.ingest.congress import latest_text_url, strip_markup
from pei.ingest.http import Client, read_payload

TEXT_LIMIT = 24_000


def bill_files(congress: int = CONGRESS):
    return sorted((RAW_DIR / "congress" / str(congress) / "bills").glob("*.json"))


def fetch_texts(congress: int = CONGRESS) -> dict:
    """Save each bill's newest formatted text. Bills with no published text are counted."""
    client = Client(min_interval=0.4)
    folder = RAW_DIR / "congress" / str(congress) / "text"
    folder.mkdir(parents=True, exist_ok=True)
    fetched = missing = 0
    for path in bill_files(congress):
        url = latest_text_url(read_payload(path).get("text") or [])
        target = folder / f"{path.stem}.txt"
        if url is None:
            missing += 1
            continue
        if target.exists():
            continue
        target.write_text(clean_text(client.get(url).text), encoding="utf-8")
        fetched += 1
    return {"fetched": fetched, "no_published_text": missing}


def clean_text(raw: str) -> str:
    body = re.sub(r"(?is)<(script|style).*?</\1>", " ", raw)
    return html.unescape(strip_markup(body))


def latest_summary(payload: dict) -> str | None:
    summaries = payload.get("summaries") or []
    if not summaries:
        return None
    newest = max(summaries, key=lambda item: item.get("updateDate") or "")
    return html.unescape(strip_markup(newest.get("text") or "")) or None


def build_document(path, congress: int = CONGRESS) -> dict:
    """Return the fields the classifier sees. Truncation is recorded, never silent."""
    payload = read_payload(path)
    bill = payload["bill"]
    text_path = RAW_DIR / "congress" / str(congress) / "text" / f"{path.stem}.txt"
    text = text_path.read_text(encoding="utf-8") if text_path.exists() else None
    truncated = bool(text and len(text) > TEXT_LIMIT)
    return {
        "bill_id": path.stem,
        "title": bill.get("title"),
        "policy_area": (bill.get("policyArea") or {}).get("name"),
        "crs_summary": latest_summary(payload),
        "latest_action": (bill.get("latestAction") or {}).get("text"),
        "bill_text": text[:TEXT_LIMIT] if text else None,
        "bill_text_truncated": truncated,
        "bill_text_chars": len(text) if text else 0,
    }


def render_for_model(document: dict) -> str:
    """Serialize the fields as data. Key order is fixed so the content hash is stable."""
    fields = {
        "title": document["title"],
        "policy_area": document["policy_area"],
        "crs_summary": document["crs_summary"],
        "latest_action": document["latest_action"],
        "bill_text": document["bill_text"],
        "bill_text_truncated": document["bill_text_truncated"],
    }
    return f"<bill>\n{json.dumps(fields, ensure_ascii=False, indent=1)}\n</bill>"


if __name__ == "__main__":
    print(fetch_texts())
