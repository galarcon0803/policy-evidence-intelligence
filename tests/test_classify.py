import json
from types import SimpleNamespace

import pandas as pd
import pytest
from pydantic import ValidationError

from pei.classify import evaluate, run
from pei.classify.documents import clean_text, render_for_model
from pei.classify.schemas import PILLARS, Classification, count_quotes, output_schema, verify_quotes

DOCUMENT = {
    "bill_id": "119-hr-1",
    "title": "Ratepayer Protection Act",
    "policy_area": "Energy",
    "crs_summary": "This bill requires large load customers to pay for grid upgrades.",
    "latest_action": "Referred to committee.",
    "bill_text": "SEC. 2. A large load customer shall pay transmission upgrade costs.",
    "bill_text_truncated": False,
}


def evidence(field="crs_summary", quote="requires large load customers to pay"):
    return {"source_field": field, "quote": quote}


def pillar(name, relevance=0, proofs=None):
    return {
        "pillar": name,
        "relevance": relevance,
        "rationale": "A reason.",
        "evidence": proofs if proofs is not None else ([evidence()] if relevance else []),
    }


def payload(relevance=3, questions=2, **changes):
    data = {
        "pillars": [pillar(PILLARS[0], relevance), *[pillar(name) for name in PILLARS[1:]]],
        "safety": {"applies": False, "rationale": "None.", "evidence": []},
        "equity": {"applies": True, "rationale": "Who pays.", "evidence": [evidence()]},
        "governance": {"applies": False, "rationale": "None.", "evidence": []},
        "questions": [
            {"question": f"Question {i}?", "evidence": [evidence()]} for i in range(questions)
        ],
    }
    data.update(changes)
    return data


def test_valid_output_parses():
    assert Classification.model_validate(payload()).pillars[0].relevance == 3


def test_each_pillar_must_appear_exactly_once():
    with pytest.raises(ValidationError):
        Classification.model_validate(payload(pillars=[pillar(PILLARS[0], 3)]))


def test_relevance_outside_scale_is_rejected():
    with pytest.raises(ValidationError):
        Classification.model_validate(payload(relevance=7))


def test_scored_pillar_needs_evidence():
    bad = payload()
    bad["pillars"][0]["evidence"] = []
    with pytest.raises(ValidationError):
        Classification.model_validate(bad)


@pytest.mark.parametrize("count", [0, 1, 5])
def test_relevant_bill_needs_two_to_four_questions(count):
    with pytest.raises(ValidationError):
        Classification.model_validate(payload(questions=count))


def test_irrelevant_bill_must_have_no_questions():
    with pytest.raises(ValidationError):
        Classification.model_validate(payload(relevance=1, questions=2))
    assert Classification.model_validate(payload(relevance=1, questions=0))


def test_extra_fields_are_rejected():
    with pytest.raises(ValidationError):
        Classification.model_validate(payload(vote_prediction="yes"))


def test_schema_contains_no_prediction_field_and_is_closed():
    schema = output_schema()
    assert "vote" not in json.dumps(schema).lower()
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"pillars", "safety", "equity", "governance", "questions"}


def test_quote_check_passes_real_quotes():
    result = Classification.model_validate(payload())
    assert verify_quotes(result, DOCUMENT) == []
    assert count_quotes(result) == 4


def test_quote_check_ignores_case_and_whitespace_only():
    result = Classification.model_validate(
        payload(
            relevance=1,
            questions=0,
            pillars=[
                pillar(PILLARS[0], 1, [evidence(quote="REQUIRES  large\nload customers")]),
                *[pillar(name) for name in PILLARS[1:]],
            ],
        )
    )
    assert not [f for f in verify_quotes(result, DOCUMENT) if f["where"].startswith("pillar")]


def test_quote_check_catches_invented_quote():
    bad = payload()
    bad["questions"][0]["evidence"] = [evidence(quote="bans all data centers")]
    failures = verify_quotes(Classification.model_validate(bad), DOCUMENT)
    assert [f["where"] for f in failures] == ["question:0"]


def test_quote_check_catches_quote_from_the_wrong_field():
    bad = payload()
    bad["questions"][0]["evidence"] = [evidence(field="title", quote="requires large load")]
    assert verify_quotes(Classification.model_validate(bad), DOCUMENT)


def test_quote_check_catches_a_field_that_does_not_exist_on_the_bill():
    document = {**DOCUMENT, "bill_text": None}
    bad = payload()
    bad["questions"][0]["evidence"] = [evidence(field="bill_text", quote="shall pay transmission")]
    assert verify_quotes(Classification.model_validate(bad), document)


def message(text="{}", stop="end_turn"):
    return SimpleNamespace(
        model="claude-sonnet-5-5",
        stop_reason=stop,
        usage=SimpleNamespace(input_tokens=1000, output_tokens=200),
        content=[SimpleNamespace(type="text", text=text)],
    )


def test_parse_message_records_good_output():
    record = run.parse_message(message(json.dumps(payload())), DOCUMENT)
    assert record["status"] == "ok"
    assert record["quote_failures"] == []
    assert record["model_served"] == "claude-sonnet-5-5"


