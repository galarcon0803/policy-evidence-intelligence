"""Checks on the filter estimate, the disagreement list, and the one-time retry of failed records."""

import json

import pandas as pd

from pei.classify import run
from pei.classify.evaluate import disagreements, filter_estimate


def test_filter_estimate_scales_each_stratum():
    misses = pd.DataFrame(
        [
            {
                "stratum": "rejected_near_miss",
                "n": 10,
                "relevant": 3,
                "rate_low": 0.1,
                "rate_high": 0.6,
            },
            {
                "stratum": "rejected_other",
                "n": 10,
                "relevant": 0,
                "rate_low": 0.0,
                "rate_high": 0.28,
            },
        ]
    )
    estimate = filter_estimate(misses, 100, {"near_miss": 1000, "other": 10000})
    assert estimate["near_miss_missed"] == 300
    assert estimate["near_miss_missed_low"] == 100
    assert estimate["other_missed_high"] == 2800
    assert estimate["filter_recall_near_miss_only"] == 100 / 400
    assert estimate["filter_recall_low"] == 100 / 700
    assert estimate["filter_recall_high"] == 100 / 200


def test_disagreements_lists_only_differences():
    labels = pd.DataFrame(
        {
            "bill_id": ["a"],
            "title": ["T"],
            "electricity_affordability": [1],
            "data_centers_communities": [0],
            "education_learning": [0],
            "jobs_skills": [0],
        }
    )
    predictions = pd.DataFrame(
        [
            {"bill_id": "a", "pillar": "electricity_affordability", "predicted": 0, "relevance": 1},
            {"bill_id": "a", "pillar": "data_centers_communities", "predicted": 0, "relevance": 0},
        ]
    )
    rows = disagreements(labels, predictions).to_dict("records")
    assert [r["pillar"] for r in rows] == ["electricity_affordability"]


def test_retry_archives_first_failure_and_records_it(tmp_path, monkeypatch):
    target = tmp_path / "classifications" / "k.json"
    target.parent.mkdir()
    target.write_text(json.dumps({"bill_id": "b", "status": "invalid"}), encoding="utf-8")
    monkeypatch.setattr(run, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(run, "cache_path", lambda key, cache_dir=tmp_path: target)
    monkeypatch.setattr(run, "load_prompt", lambda: "p")
    monkeypatch.setattr(run, "render_for_model", lambda document: "r")

    def fake_classify(documents):
        if documents:
            assert not target.exists()
            target.write_text(json.dumps({"bill_id": "b", "status": "ok"}), encoding="utf-8")
        return {"requested": len(documents)}

    monkeypatch.setattr(run, "classify", fake_classify)
    run.retry_failed([{"bill_id": "b"}])
    record = json.loads(target.read_text(encoding="utf-8"))
    assert record == {"bill_id": "b", "status": "ok", "retried_from": "invalid"}
    archived = json.loads((tmp_path / "classifications_failed" / "k.json").read_text("utf-8"))
    assert archived["status"] == "invalid"
    assert run.retry_failed([{"bill_id": "b"}])["requested"] == 0
