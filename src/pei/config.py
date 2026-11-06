"""Project paths and settings. Secrets come only from the environment or a local .env."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
CACHE_DIR = DATA_DIR / "cache"
SNAPSHOT_DIR = DATA_DIR / "snapshot"
DB_PATH = DATA_DIR / "pei.duckdb"
PROMPTS_DIR = ROOT / "prompts"
METRICS_DIR = ROOT / "metrics"
EVAL_DIR = ROOT / "eval"

CONGRESS = int(os.getenv("PEI_CONGRESS", "119"))
MODEL = os.getenv("PEI_MODEL", "claude-sonnet-5-5")
USER_AGENT = "policy-evidence-intelligence/0.1 (independent research prototype)"


def api_key(name: str) -> str:
    """Return a required API key, with a clear error that never echoes values."""
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(
            f"{name} is not set. Add it to .env for full mode; demo mode does not need it."
        )
    return value


@lru_cache
def load_yaml(name: str) -> dict:
    with (CONFIG_DIR / name).open(encoding="utf-8") as f:
        return yaml.safe_load(f)
