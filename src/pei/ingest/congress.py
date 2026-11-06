"""Congress.gov API v3: list every bill, filter locally, then fetch detail for candidates.

Run: python -m pei.ingest.congress [--limit N]
"""

from __future__ import annotations

import argparse
import re
from datetime import UTC, datetime

from pei.config import CONGRESS, api_key
from pei.ingest.candidates import build_matcher, is_candidate
from pei.ingest.http import Client, raw_path, read_payload, write_json

BASE = "https://api.congress.gov/v3"
PAGE = 250
# The documented limit is 5,000 requests per hour.
MIN_INTERVAL = 0.75
SUBRESOURCES = ("actions", "cosponsors", "committees", "summaries", "text", "subjects")
PAYLOAD_KEY = {"text": "textVersions", "subjects": "subjects"}


def _params(**extra) -> dict:
    return {"api_key": api_key("CONGRESS_API_KEY"), "format": "json", **extra}


def fetch_bill_list(client: Client, congress: int = CONGRESS) -> list[dict]:
    """Fetch the full bill list. Saved pages resume a same-day run; a new day refreshes the list."""
    bills: list[dict] = []
    offset = 0
    today = datetime.now(UTC).date().isoformat()
    while True:
        path = raw_path("congress", str(congress), "list", today, f"bills_{offset:06d}.json")
        if path.exists():
            page = read_payload(path)
        else:
            url = f"{BASE}/bill/{congress}"
            page = client.get_json(url, _params(limit=PAGE, offset=offset, sort="updateDate asc"))
            write_json(path, page, url)
        batch = page.get("bills", [])
        bills.extend(batch)
        offset += PAGE
        if len(batch) < PAGE or offset >= page.get("pagination", {}).get("count", 0):
            return bills


def _paged(client: Client, url: str, key: str) -> list:
    """Collect a list sub-resource across pages."""
    items: list = []
    offset = 0
    while True:
        page = client.get_json(url, _params(limit=PAGE, offset=offset))
        batch = page.get(key, [])
        if isinstance(batch, dict):  # subjects nests its lists in an object
            return [batch]
        items.extend(batch)
        offset += PAGE
        if len(batch) < PAGE:
            return items


def bill_id(bill: dict, congress: int = CONGRESS) -> str:
    return f"{congress}-{bill['type'].lower()}-{bill['number']}"


def fetch_bill_detail(client: Client, bill: dict, congress: int = CONGRESS) -> None:
    """Fetch one bill with its sub-resources. Refetches only if the bill's update date moved."""
    identifier = bill_id(bill, congress)
    path = raw_path("congress", str(congress), "bills", f"{identifier}.json")
    if path.exists():
        saved = read_payload(path)
        if saved.get("list_update_date") == bill.get("updateDateIncludingText"):
            return
    root = f"{BASE}/bill/{congress}/{bill['type'].lower()}/{bill['number']}"
    payload = {
        "list_update_date": bill.get("updateDateIncludingText"),
        "bill": client.get_json(root, _params())["bill"],
    }
    for name in SUBRESOURCES:
        payload[name] = _paged(client, f"{root}/{name}", PAYLOAD_KEY.get(name, name))
    write_json(path, payload, root)


TEXT_FORMATS = ("Formatted Text", "Formatted XML")


def latest_text_url(text_versions: list[dict]) -> str | None:
    """Pick the newest version's formatted-text URL, if one has been published."""
    dated = [v for v in text_versions if v.get("date")]
    for version in sorted(dated, key=lambda v: v["date"], reverse=True):
        for wanted in TEXT_FORMATS:
            for fmt in version.get("formats", []):
                if fmt.get("type") == wanted:
                    return fmt["url"]
    return None


def strip_markup(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def fetch_members(client: Client, congress: int = CONGRESS) -> None:
    """Save every member who served in this Congress (party, state, chamber)."""
    path = raw_path("congress", str(congress), "members.json")
    url = f"{BASE}/member/congress/{congress}"
    members: list[dict] = []
    offset = 0
    while True:
        page = client.get_json(url, _params(limit=PAGE, offset=offset, currentMember="false"))
        batch = page.get("members", [])
        members.extend(batch)
        offset += PAGE
        if len(batch) < PAGE:
            break
    write_json(path, members, url)


def run(limit: int | None = None, congress: int = CONGRESS) -> dict:
    client = Client(min_interval=MIN_INTERVAL)
    bills = fetch_bill_list(client, congress)
    matcher = build_matcher()
    candidates = [b for b in bills if is_candidate(b.get("title", ""), matcher)]
    if limit:
        candidates = candidates[:limit]
    for number, bill in enumerate(candidates, 1):
        fetch_bill_detail(client, bill, congress)
        if number % 50 == 0:
            print(f"  {number}/{len(candidates)} bills")
    fetch_members(client, congress)
    return {"bills_listed": len(bills), "candidates": len(candidates)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="Fetch detail for only the first N candidates")
    print(run(parser.parse_args().limit))
