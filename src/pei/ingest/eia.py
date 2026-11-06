"""EIA API v2: retail sales by state and sector, plus power-sector fuel cost and generation.

Run: python -m pei.ingest.eia
"""

from __future__ import annotations

from pei.config import api_key
from pei.ingest.http import Client, raw_path, write_json

BASE = "https://api.eia.gov/v2/electricity"
PAGE = 5000
FUELS = ("COW", "NGO", "NUC", "ALL", "AOR")
ELECTRIC_POWER_SECTOR = "98"


def _fetch_all(client: Client, route: str, params: dict) -> list[dict]:
    rows: list[dict] = []
    offset = 0
    while True:
        query = {
            "api_key": api_key("EIA_API_KEY"),
            "offset": offset,
            "length": PAGE,
            "sort[0][column]": "period",
            "sort[0][direction]": "asc",
            **params,
        }
        response = client.get_json(f"{BASE}/{route}/data/", query)["response"]
        batch = response["data"]
        rows.extend(batch)
        offset += len(batch)
        if not batch or offset >= int(response["total"]):
            return rows


def fetch_retail_sales(client: Client, frequency: str = "annual") -> int:
    params = {
        "frequency": frequency,
        "data[0]": "price",
        "data[1]": "sales",
        "data[2]": "revenue",
        "data[3]": "customers",
    }
    rows = _fetch_all(client, "retail-sales", params)
    write_json(raw_path("eia", f"retail_sales_{frequency}.json"), rows, f"{BASE}/retail-sales/data")
    return len(rows)


def fetch_operational(client: Client, frequency: str = "annual") -> int:
    params = {
        "frequency": frequency,
        "data[0]": "generation",
        "data[1]": "cost-per-btu",
        "facets[sectorid][]": ELECTRIC_POWER_SECTOR,
    }
    for index, fuel in enumerate(FUELS):
        params[f"facets[fueltypeid][{index}]"] = fuel
    rows = _fetch_all(client, "electric-power-operational-data", params)
    write_json(
        raw_path("eia", f"operational_{frequency}.json"),
        rows,
        f"{BASE}/electric-power-operational-data/data",
    )
    return len(rows)


def run() -> dict:
    client = Client(min_interval=0.5)
    return {
        "retail_annual": fetch_retail_sales(client, "annual"),
        "retail_monthly": fetch_retail_sales(client, "monthly"),
        "operational_annual": fetch_operational(client, "annual"),
    }


if __name__ == "__main__":
    print(run())
