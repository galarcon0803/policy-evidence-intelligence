"""Build the DuckDB analytical store from raw files, and export the demo snapshot.

Run: python -m pei.transform.build [--snapshot] [--baseline YYYY-MM-DD]
"""

from __future__ import annotations

import argparse
import json
import zipfile
from datetime import date, timedelta
from pathlib import Path

import duckdb
import pandas as pd

from pei.config import CONFIG_DIR, CONGRESS, DB_PATH, RAW_DIR, SNAPSHOT_DIR
from pei.ingest.candidates import build_matcher, is_candidate
from pei.ingest.http import read_payload
from pei.ingest.public_files import AEI_RELEASE
from pei.ingest.votes import CAST_CODES, classify_vote_question

SQL_DIR = Path(__file__).parent / "sql"

# Committed for the demo. Senate rows are limited to tracked bills by the joins in the SQL models.
SNAPSHOT_TABLES = (
    "bills",
    "actions",
    "recorded_vote_refs",
    "text_versions",
    "latest_summaries",
    "bill_committees",
    "bill_stage",
    "members",
    "committee_assignments",
    "member_evidence",
    "state_year_panel",
    "atlas_state",
    "epoch_us_sites",
    "aei_state",
    "aei_job_exposure",
    "bill_changes",
    "change_baseline",
    "source_freshness",
)


def _load_bills(con: duckdb.DuckDBPyConnection, congress: int) -> int:
    root = RAW_DIR / "congress" / str(congress)
    rejected = {}
    rejected_path = root / "rejected_sample.json"
    if rejected_path.exists():
        for bill in read_payload(rejected_path):
            rejected[f"{congress}-{bill['type'].lower()}-{bill['number']}"] = bill["stratum"]
    matcher = build_matcher()
    rows = []
    for path in sorted((root / "bills").glob("*.json")):
        envelope = json.loads(path.read_text(encoding="utf-8"))
        doc = envelope["payload"]
        rows.append(
            {
                "bill_id": path.stem,
                "doc": json.dumps(doc),
                "fetched_at": envelope["fetched_at"],
                "is_candidate": is_candidate(doc["bill"].get("title", ""), matcher),
                "sample_stratum": rejected.get(path.stem),
            }
        )
    frame = pd.DataFrame(rows)  # noqa: F841 - read by DuckDB's replacement scan
    con.execute(
        "CREATE OR REPLACE TABLE raw_bills AS "
        "SELECT bill_id, doc::JSON AS doc, fetched_at, is_candidate, sample_stratum FROM frame"
    )
    return len(rows)


CHAMBER_NAMES = {"House of Representatives": "House", "Senate": "Senate"}


def _load_members(con: duckdb.DuckDBPyConnection, congress: int) -> None:
    members = read_payload(RAW_DIR / "congress" / str(congress) / "members.json")
    rows = []
    for member in members:
        terms = member.get("terms", {}).get("item", [])
        chamber = CHAMBER_NAMES.get(terms[-1].get("chamber")) if terms else None
        rows.append(
            {
                "bioguide_id": member["bioguideId"],
                "name": member["name"],
                "party": member.get("partyName"),
                "state": member.get("state"),
                "chamber": chamber,
            }
        )
    frame = pd.DataFrame(rows)  # noqa: F841
    con.execute("CREATE OR REPLACE TABLE raw_members AS SELECT * FROM frame")


def _load_committees(con: duckdb.DuckDBPyConnection) -> None:
    root = RAW_DIR / "legislators"
    names = {}
    for committee in read_payload(root / "committees-current.json"):
        names[committee["thomas_id"]] = committee["name"]
        for sub in committee.get("subcommittees", []):
            names[committee["thomas_id"] + sub["thomas_id"]] = f"{committee['name']}: {sub['name']}"
    rows = []
    for code, roster in read_payload(root / "committee-membership-current.json").items():
        for seat in roster:
            rows.append(
                {
                    "bioguide": seat.get("bioguide"),
                    "committee_code": code,
                    "committee_name": names.get(code, code),
                    "title": seat.get("title"),
                }
            )
    frame = pd.DataFrame(rows)  # noqa: F841
    con.execute("CREATE OR REPLACE TABLE raw_committee_membership AS SELECT * FROM frame")


COLUMNS = ["congress", "session", "roll", "bioguide_id", "cast_vote", "vote_question"]


def _load_votes(con: duckdb.DuckDBPyConnection, congress: int) -> None:
    rows = []
    session_numbers = {"1st": 1, "2nd": 2}
    for path in sorted((RAW_DIR / "votes" / "house").glob("*.json")):
        vote = read_payload(path)
        for member in vote["members"]:
            rows.append(
                {
                    "congress": vote["congress"],
                    "session": session_numbers.get(vote["session"]),
                    "roll": vote["roll"],
                    "bioguide_id": member["bioguide_id"],
                    "cast_vote": member["vote"],
                    "vote_question": vote["vote_question"],
                    "evidence_type": classify_vote_question(vote["vote_question"]),
                }
            )
    house = pd.DataFrame(rows, columns=[*COLUMNS, "evidence_type"])  # noqa: F841
    con.execute("CREATE OR REPLACE TABLE raw_house_votes AS SELECT * FROM house")

    root = RAW_DIR / "votes" / "voteview"
    rolls = pd.read_csv(root / f"S{congress}_rollcalls.csv", low_memory=False)
    casts = pd.read_csv(root / f"S{congress}_votes.csv", low_memory=False)
    people = pd.read_csv(root / f"S{congress}_members.csv", low_memory=False)
    casts = casts[casts["chamber"] == "Senate"]
    merged = casts.merge(
        rolls[["rollnumber", "session", "clerk_rollnumber", "vote_question"]], on="rollnumber"
    ).merge(people.loc[people["chamber"] == "Senate", ["icpsr", "bioguide_id"]], on="icpsr")
    senate = pd.DataFrame(  # noqa: F841
        {
            "congress": congress,
            "session": merged["session"],
            "roll": merged["clerk_rollnumber"],
            "bioguide_id": merged["bioguide_id"],
            "cast_vote": merged["cast_code"].map(CAST_CODES),
            "vote_question": merged["vote_question"],
            "evidence_type": merged["vote_question"].map(classify_vote_question),
        }
    )
    con.execute("CREATE OR REPLACE TABLE raw_senate_votes AS SELECT * FROM senate")


