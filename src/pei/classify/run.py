"""Classify bills with Claude, using the Batch API and a content-hash cache.

Run: python -m pei.classify.run --pilot 20     (measures cost, then stops)
     python -m pei.classify.run --budget 15    (full run, refuses to exceed the budget)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

from pei.classify.documents import bill_files, build_document, render_for_model
from pei.classify.schemas import Classification, count_quotes, output_schema, verify_quotes
from pei.config import CACHE_DIR, CONGRESS, MODEL, PROMPTS_DIR, RAW_DIR
from pei.ingest.http import read_payload

PROMPT_VERSION = "classify_v1"
EFFORT = "low"
MAX_TOKENS = 8000
# Claude Sonnet 5.5 list prices, dollars per million tokens, and the Batch API discount.
INPUT_PER_M = 2.0
OUTPUT_PER_M = 10.0
BATCH_DISCOUNT = 0.5


def load_prompt(version: str = PROMPT_VERSION) -> str:
    return (PROMPTS_DIR / f"{version}.md").read_text(encoding="utf-8")


def content_hash(rendered: str, prompt: str, model: str = MODEL, effort: str = EFFORT) -> str:
    """Key results on everything that can change them, so reruns only pay for real changes."""
    material = "\x00".join((prompt, model, effort, rendered))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def cache_path(key: str, cache_dir: Path = CACHE_DIR) -> Path:
    return cache_dir / "classifications" / f"{key}.json"


def batch_cost(input_tokens: int, output_tokens: int) -> float:
    return BATCH_DISCOUNT * (input_tokens * INPUT_PER_M + output_tokens * OUTPUT_PER_M) / 1e6


def parse_message(message, document: dict) -> dict:
    """Turn an API message into a cache record. Bad output is recorded, not dropped or repaired."""
    usage = {
        "input_tokens": message.usage.input_tokens,
        "output_tokens": message.usage.output_tokens,
    }
    record = {
        "bill_id": document["bill_id"],
        "model_served": message.model,
        "prompt_version": PROMPT_VERSION,
        "effort": EFFORT,
        "classified_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "stop_reason": message.stop_reason,
        "usage": usage,
        "status": "ok",
        "result": None,
        "quote_failures": [],
        "quote_count": 0,
    }
    if message.stop_reason == "refusal":
        record["status"] = "refused"
        return record
    if message.stop_reason == "max_tokens":
        record["status"] = "truncated"
        return record
    text = "".join(block.text for block in message.content if block.type == "text")
    try:
        result = Classification.model_validate_json(text)
    except ValueError as err:
        record["status"] = "invalid"
        record["error"] = str(err)[:500]
        return record
    record["result"] = result.model_dump()
    record["quote_failures"] = verify_quotes(result, document)
    record["quote_count"] = count_quotes(result)
    return record


def make_request(key: str, document: dict, prompt: str) -> Request:
    return Request(
        custom_id=key[:64],
        params=MessageCreateParamsNonStreaming(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=prompt,
            output_config={
                "effort": EFFORT,
                "format": {"type": "json_schema", "schema": output_schema()},
            },
            messages=[{"role": "user", "content": render_for_model(document)}],
        ),
    )


def wait_for_batch(client: anthropic.Anthropic, batch_id: str, poll: int = 30):
    while True:
        batch = client.messages.batches.retrieve(batch_id)
        if batch.processing_status == "ended":
            return batch
        time.sleep(poll)


def classify(documents: list[dict], client: anthropic.Anthropic | None = None) -> dict:
    """Classify whatever is not already cached. Returns counts and the actual cost of this run."""
    prompt = load_prompt()
    pending = {}
    for document in documents:
        key = content_hash(render_for_model(document), prompt)
        if not cache_path(key).exists():
            pending[key[:64]] = (key, document)
    summary = {"requested": len(documents), "cached": len(documents) - len(pending), "cost": 0.0}
    if not pending:
        return summary

    client = client or anthropic.Anthropic()
    requests = [make_request(key, doc, prompt) for key, doc in pending.values()]
    batch = client.messages.batches.create(requests=requests)
    print(f"Batch {batch.id}: {len(requests)} requests", flush=True)
    wait_for_batch(client, batch.id)

    statuses: dict[str, int] = {}
    for entry in client.messages.batches.results(batch.id):
        key, document = pending[entry.custom_id]
        if entry.result.type != "succeeded":
            statuses[entry.result.type] = statuses.get(entry.result.type, 0) + 1
            continue
        record = parse_message(entry.result.message, document)
        statuses[record["status"]] = statuses.get(record["status"], 0) + 1
        summary["cost"] += batch_cost(**record["usage"])
        path = cache_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    summary["statuses"] = statuses
    return summary


def candidate_documents() -> list[dict]:
    """Bills that passed the title filter. Rejected bills exist only to measure the filter."""
    rejected_path = RAW_DIR / "congress" / str(CONGRESS) / "rejected_sample.json"
    rejected = {
        f"{CONGRESS}-{bill['type'].lower()}-{bill['number']}"
        for bill in read_payload(rejected_path)
    }
    return [build_document(path) for path in bill_files() if path.stem not in rejected]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot", type=int)
    parser.add_argument("--budget", type=float, default=15.0)
    parser.add_argument("--exclude", type=Path, help="CSV of bill_ids to leave out of the pilot")
    args = parser.parse_args()
    documents = candidate_documents()
    if args.pilot:
        import pandas as pd

        excluded = set()
        if args.exclude and args.exclude.exists():
            excluded = set(pd.read_csv(args.exclude)["bill_id"])
        chosen = [d for d in documents if d["bill_id"] not in excluded][
            :: len(documents) // args.pilot
        ]
        summary = classify(chosen[: args.pilot])
        per_bill = summary["cost"] / max(args.pilot - summary["cached"], 1)
        projected = per_bill * len(documents)
        print(json.dumps(summary, indent=1))
        print(
            f"Cost per bill ${per_bill:.4f}. Projected for {len(documents)} bills: ${projected:.2f}"
        )
        return
    print(json.dumps(classify(documents), indent=1))


if __name__ == "__main__":
    main()
