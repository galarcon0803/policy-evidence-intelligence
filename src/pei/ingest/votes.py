"""Recorded votes tied to tracked bills.

House: Clerk roll call XML, the primary source.
Senate: senate.gov returns 403 to this client, and Congress.gov has no senate-vote endpoint
(404 as of 2026-11-06). This pipeline does not try to get around that block. Senate votes come
from Voteview (UCLA) instead, labeled as a secondary source with its own lag.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass

from pei.config import CONGRESS
from pei.ingest.http import Client, raw_path, read_payload, write_json


@dataclass(frozen=True)
class RollCall:
    chamber: str
    congress: int
    session: int
    roll: int
    url: str


def recorded_votes(actions: list[dict]) -> list[RollCall]:
    """Pull unique roll calls referenced by a bill's action history."""
    found: dict[tuple, RollCall] = {}
    for action in actions:
        for vote in action.get("recordedVotes") or []:
            item = RollCall(
                chamber=vote["chamber"],
                congress=int(vote["congress"]),
                session=int(vote["sessionNumber"]),
                roll=int(vote["rollNumber"]),
                url=vote["url"],
            )
            found[(item.chamber, item.congress, item.session, item.roll)] = item
    return list(found.values())


def parse_clerk_xml(xml_bytes: bytes) -> dict:
    """Parse a House Clerk roll call into metadata and one row per member."""
    root = ET.fromstring(xml_bytes)
    meta = root.find("vote-metadata")

    def text(tag: str) -> str | None:
        node = meta.find(tag)
        return node.text.strip() if node is not None and node.text else None

    members = []
    for row in root.findall("vote-data/recorded-vote"):
        legislator = row.find("legislator")
        members.append(
            {
                "bioguide_id": legislator.get("name-id"),
                "name": legislator.get("unaccented-name") or legislator.text,
                "party": legislator.get("party"),
                "state": legislator.get("state"),
                "vote": row.findtext("vote"),
            }
        )
    return {
        "congress": int(text("congress")),
        "session": text("session"),
        "roll": int(text("rollcall-num")),
        "legis_num": text("legis-num"),
        "vote_question": text("vote-question"),
        "vote_type": text("vote-type"),
        "vote_result": text("vote-result"),
        "action_date": text("action-date"),
        "vote_desc": text("vote-desc"),
        "members": members,
    }


def classify_vote_question(question: str | None) -> str:
    """Map an official vote question to an evidence type. Ambiguous stays 'unclassified'.

    Only wording that plainly means passage counts as final passage. A vote on a rule or a motion
    to recommit is procedural, and a vote on an amendment is reported as its own type.
    """
    q = (question or "").strip().lower()
    if not q:
        return "unclassified"
    if q.startswith(
        (
            "on passage",
            "on the bill",
            "on the joint resolution",
            "on the conference report",
            "on agreeing to the conference report",
        )
    ):
        return "final_passage_vote"
    if "suspend the rules and pass" in q or "suspend the rules and agree" in q:
        return "final_passage_vote"
    if "amendment" in q and not q.startswith("on motion"):
        return "amendment_vote"
    if q.startswith(("on cloture", "on the cloture")):
        return "procedural_vote"
    if q.startswith(("on motion", "on the motion", "on ordering the previous question")):
        return "procedural_vote"
    if "resolution" in q and "rule" in q:
        return "procedural_vote"
    return "unclassified"


VOTEVIEW = "https://voteview.com/static/data/out"
CAST_CODES = {
    1: "Yea",
    2: "Yea",
    3: "Yea",
    4: "Nay",
    5: "Nay",
    6: "Nay",
    7: "Present",
    8: "Present",
}
CAST_CODES[9] = "Not Voting"


def fetch_voteview_senate(client: Client, congress: int) -> None:
    """Save Voteview's Senate files. A secondary source: its site states no data license, so only
    rows tied to tracked bills are ever committed, credited, and labeled secondary."""
    for folder, suffix in (("rollcalls", "rollcalls"), ("votes", "votes"), ("members", "members")):
        name = f"S{congress}_{suffix}.csv"
        path = raw_path("votes", "voteview", name)
        path.write_bytes(client.get(f"{VOTEVIEW}/{folder}/{name}").content)


def fetch_house_roll(client: Client, vote: RollCall) -> dict | None:
    """Fetch and save a House roll call. Senate roll calls come from Voteview."""
    if vote.chamber != "House":
        return None
    path = raw_path("votes", "house", f"{vote.congress}_{vote.session}_{vote.roll:04d}.json")
    if not path.exists():
        response = client.get(vote.url)
        write_json(path, parse_clerk_xml(response.content), vote.url)
    return {"path": str(path)}


def fetch_tracked_votes(congress: int) -> dict:
    """Fetch every House roll call referenced by a saved bill, plus Voteview's Senate files."""
    client = Client(min_interval=0.25)
    bills = raw_path("congress", str(congress), "bills", "x").parent
    house = senate = 0
    for path in sorted(bills.glob("*.json")):
        for vote in recorded_votes(read_payload(path)["actions"]):
            if vote.chamber == "House":
                fetch_house_roll(client, vote)
                house += 1
            else:
                senate += 1
    fetch_voteview_senate(client, congress)
    return {"house_refs": house, "senate_refs": senate}


if __name__ == "__main__":
    print(fetch_tracked_votes(CONGRESS))
