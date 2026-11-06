"""Keyless public files: Epoch AI data centers, Anthropic Economic Index, committee rosters.

Run: python -m pei.ingest.public_files
"""

from __future__ import annotations

import csv
import io

import httpx

from pei.config import USER_AGENT
from pei.ingest.http import Client, raw_path, write_json

EPOCH_URL = "https://epoch.ai/data/data_centers/data_centers.zip"
HF = "https://huggingface.co/datasets/Anthropic/EconomicIndex/resolve/main"
AEI_RELEASE = "release_2026_06_26"
AEI_FILE = "aei_claude_ai_2026-06-26.csv"
JOB_EXPOSURE = "labor_market_impacts/job_exposure.csv"
LEGISLATORS = "https://unitedstates.github.io/congress-legislators"


def fetch_epoch(client: Client) -> None:
    path = raw_path("epoch", "data_centers.zip")
    path.write_bytes(client.get(EPOCH_URL).content)


def fetch_job_exposure(client: Client) -> None:
    path = raw_path("aei", "job_exposure.csv")
    path.write_bytes(client.get(f"{HF}/{JOB_EXPOSURE}").content)


def keep_aei_row(row: dict) -> bool:
    """Keep overall metrics for the US and its states. Other cells are not used here."""
    if row["category_name"] != "overall":
        return False
    return row["geo_id"] == "USA" or row["geo_id"].startswith("US-")


def fetch_aei_us_overall() -> int:
    """Stream the 219 MB release and keep only US overall rows, so the raw store stays small."""
    url = f"{HF}/{AEI_RELEASE}/data/{AEI_FILE}"
    path = raw_path("aei", f"us_overall_{AEI_RELEASE}.csv")
    kept = 0
    headers = {"User-Agent": USER_AGENT}
    with (
        httpx.stream("GET", url, headers=headers, follow_redirects=True, timeout=300) as response,
        path.open("w", newline="", encoding="utf-8") as out,
    ):
        response.raise_for_status()
        reader = csv.DictReader(response.iter_lines())
        writer = csv.DictWriter(out, fieldnames=reader.fieldnames)
        writer.writeheader()
        for row in reader:
            if keep_aei_row(row):
                writer.writerow(row)
                kept += 1
    return kept


def fetch_legislators(client: Client) -> None:
    for name in ("committee-membership-current", "committees-current", "legislators-current"):
        url = f"{LEGISLATORS}/{name}.json"
        write_json(raw_path("legislators", f"{name}.json"), client.get_json(url), url)


def read_csv_bytes(content: bytes) -> list[dict]:
    return list(csv.DictReader(io.StringIO(content.decode("utf-8"))))


def run() -> dict:
    client = Client(min_interval=0.25)
    fetch_epoch(client)
    fetch_job_exposure(client)
    fetch_legislators(client)
    return {"aei_rows": fetch_aei_us_overall()}


if __name__ == "__main__":
    print(run())
