from pathlib import Path

import pytest

from pei.ingest.candidates import is_candidate, match_title
from pei.ingest.congress import latest_text_url, strip_markup
from pei.ingest.http import read_payload, redact_url, write_json
from pei.ingest.public_files import keep_aei_row
from pei.ingest.votes import classify_vote_question, parse_clerk_xml, recorded_votes

CLERK_XML = b"""<?xml version="1.0"?>
<rollcall-vote><vote-metadata>
<congress>119</congress><session>1st</session><rollcall-num>14</rollcall-num>
<legis-num>H R 144</legis-num><vote-question>On Passage</vote-question>
<vote-type>YEA-AND-NAY</vote-type><vote-result>Passed</vote-result>
<action-date>15-Jan-2025</action-date><vote-desc>Example</vote-desc>
</vote-metadata><vote-data>
<recorded-vote><legislator name-id="A000001" party="D" state="TN" unaccented-name="Able">Able</legislator><vote>Yea</vote></recorded-vote>
<recorded-vote><legislator name-id="B000002" party="R" state="VA" unaccented-name="Baker">Baker</legislator><vote>Nay</vote></recorded-vote>
</vote-data></rollcall-vote>"""  # noqa: E501


def test_redact_url_removes_key_and_keeps_other_params():
    clean = redact_url("https://api.example.gov/x?api_key=SECRET&limit=5")
    assert "SECRET" not in clean
    assert "limit=5" in clean


def test_raw_store_never_writes_key(tmp_path: Path):
    path = tmp_path / "x.json"
    write_json(path, {"a": 1}, "https://api.example.gov/x?api_key=SECRET")
    assert "SECRET" not in path.read_text()
    assert read_payload(path) == {"a": 1}


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Data Center Transparency Act", True),
        ("Ratepayer Protection Act", True),
        ("AI Workforce Training Act", True),
        ("A bill to rename a post office", False),
        # Word boundaries: "grid" must not match "gridlock", and "AI" must not match "aid".
        ("Ending Gridlock Act", False),
        ("Foreign Aid Reform Act", False),
    ],
)
def test_candidate_filter(title, expected):
    assert is_candidate(title) is expected


def test_match_title_reports_pillars():
    result = match_title("Data Center Ratepayer Protection Act")
    assert "electricity_affordability" in result["keyword_pillars"]
    assert "data_centers_communities" in result["keyword_pillars"]


def test_recorded_votes_deduplicates():
    vote = {
        "chamber": "House",
        "congress": 119,
        "sessionNumber": 1,
        "rollNumber": 14,
        "url": "https://clerk.house.gov/evs/2025/roll014.xml",
    }
    actions = [{"recordedVotes": [vote]}, {"recordedVotes": [vote]}, {"text": "no vote"}]
    assert len(recorded_votes(actions)) == 1


def test_parse_clerk_xml():
    parsed = parse_clerk_xml(CLERK_XML)
    assert parsed["roll"] == 14
    assert parsed["vote_question"] == "On Passage"
    assert parsed["members"][0] == {
        "bioguide_id": "A000001",
        "name": "Able",
        "party": "D",
        "state": "TN",
        "vote": "Yea",
    }


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("On Passage", "final_passage_vote"),
        ("On Motion to Suspend the Rules and Pass", "final_passage_vote"),
        ("On Agreeing to the Conference Report", "final_passage_vote"),
        ("On Motion to Recommit", "procedural_vote"),
        ("On Ordering the Previous Question", "procedural_vote"),
        ("On Cloture on the Motion to Proceed", "procedural_vote"),
        ("On Agreeing to the Amendment", "amendment_vote"),
        ("Something New", "unclassified"),
        (None, "unclassified"),
    ],
)
def test_vote_evidence_type(question, expected):
    assert classify_vote_question(question) == expected


def test_latest_text_url_prefers_newest_formatted_text():
    versions = [
        {"date": "2025-01-03T05:00:00Z", "formats": [{"type": "Formatted Text", "url": "old"}]},
        {"date": None, "formats": [{"type": "Formatted Text", "url": "undated"}]},
        {"date": "2025-01-16T05:00:00Z", "formats": [{"type": "Formatted Text", "url": "new"}]},
    ]
    assert latest_text_url(versions) == "new"
    assert latest_text_url([]) is None


def test_strip_markup():
    assert strip_markup("<p><b>A</b>  bill</p>") == "A bill"


def test_aei_filter_keeps_only_us_overall():
    assert keep_aei_row({"category_name": "overall", "geo_id": "US-VA"})
    assert keep_aei_row({"category_name": "overall", "geo_id": "USA"})
    assert not keep_aei_row({"category_name": "overall", "geo_id": "GBR"})
    assert not keep_aei_row({"category_name": "onet", "geo_id": "US-VA"})


def test_rejected_sample_draws_both_strata_and_is_stable(tmp_path, monkeypatch):
    from pei.ingest import congress

    monkeypatch.setattr(
        congress, "raw_path", lambda *parts: tmp_path.joinpath(*parts[-1:]), raising=True
    )
    bills = [
        {"type": "HR", "number": str(i), "title": f"Rural Energy Thing {i}"} for i in range(30)
    ] + [{"type": "HR", "number": str(i + 100), "title": f"Post Office {i}"} for i in range(30)]
    sample = congress.rejected_sample(bills, None, each=5)
    assert {b["stratum"] for b in sample} == {"near_miss", "other"}
    assert sum(b["stratum"] == "near_miss" for b in sample) == 5
    assert congress.rejected_sample([], None, each=5) == sample
