import json
import shutil
from pathlib import Path

import duckdb
import pytest

from pei.config import ROOT
from pei.metrics import registry as reg


def good_metric(**changes):
    metric = {
        "id": "m1",
        "name": "Metric",
        "status": "computable",
        "definition": "A definition",
        "sql": "SELECT 1 AS value",
        "unit": "count",
        "geography": "US",
        "refresh_cadence": "Annual",
        "owner": "Team",
        "version": "1.0.0",
        "sources": [{"name": "Source", "url": "https://example.gov"}],
        "limitations": "Some",
        "uncertainty": "Some",
        "decision_use": "Some",
        "misread_risk": "Some",
        "does_not_show": "Some",
        "version_history": [{"version": "1.0.0", "date": "2026-11-06", "change": "Initial"}],
    }
    metric.update(changes)
    return metric


def validate(*metrics):
    return reg.validate_registry(list(metrics), duckdb.connect(":memory:"))


def test_complete_metric_passes():
    assert validate(good_metric()) == []


@pytest.mark.parametrize("field", reg.REQUIRED_FIELDS)
def test_each_required_field_is_enforced(field):
    metric = good_metric()
    metric.pop(field)
    assert validate(metric)


def test_broken_sql_is_flagged():
    problems = validate(good_metric(sql="SELECT nope FROM missing"))
    assert any("SQL failed" in p for p in problems)


def test_sql_without_value_column_is_flagged():
    assert any("value column" in p for p in validate(good_metric(sql="SELECT 1 AS x")))


def test_duplicate_ids_are_flagged():
    assert any("duplicate" in p for p in validate(good_metric(), good_metric()))


def test_version_must_match_history():
    assert any("version_history" in p for p in validate(good_metric(version="2.0.0")))


def internal(**changes):
    metric = good_metric(
        id="i1",
        status="requires_internal",
        schema=[{"field": "a", "type": "float"}],
        sources=[{"name": "Requires Anthropic internal data (not available)", "url": ""}],
    )
    metric.pop("sql")
    metric.update(changes)
    return metric


def test_internal_metric_schema_only_passes():
    assert validate(internal()) == []


def test_internal_metric_cannot_have_a_value_query():
    assert any("must not have sql" in p for p in validate(internal(sql="SELECT 1 AS value")))


def test_internal_metric_must_be_labeled():
    unlabeled = internal(sources=[{"name": "Some file", "url": "x"}])
    assert any("must be marked" in p for p in validate(unlabeled))


def test_computing_an_internal_metric_raises():
    with pytest.raises(ValueError, match="internal data"):
        reg.compute(internal(), duckdb.connect(":memory:"))


def test_every_internal_metric_in_real_registry_has_no_sql():
    internal_metrics = [m for m in reg.load_registry() if m["status"] == "requires_internal"]
    assert len(internal_metrics) >= 3
    assert all("sql" not in m for m in internal_metrics)


def test_efficiency_metric_is_paired_with_absolute_consumption():
    metrics = {m["id"]: m for m in reg.load_registry()}
    efficiency = metrics["energy_per_quality_adjusted_workload"]
    assert efficiency["paired_with"] == "total_electricity_consumption"


def test_real_registry_entries_are_complete():
    problems = [p for m in reg.load_registry() for p in reg.validate_entry(m)]
    assert problems == []


def test_real_metric_sql_runs_on_snapshot():
    assert reg.validate_registry(reg.load_registry(), reg.connect_snapshot()) == []


def test_codebase_does_not_recompute_registered_metrics():
    assert reg.find_duplicate_logic() == []


def test_duplicate_logic_check_catches_a_recomputed_metric(tmp_path: Path):
    (tmp_path / "bad.py").write_text('sql = "SELECT 100 * (res_price / prior - 1)"')
    findings = reg.find_duplicate_logic((tmp_path,))
    assert any("residential_price_yoy" in f for f in findings)


# Claims ledger ------------------------------------------------------------------------------


def test_published_claims_match_current_results():
    assert reg.check_claims() == []


@pytest.fixture
def sandbox(tmp_path: Path) -> Path:
    """A copy of everything the ledger reads, so a test can introduce drift safely."""
    for folder in ("metrics", "data/snapshot", "analysis"):
        shutil.copytree(ROOT / folder, tmp_path / folder)
    return tmp_path


def test_claims_detect_a_changed_number_in_a_document(sandbox: Path):
    path = sandbox / "analysis" / "flagship_case_study.md"
    text = path.read_text(encoding="utf-8").replace(
        "| Baseline (P1) | −0.153", "| Baseline (P1) | −0.200"
    )
    path.write_text(text, encoding="utf-8")
    assert any("p1_coefficient" in p for p in reg.check_claims(sandbox))


def test_claims_detect_changed_results(sandbox: Path):
    path = sandbox / "analysis" / "results" / "flagship.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["p1_twfe"]["coef"] = 0.5
    path.write_text(json.dumps(data), encoding="utf-8")
    problems = reg.check_claims(sandbox)
    assert any("p1_coefficient" in p and "does not contain" in p for p in problems)
    assert any("source data changed" in p for p in problems)


def test_pin_records_hashes_and_clears_hash_failures(sandbox: Path):
    path = sandbox / "analysis" / "results" / "flagship.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["note"] = "new field, same numbers"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert any("source data changed" in p for p in reg.check_claims(sandbox))
    reg.pin_claims(sandbox, today="2030-01-01")
    assert reg.check_claims(sandbox) == []
    assert any(
        c.as_of == "2030-01-01" for c in reg.load_claims(sandbox / "metrics/published_claims.yaml")
    )