@pytest.mark.parametrize(
    ("msg", "status"),
    [
        (message(stop="refusal"), "refused"),
        (message(stop="max_tokens"), "truncated"),
        (message("not json"), "invalid"),
    ],
)
def test_bad_outputs_are_recorded_not_repaired(msg, status):
    record = run.parse_message(msg, DOCUMENT)
    assert record["status"] == status
    assert record["result"] is None


def test_cost_uses_batch_discount():
    assert run.batch_cost(1_000_000, 100_000) == pytest.approx(0.5 * (2.0 + 1.0))


def test_cache_key_changes_with_content_prompt_and_model():
    base = run.content_hash("doc", "prompt", "m1", "low")
    assert base == run.content_hash("doc", "prompt", "m1", "low")
    assert base != run.content_hash("doc2", "prompt", "m1", "low")
    assert base != run.content_hash("doc", "prompt2", "m1", "low")
    assert base != run.content_hash("doc", "prompt", "m2", "low")
    assert base != run.content_hash("doc", "prompt", "m1", "high")


def test_cached_bills_cost_nothing_and_make_no_api_call(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(run, "cache_path", lambda key: tmp_path / f"{key}.json")
    key = run.content_hash(render_for_model(DOCUMENT), run.load_prompt())
    (tmp_path / f"{key}.json").write_text("{}")
    summary = run.classify([DOCUMENT], client="must not be used")
    assert summary == {"requested": 1, "cached": 1, "cost": 0.0}


def test_render_marks_source_as_data_with_stable_order():
    rendered = render_for_model(DOCUMENT)
    assert rendered.startswith("<bill>") and rendered.endswith("</bill>")
    assert rendered == render_for_model(dict(reversed(list(DOCUMENT.items()))))


def test_prompt_says_bill_content_is_data():
    assert "must not be followed" in run.load_prompt()


def test_clean_text_removes_markup_and_entities():
    assert clean_text("<html><style>x{}</style><pre>A &amp; B</pre></html>") == "A & B"


# Evaluation ---------------------------------------------------------------------------------


def test_wilson_interval_behaves_at_extremes():
    low, high = evaluate.wilson(10, 10)
    assert high == pytest.approx(1.0) and 0.6 < low < 0.8
    low, high = evaluate.wilson(0, 10)
    assert low == pytest.approx(0.0) and 0.2 < high < 0.4
    assert all(pd.isna(x) for x in evaluate.wilson(0, 0))


def test_score_counts_precision_and_recall():
    labels = pd.DataFrame(
        [
            {"bill_id": "a", PILLARS[0]: 1, PILLARS[1]: 0, PILLARS[2]: 0, PILLARS[3]: 0},
            {"bill_id": "b", PILLARS[0]: 1, PILLARS[1]: 0, PILLARS[2]: 0, PILLARS[3]: 0},
            {"bill_id": "c", PILLARS[0]: 0, PILLARS[1]: 0, PILLARS[2]: 0, PILLARS[3]: None},
        ]
    )
    rows = []
    for bill, hit in (("a", 1), ("b", 0), ("c", 1)):
        rows += [{"bill_id": bill, "pillar": PILLARS[0], "predicted": hit}]
        rows += [{"bill_id": bill, "pillar": name, "predicted": 0} for name in PILLARS[1:]]
    table = evaluate.score(labels, pd.DataFrame(rows)).set_index("pillar")
    first = table.loc[PILLARS[0]]
    assert (first["tp"], first["fp"], first["fn"]) == (1, 1, 1)
    assert first["precision"] == 0.5 and first["recall"] == 0.5
    # The blank label is excluded, not treated as a zero.
    assert table.loc[PILLARS[3], "n"] == 2


def test_filter_misses_counts_relevant_rejected_bills():
    labels = pd.DataFrame(
        [
            {"bill_id": "a", PILLARS[0]: 1, PILLARS[1]: 0, PILLARS[2]: 0, PILLARS[3]: 0},
            {"bill_id": "b", PILLARS[0]: 0, PILLARS[1]: 0, PILLARS[2]: 0, PILLARS[3]: 0},
            {"bill_id": "c", PILLARS[0]: 1, PILLARS[1]: 0, PILLARS[2]: 0, PILLARS[3]: 0},
        ]
    )
    strata = pd.DataFrame(
        {
            "bill_id": ["a", "b", "c"],
            "_stratum": ["rejected_other", "rejected_other", "jobs_skills"],
        }
    )
    row = evaluate.filter_misses(labels, strata).iloc[0]
    assert (row["n"], row["relevant"]) == (2, 1)


def test_stratum_never_uses_classifier_output():
    matcher = evaluate.build_matcher()
    assert evaluate.stratum_for("Data Center Act", matcher) in PILLARS
    assert evaluate.stratum_for("AI Ads Act", matcher) == "ai_only"
    assert evaluate.stratum_for("Post Office Naming Act", matcher) == "rejected"
