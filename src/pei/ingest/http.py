"""Shared HTTP helpers: an honestly identified client, retries, throttling, and a raw store.

Raw responses are saved as fetched so every clean table can be rebuilt and audited. API keys are
sent as query parameters by these APIs, so they are stripped before anything is written or logged.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from pei.config import RAW_DIR, USER_AGENT

RETRYABLE = {429, 500, 502, 503, 504}
SECRET_PARAMS = {"api_key"}


def redact_url(url: str) -> str:
    """Remove secret query parameters from a URL."""
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query) if k not in SECRET_PARAMS]
    return urlunsplit(parts._replace(query=urlencode(query)))


class SourceBlocked(RuntimeError):
    """A source refused access. Callers record the gap; nothing tries to get around it."""


class Client:
    def __init__(self, min_interval: float = 0.0, retries: int = 4, timeout: float = 60.0):
        self._client = httpx.Client(
            headers={"User-Agent": USER_AGENT}, timeout=timeout, follow_redirects=True
        )
        self.min_interval = min_interval
        self.retries = retries
        self._last = 0.0

    def get(self, url: str, params: dict | None = None) -> httpx.Response:
        for attempt in range(self.retries + 1):
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            try:
                response = self._client.get(url, params=params)
            except httpx.TransportError as err:
                if attempt == self.retries:
                    raise RuntimeError(f"Network failure: {redact_url(url)}") from err
                time.sleep(2**attempt)
                continue
            if response.status_code in (401, 403):
                raise SourceBlocked(f"{response.status_code} from {redact_url(url)}")
            if response.status_code in RETRYABLE and attempt < self.retries:
                retry_after = response.headers.get("retry-after", "")
                time.sleep(int(retry_after) if retry_after.isdigit() else 2**attempt)
                continue
            if response.is_error:
                raise RuntimeError(f"HTTP {response.status_code} from {redact_url(url)}")
            return response
        raise AssertionError("unreachable")

    def get_json(self, url: str, params: dict | None = None) -> dict:
        return self.get(url, params).json()


def raw_path(*parts: str) -> Path:
    path = RAW_DIR.joinpath(*parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, payload: dict | list, source_url: str) -> None:
    """Write a raw payload with provenance. Temp-then-rename keeps interrupted runs resumable."""
    envelope = {
        "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source_url": redact_url(source_url),
        "payload": payload,
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(envelope, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def read_payload(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8"))["payload"]