def _load_public(con: duckdb.DuckDBPyConnection) -> None:
    for table, name in (
        ("raw_retail_annual", "retail_sales_annual.json"),
        ("raw_operational_annual", "operational_annual.json"),
    ):
        frame = pd.DataFrame(read_payload(RAW_DIR / "eia" / name))  # noqa: F841
        con.execute(f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM frame")

    atlas_files = sorted((RAW_DIR / "atlas").glob("*.csv"))
    atlas = pd.read_csv(atlas_files[-1], low_memory=False)  # noqa: F841
    con.execute("CREATE OR REPLACE TABLE raw_atlas AS SELECT * FROM atlas")

    with zipfile.ZipFile(RAW_DIR / "epoch" / "data_centers.zip") as archive:
        epoch = pd.read_csv(archive.open("data_centers.csv"))  # noqa: F841
    con.execute("CREATE OR REPLACE TABLE raw_epoch AS SELECT * FROM epoch")

    aei = pd.read_csv(RAW_DIR / "aei" / f"us_overall_{AEI_RELEASE}.csv")  # noqa: F841
    con.execute("CREATE OR REPLACE TABLE raw_aei AS SELECT * FROM aei")
    jobs = pd.read_csv(RAW_DIR / "aei" / "job_exposure.csv")  # noqa: F841
    con.execute("CREATE OR REPLACE TABLE raw_job_exposure AS SELECT * FROM jobs")

    states = pd.read_csv(CONFIG_DIR / "states.csv")  # noqa: F841
    con.execute("CREATE OR REPLACE TABLE ref_states AS SELECT * FROM states")


FRESHNESS_SQL = """
CREATE OR REPLACE TABLE source_freshness AS
SELECT 'Congress.gov bills' AS source, 'primary' AS tier,
    max(official_update_at)::DATE AS latest_official_date, max(fetched_at)::DATE AS fetched_on,
    count(*)::BIGINT AS records FROM bills
UNION ALL
SELECT 'House Clerk roll calls', 'primary', max(vote_date), NULL, count(*)::BIGINT
    FROM recorded_vote_refs WHERE chamber = 'House'
UNION ALL
SELECT 'Senate roll calls (Voteview)', 'secondary', max(vote_date), NULL, count(*)::BIGINT
    FROM recorded_vote_refs WHERE chamber = 'Senate'
UNION ALL
SELECT 'EIA retail sales', 'primary', make_date(max(year), 12, 31), NULL, count(*)::BIGINT
    FROM state_year_panel
UNION ALL
SELECT 'Anthropic Economic Index', 'public release', max(period_end), NULL, count(*)::BIGINT
    FROM aei_state
"""


def run_sql_models(con: duckdb.DuckDBPyConnection) -> None:
    for path in sorted(SQL_DIR.glob("*.sql")):
        con.execute(path.read_text(encoding="utf-8"))


def set_baseline(con: duckdb.DuckDBPyConnection, baseline: date) -> None:
    con.execute(
        "CREATE OR REPLACE TABLE change_baseline AS SELECT ?::DATE AS baseline_date", [baseline]
    )


def build(baseline: date | None = None, congress: int = CONGRESS) -> duckdb.DuckDBPyConnection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH))
    _load_bills(con, congress)
    _load_members(con, congress)
    _load_committees(con)
    _load_votes(con, congress)
    _load_public(con)
    set_baseline(con, baseline or date.today() - timedelta(days=14))
    run_sql_models(con)
    con.execute(FRESHNESS_SQL)
    return con


ENERGY_TABLES = (
    "state_year_panel",
    "atlas_state",
    "epoch_us_sites",
    "aei_state",
    "aei_job_exposure",
)


def build_energy() -> duckdb.DuckDBPyConnection:
    """Build only public energy and usage tables, which need no Congress data."""
    con = duckdb.connect(":memory:")
    _load_public(con)
    con.execute((SQL_DIR / "03_energy_panel.sql").read_text(encoding="utf-8"))
    return con


def export_snapshot(con: duckdb.DuckDBPyConnection, tables=SNAPSHOT_TABLES) -> None:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    for table in tables:
        target = (SNAPSHOT_DIR / f"{table}.parquet").as_posix()
        con.execute(f"COPY {table} TO '{target}' (FORMAT PARQUET, COMPRESSION ZSTD)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", action="store_true")
    parser.add_argument("--baseline", type=date.fromisoformat)
    parser.add_argument("--energy-only", action="store_true")
    args = parser.parse_args()
    if args.energy_only:
        export_snapshot(build_energy(), ENERGY_TABLES)
        raise SystemExit(0)
    connection = build(args.baseline)
    if args.snapshot:
        export_snapshot(connection)
    for name in ("bills", "actions", "member_evidence", "state_year_panel", "bill_changes"):
        print(name, connection.execute(f"SELECT count(*) FROM {name}").fetchone()[0])
