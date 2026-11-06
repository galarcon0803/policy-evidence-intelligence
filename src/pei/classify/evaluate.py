"""Build the blind labeling sample, and score the classifier against human labels.

Run: python -m pei.classify.evaluate --make-sheet
     python -m pei.classify.evaluate --score
"""

from __future__ import annotations

import argparse
import json
import math
import random

import anthropic
import pandas as pd

from pei.classify.documents import bill_files, build_document, render_for_model
from pei.classify.run import (
    batch_cost,
    cache_path,
    content_hash,
    load_prompt,
    make_request,
    parse_message,
    wait_for_batch,
)
from pei.classify.schemas import PILLARS, RELEVANT_AT
from pei.config import CONGRESS, EVAL_DIR, RAW_DIR, ROOT
from pei.ingest.candidates import build_matcher, match_title
from pei.ingest.http import read_payload

SEED = 20261106
PER_STRATUM = 10
SHEET = EVAL_DIR / "labels_to_fill.csv"
LABELS = EVAL_DIR / "labels.csv"


def wilson(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval, which behaves sensibly for small samples and extreme rates."""
    if total == 0:
        return (float("nan"), float("nan"))
    p = successes / total
    denominator = 1 + z**2 / total
    center = (p + z**2 / (2 * total)) / denominator
    half = z * math.sqrt(p * (1 - p) / total + z**2 / (4 * total**2)) / denominator
    return (max(0.0, center - half), min(1.0, center + half))


def stratum_for(title: str, matcher) -> str:
    """Stratify on the title keywords only, so the sample never depends on the classifier."""
    match = match_title(title, matcher)
    if match["keyword_pillars"]:
        return match["keyword_pillars"][0]
    return "ai_only" if match["keyword_ai"] else "rejected"


def sheet_context(document: dict, limit: int = 1200) -> str:
    """What the labeler reads: the CRS summary if there is one, or else the bill's own opening."""
    if document["crs_summary"]:
        return document["crs_summary"][:limit]
    text = document["bill_text"]
    if not text:
        return "(no summary or text published: use the link)"
    # Skip the printing header, which sits before the words that open the bill or resolution.
    starts = [i for i in (text.find(w) for w in ("A BILL", "RESOLUTION", "AN ACT")) if i >= 0]
    start = min(starts) if starts else 0
    return "(bill text) " + text[start : start + limit]


def make_sheet(per_stratum: int = PER_STRATUM, seed: int = SEED) -> pd.DataFrame:
    """About 10 bills per keyword stratum, plus AI-title-only bills and the 20 rejected bills."""
    matcher = build_matcher()
    rejected_path = RAW_DIR / "congress" / str(CONGRESS) / "rejected_sample.json"
    rejected = {
        f"{CONGRESS}-{b['type'].lower()}-{b['number']}": b["stratum"]
        for b in read_payload(rejected_path)
    }
    strata: dict[str, list] = {}
    for path in bill_files():
        document = build_document(path)
        if path.stem in rejected:
            name = f"rejected_{rejected[path.stem]}"
        else:
            name = stratum_for(document["title"] or "", matcher)
        strata.setdefault(name, []).append(document)

    rng = random.Random(seed)
    rows = []
    for name in sorted(strata):
        members = strata[name]
        count = len(members) if name.startswith("rejected") else min(per_stratum, len(members))
        for document in rng.sample(members, count):
            bill_type, number = document["bill_id"].split("-")[1:]
            url_type = {
                "hr": "house-bill",
                "s": "senate-bill",
                "hres": "house-resolution",
                "sres": "senate-resolution",
                "hjres": "house-joint-resolution",
                "sjres": "senate-joint-resolution",
                "hconres": "house-concurrent-resolution",
                "sconres": "senate-concurrent-resolution",
            }[bill_type]
            rows.append(
                {
                    "bill_id": document["bill_id"],
                    "title": document["title"],
                    "policy_area": document["policy_area"],
                    "summary": sheet_context(document),
                    "url": f"https://www.congress.gov/bill/{CONGRESS}th-congress/{url_type}/{number}",
                    **{pillar: "" for pillar in PILLARS},
                    "notes": "",
                    "_stratum": name,
                }
            )
    frame = pd.DataFrame(rows).sample(frac=1, random_state=seed).reset_index(drop=True)
    return frame


def write_sheet() -> pd.DataFrame:
    frame = make_sheet()
    # The stratum would reveal which bills the filter rejected, so it stays out of the sheet.
    frame[["bill_id", "_stratum"]].to_csv(EVAL_DIR / "sample_strata.csv", index=False)
    frame.drop(columns="_stratum").to_csv(SHEET, index=False, encoding="utf-8-sig")
    return frame


def load_predictions(bill_ids: list[str]) -> pd.DataFrame:
    prompt = load_prompt()
    documents = {path.stem: build_document(path) for path in bill_files() if path.stem in bill_ids}
    rows = []
    for bill_id, document in documents.items():
        path = cache_path(content_hash(render_for_model(document), prompt))
        if not path.exists():
            continue
        record = json.loads(path.read_text(encoding="utf-8"))
        if record["status"] != "ok":
            continue
        for item in record["result"]["pillars"]:
            rows.append(
                {
                    "bill_id": bill_id,
                    "pillar": item["pillar"],
                    "predicted": int(item["relevance"] >= RELEVANT_AT),
                }
            )
    return pd.DataFrame(rows)


def score(labels: pd.DataFrame, predictions: pd.DataFrame) -> pd.DataFrame:
    """Precision and recall per pillar, plus micro-averaged, each with a Wilson interval."""
    long = labels.melt(
        id_vars="bill_id", value_vars=list(PILLARS), var_name="pillar", value_name="label"
    )
    long = long.dropna(subset=["label"]).astype({"label": int})
    merged = long.merge(predictions, on=["bill_id", "pillar"])
    rows = []
    groups = [(pillar, merged[merged["pillar"] == pillar]) for pillar in PILLARS]
    groups.append(("all_pillars", merged))
    for name, group in groups:
        tp = int(((group["label"] == 1) & (group["predicted"] == 1)).sum())
        fp = int(((group["label"] == 0) & (group["predicted"] == 1)).sum())
        fn = int(((group["label"] == 1) & (group["predicted"] == 0)).sum())
        precision_ci = wilson(tp, tp + fp)
        recall_ci = wilson(tp, tp + fn)
        rows.append(
            {
                "pillar": name,
                "n": len(group),
                "tp": tp,
                "fp": fp,
                "fn": fn,
                "precision": tp / (tp + fp) if tp + fp else float("nan"),
                "precision_low": precision_ci[0],
                "precision_high": precision_ci[1],
                "recall": tp / (tp + fn) if tp + fn else float("nan"),
                "recall_low": recall_ci[0],
                "recall_high": recall_ci[1],
            }
        )
    return pd.DataFrame(rows)


def filter_misses(labels: pd.DataFrame, strata: pd.DataFrame) -> pd.DataFrame:
    """How many filter-rejected bills did the human mark relevant, by rejected stratum?"""
    merged = labels.merge(strata, on="bill_id")
    rejected = merged[merged["_stratum"].str.startswith("rejected")]
    relevant = rejected[list(PILLARS)].fillna(0).astype(int).any(axis=1)
    rows = []
    for name, group in rejected.assign(relevant=relevant).groupby("_stratum"):
        low, high = wilson(int(group["relevant"].sum()), len(group))
        rows.append(
            {
                "stratum": name,
                "n": len(group),
                "relevant": int(group["relevant"].sum()),
                "rate_low": low,
                "rate_high": high,
            }
        )
    return pd.DataFrame(rows)


def retest(bill_ids: list[str]) -> dict:
    """Classify the labeled bills a second time and report decision-level agreement.

    The API accepts no seed, so this measures how much a repeat run can differ. It spends real
    tokens, a small amount, and it is the only code path that bypasses the cache.
    """
    client = anthropic.Anthropic()
    prompt = load_prompt()
    documents = [build_document(path) for path in bill_files() if path.stem in bill_ids]
    requests = [
        make_request(f"retest{index}", document, prompt) for index, document in enumerate(documents)
    ]
    batch = client.messages.batches.create(requests=requests)
    wait_for_batch(client, batch.id)
    first = load_predictions(bill_ids)
    rows = []
    cost = 0.0
    for entry in client.messages.batches.results(batch.id):
        if entry.result.type != "succeeded":
            continue
        document = documents[int(entry.custom_id.removeprefix("retest"))]
        record = parse_message(entry.result.message, document)
        cost += batch_cost(**record["usage"])
        if record["status"] != "ok":
            continue
        for item in record["result"]["pillars"]:
            rows.append(
                {
                    "bill_id": document["bill_id"],
                    "pillar": item["pillar"],
                    "second": int(item["relevance"] >= RELEVANT_AT),
                }
            )
    merged = first.merge(pd.DataFrame(rows), on=["bill_id", "pillar"])
    return {
        "n": len(merged),
        "agreement": float((merged["predicted"] == merged["second"]).mean()),
        "cost_usd": round(cost, 4),
    }


def run_score(with_retest: bool = False) -> dict:
    labels = pd.read_csv(LABELS)
    strata = pd.read_csv(EVAL_DIR / "sample_strata.csv")
    predictions = load_predictions(labels["bill_id"].tolist())
    # Filter-rejected bills are scored only for the filter, since the live pipeline never sends
    # such bills to the classifier in normal use.
    in_scope = strata[~strata["_stratum"].str.startswith("rejected")]["bill_id"]
    table = score(labels[labels["bill_id"].isin(in_scope)], predictions)
    misses = filter_misses(labels, strata)
    results = {
        "classifier": table.to_dict("records"),
        "filter_misses": misses.to_dict("records"),
        "labels_total": len(labels),
        "blank_cells": int(labels[list(PILLARS)].isna().sum().sum()),
    }
    out = ROOT / "eval" / "results.json"
    if with_retest:
        results["retest"] = retest(in_scope.tolist())
    elif out.exists():
        previous = json.loads(out.read_text(encoding="utf-8"))
        if "retest" in previous:
            results["retest"] = previous["retest"]
    out.write_text(json.dumps(results, indent=1), encoding="utf-8")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--make-sheet", action="store_true")
    parser.add_argument("--score", action="store_true")
    parser.add_argument(
        "--retest", action="store_true", help="Also rerun labeled bills (costs tokens)"
    )
    args = parser.parse_args()
    if args.make_sheet:
        print(write_sheet()["_stratum"].value_counts())
    if args.score:
        print(json.dumps(run_score(args.retest), indent=1))
