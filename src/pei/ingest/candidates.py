"""Local candidate filter. Congress.gov's bill list has no keyword search, so we match here."""

from __future__ import annotations

import re

from pei.config import load_yaml


def _pattern(terms: list[str], case_sensitive: bool = False) -> re.Pattern:
    alternatives = "|".join(re.escape(term) for term in sorted(terms, key=len, reverse=True))
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.compile(rf"\b(?:{alternatives})\b", flags)


def build_matcher() -> tuple[dict[str, re.Pattern], re.Pattern, re.Pattern]:
    config = load_yaml("keywords.yaml")
    pillars = {name: _pattern(terms) for name, terms in config["pillars"].items()}
    terms = config["cross_cutting"]
    # "AI" must stay case-sensitive, or the filter would match the word "ai" in other contexts.
    acronyms = [t for t in terms if t.isupper()]
    words = [t for t in terms if not t.isupper()]
    return pillars, _pattern(words), _pattern(acronyms, case_sensitive=True)


def match_title(title: str, matcher=None) -> dict:
    """Return which pillar and cross-cutting keywords a bill title hits."""
    pillars, words, acronyms = matcher or build_matcher()
    hits = sorted(name for name, pattern in pillars.items() if pattern.search(title or ""))
    cross_cutting = bool(words.search(title or "") or acronyms.search(title or ""))
    return {"keyword_pillars": hits, "keyword_ai": cross_cutting}


def is_candidate(title: str, matcher=None) -> bool:
    result = match_title(title, matcher)
    return bool(result["keyword_pillars"] or result["keyword_ai"])
