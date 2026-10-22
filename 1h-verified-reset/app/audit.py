"""Audit log and alerts: one JSON object per line, appended and never rewritten.

audit.jsonl records everything the service does (including refusals).
alerts.jsonl records only the "MFA changed soon after a password reset" alerts.
T1-S03 adds the stricter append-only checks; this session just writes the lines.

Rule: never put a secret (temporary password, code, token) in an event.
"""

import json
import os
import threading
from pathlib import Path

from . import clock

REQUIRED_FIELDS = ("ts", "request_id", "actor", "action", "outcome", "details")
_lock = threading.Lock()


def audit_path() -> Path:
    return Path(os.environ.get("AUDIT_LOG_PATH", "audit.jsonl"))


def alerts_path() -> Path:
    return Path(os.environ.get("ALERTS_LOG_PATH", "alerts.jsonl"))


def _append(path: Path, event: dict) -> None:
    line = json.dumps(event, default=str, sort_keys=True)
    with _lock, path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def record(event: dict) -> dict:
    """Append one audit line. `ts` and `details` are filled in if missing."""
    event = dict(event)
    event.setdefault("ts", clock.now().isoformat())
    event.setdefault("details", {})
    event.setdefault("request_id", None)
    missing = [f for f in REQUIRED_FIELDS if f not in event]
    if missing:
        raise ValueError(f"audit event missing fields: {missing}")
    _append(audit_path(), event)
    return event


def record_alert(alert: dict) -> dict:
    alert = {"ts": clock.now().isoformat(), **alert}
    _append(alerts_path(), alert)
    return alert


def read_alerts() -> list[dict]:
    path = alerts_path()
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]
