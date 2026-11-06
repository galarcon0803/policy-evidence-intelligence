"""Load and validate the metrics registry, and check published numbers against it.

Run: python -m pei.metrics.registry
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd
import yaml

from pei.config import METRICS_DIR, ROOT, SNAPSHOT_DIR

REQUIRED_FIELDS = (
    "id",
    "name",
    "status",
    "definition",
    "unit",
    "geography",
    "refresh_cadence",
    "owner",
    "version",
    "sources",
    "limitations",
    "uncertainty",
    "decision_use",
    "misread_risk",
    "does_not_show",
    "version_history",
)
STATUSES = {"computable", "requires_internal"}
INTERNAL_MARK = "Requires Anthropic internal data"


def load_registry(path: Path | None = None) -> list[dict]:
    path = path or METRICS_DIR / "registry.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))["metrics"]


def connect_snapshot(source: Path = SNAPSHOT_DIR) -> duckdb.DuckDBPyConnection:
    """Open an in-memory database with every snapshot file as a view."""
    con = duckdb.connect(":memory:")
    for file in sorted(source.glob("*.parquet")):
        con.execute(f"CREATE VIEW {file.stem} AS SELECT * FROM '{file.as_posix()}'")
    return con


def validate_entry(metric: dict) -> list[str]:
    """Return completeness problems for one entry. Does not run any SQL."""
    label = metric.get("id", "<no id>")
    problems = [f"{label}: missing {field}" for field in REQUIRED_FIELDS if not metric.get(field)]
    status = metric.get("status")
    if status not in STATUSES:
        problems.append(f"{label}: unknown status {status!r}")
    if status == "computable":
        if not metric.get("sql"):
            problems.append(f"{label}: computable metric has no sql")
        if any(not source.get("url") for source in metric.get("sources", [])):
            problems.append(f"{label}: computable metric has a source without a url")
        if INTERNAL_MARK in json.dumps(metric.get("sources", [])):
            problems.append(f"{label}: computable metric cites internal data")
    if status == "requires_internal":
        if metric.get("sql"):
            problems.append(f"{label}: internal metric must not have sql")
        if not metric.get("schema"):
            problems.append(f"{label}: internal metric needs a schema")
        if INTERNAL_MARK not in json.dumps(metric.get("sources", [])):
            problems.append(f"{label}: internal metric must be marked as requiring internal data")
    history = metric.get("version_history") or []
    if history and history[-1].get("version") != metric.get("version"):
        problems.append(f"{label}: version does not match the latest version_history entry")
    return problems


def validate_registry(metrics: list[dict], con: duckdb.DuckDBPyConnection) -> list[str]:
    """Check every entry is complete, IDs are unique, pairs resolve, and all SQL runs."""
    problems: list[str] = []
    ids = [metric.get("id") for metric in metrics]
    for duplicate in {i for i in ids if ids.count(i) > 1}:
        problems.append(f"duplicate metric id: {duplicate}")
    for metric in metrics:
        problems += validate_entry(metric)
        pair = metric.get("paired_with")
        if pair and pair not in ids:
            problems.append(f"{metric['id']}: paired_with points to unknown metric {pair}")
        if metric.get("status") == "computable" and metric.get("sql"):
            try:
                rows = con.execute(metric["sql"]).df()
            except duckdb.Error as err:
                problems.append(f"{metric['id']}: SQL failed: {err}")
                continue
            if "value" not in rows.columns:
                problems.append(f"{metric['id']}: SQL must return a value column")
            elif rows.empty:
                problems.append(f"{metric['id']}: SQL returned no rows")
    return problems


def compute(metric: dict, con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    if metric.get("status") != "computable":
        raise ValueError(f"{metric['id']} requires internal data and has no value here")
    return con.execute(metric["sql"]).df()


# Consistency check ---------------------------------------------------------------------------

SCANNED_SUFFIXES = {".py", ".sql"}
SCANNED_DIRS = ("src", "app")
# Tokens that identify each metric's canonical logic. This is a pattern check that catches the
# common mistake of recomputing a metric by hand, and it is not a proof of semantic uniqueness.
SIGNATURES = {
    "residential_price_yoy": re.compile(r"res_price\s*/\s*\w+|pct_change\(\).*res_price"),
    "ci_load_growth": re.compile(r"ci_sales\s*/\s*\w+|lag\(ci_sales"),
    "atlas_footprint": re.compile(r"building_sqft\s*/\s*1e6"),
}


def find_duplicate_logic(roots: tuple[Path, ...] | None = None) -> list[str]:
    """Flag code outside the registry that appears to recompute a registered metric."""
    roots = roots or tuple(ROOT / name for name in SCANNED_DIRS)
    findings = []
    for root in roots:
        for path in sorted(root.rglob("*")):
            if path.suffix not in SCANNED_SUFFIXES or path.name == Path(__file__).name:
                continue
            text = path.read_text(encoding="utf-8")
            for metric_id, pattern in SIGNATURES.items():
                if pattern.search(text):
                    findings.append(f"{path.name}: appears to recompute {metric_id}")
    return findings


# Published claims ledger ---------------------------------------------------------------------


@dataclass(frozen=True)
class Claim:
    """One number published in a document, pinned to where it comes from."""

    id: str
    text: str
    documents: tuple[str, ...]
    source: str
    selector: dict
    scale: float
    decimals: int
    metric_version: str | None
    as_of: str
    source_hash: str


def load_claims(path: Path | None = None) -> list[Claim]:
    path = path or METRICS_DIR / "published_claims.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    claims = []
    for row in raw["claims"]:
        claims.append(
            Claim(
                id=row["id"],
                text=row["text"],
                documents=tuple(row["documents"]),
                source=row["source"],
                selector=row["selector"],
                scale=float(row.get("scale", 1)),
                decimals=int(row["decimals"]),
                metric_version=row.get("metric_version"),
                as_of=row["as_of"],
                source_hash=row["source_hash"],
            )
        )
    return claims


def _results_value(selector: dict, root: Path) -> float:
    data = json.loads((root / "analysis" / "results" / "flagship.json").read_text("utf-8"))
    node = data
    for key in selector["path"]:
        node = node[key]
    return float(node)


def _metric_value(selector: dict, metrics: list[dict], con: duckdb.DuckDBPyConnection) -> float:
    metric = next(m for m in metrics if m["id"] == selector["metric"])
    rows = compute(metric, con)
    for column, wanted in selector.get("where", {}).items():
        rows = rows[rows[column] == wanted]
    if len(rows) != 1:
        raise ValueError(f"selector for {selector['metric']} matched {len(rows)} rows")
    return float(rows["value"].iloc[0])


def source_hash(claim_source: str, selector: dict, root: Path, con) -> str:
    """Hash the data behind a claim, so a silent change to the source is detectable."""
    if claim_source == "flagship_results":
        payload = (root / "analysis" / "results" / "flagship.json").read_bytes()
    else:
        metric = selector["metric"]
        sql = next(
            m for m in load_registry(root / "metrics" / "registry.yaml") if m["id"] == metric
        )
        frame = con.execute(sql["sql"]).df()
        order = sorted(frame.columns)
        payload = frame.sort_values(order)[order].to_csv(index=False).encode()
    return hashlib.sha256(payload.replace(b"\r\n", b"\n")).hexdigest()[:16]


def format_claim_value(value: float, claim: Claim) -> str:
    return f"{value * claim.scale:.{claim.decimals}f}".replace("-", "−")


def check_claims(root: Path = ROOT, source: Path | None = None) -> list[str]:
    """Recompute every published number. Any drift in value, version, text, or data is a failure."""
    con = connect_snapshot(source or root / "data" / "snapshot")
    metrics = load_registry(root / "metrics" / "registry.yaml")
    versions = {m["id"]: m["version"] for m in metrics}
    problems = []
    for claim in load_claims(root / "metrics" / "published_claims.yaml"):
        if claim.source == "flagship_results":
            value = _results_value(claim.selector, root)
        else:
            value = _metric_value(claim.selector, metrics, con)
            current = versions[claim.selector["metric"]]
            if claim.metric_version != current:
                problems.append(
                    f"{claim.id}: pinned to metric version {claim.metric_version}, now {current}"
                )
        expected = claim.text.replace("{value}", format_claim_value(value, claim))
        for document in claim.documents:
            body = (root / document).read_text(encoding="utf-8")
            if expected not in body:
                problems.append(f"{claim.id}: {document} does not contain: {expected!r}")
        current_hash = source_hash(claim.source, claim.selector, root, con)
        if current_hash != claim.source_hash:
            problems.append(
                f"{claim.id}: source data changed ({claim.source_hash} to {current_hash}). "
                "Review the claim, then update its hash and as_of date."
            )
    return problems


def pin_claims(root: Path = ROOT, today: str | None = None) -> int:
    """After review, record current data hashes and metric versions in the ledger."""
    path = root / "metrics" / "published_claims.yaml"
    con = connect_snapshot(root / "data" / "snapshot")
    versions = {m["id"]: m["version"] for m in load_registry(root / "metrics" / "registry.yaml")}
    text = path.read_text(encoding="utf-8")
    header = text[: text.index("claims:")]
    data = yaml.safe_load(text)
    for row in data["claims"]:
        fresh = source_hash(row["source"], row["selector"], root, con)
        if fresh != row["source_hash"]:
            row["source_hash"] = fresh
            row["as_of"] = today or date.today().isoformat()
        if row["source"] != "flagship_results":
            row["metric_version"] = versions[row["selector"]["metric"]]
    body = yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=100)
    path.write_text(header + body, encoding="utf-8")
    return len(data["claims"])


def main() -> int:
    if "--pin" in sys.argv:
        print(f"Pinned {pin_claims()} claims. Review the diff before committing.")
        return 0
    con = connect_snapshot()
    problems = validate_registry(load_registry(), con)
    problems += find_duplicate_logic()
    problems += check_claims()
    for problem in problems:
        print("FAIL", problem)
    print(f"{len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
