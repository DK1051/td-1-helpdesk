"""The audit log only ever grows, and never holds a secret."""

import inspect
import itertools
import json
import os
from datetime import timedelta
from pathlib import Path

from app import audit, clock
from flows import (
    AUTH_MANAGER,
    call_back,
    completed_password_reset,
    create,
    issue,
    send_code,
    verify_until_approved,
)

FORBIDDEN_IN_MODULE = [
    "truncate",
    "unlink",
    "remove",
    "'w'",
    '"w"',
    "write_text",
    "write_bytes",
    "rename",
    "seek(",
    "os.replace",
]
REQUIRED = {"ts", "request_id", "actor", "action", "outcome", "details"}


def test_the_module_has_no_way_to_edit_delete_or_shorten_the_log():
    source = inspect.getsource(audit)
    assert [word for word in FORBIDDEN_IN_MODULE if word in source] == []
    public = {
        n
        for n, f in vars(audit).items()
        if inspect.isfunction(f) and f.__module__ == audit.__name__ and not n.startswith("_")
    }
    assert public == {"record", "record_alert", "read_alerts", "audit_path", "alerts_path"}
    assert source.count('.open("a"') == 1  # the one place that writes opens the file in append mode


def test_a_full_scenario_only_ever_adds_lines_and_never_leaks_a_secret(client, kc):
    log_path = Path(os.environ["AUDIT_LOG_PATH"])
    snapshots: list[str] = []  # the whole file after every API call
    secrets_seen: set[str] = set()  # every temporary password and correct code this scenario produced
    original_request = client.request

    def watching_request(*args, **kwargs):
        sent = kwargs.get("json") or {}
        if isinstance(sent, dict) and sent.get("code") and sent["code"] != "000000":
            secrets_seen.add(sent["code"])
        response = original_request(*args, **kwargs)
        if response.headers.get("content-type", "").startswith("application/json"):
            body = response.json()
            if isinstance(body, dict) and body.get("temporary_password"):
                secrets_seen.add(body["temporary_password"])
        snapshots.append(log_path.read_text() if log_path.exists() else "")
        return response

    client.request = watching_request

    completed_password_reset(client, kc, "priya.nair")  # happy path
    create(client, user="nobody.here")  # unknown user
    bad = create(client).json()["id"]
    send_code(client, bad)  # out of order
    call_back(client, bad, "555-9999")  # wrong number -> BLOCKED
    big = verify_until_approved(client, kc, "password", "daniel.okafor")  # privileged
    issue(client, big)  # refused: 409
    client.post(f"/reset-requests/{big}/approve", headers={"Authorization": "Bearer regular-token"})  # 403
    client.post(f"/reset-requests/{big}/approve", headers=AUTH_MANAGER)
    issue(client, big)
    clock.advance(timedelta(minutes=61))
    client.post("/maintenance/expire-temp-passwords")
    client.post("/mfa-change-events", json={"username": "priya.nair", "change": "x", "source": "test"})

    assert len(snapshots) > 12
    for before, after in itertools.pairwise(snapshots):
        assert after.startswith(before)  # nothing earlier was changed or removed
        assert after.count("\n") >= before.count("\n")  # the line count never goes down
    final = snapshots[-1]
    assert final.count("\n") >= 18 and len(secrets_seen) >= 4

    for line in final.splitlines():
        event = json.loads(line)  # every line is valid JSON...
        assert set(event) == REQUIRED  # ...with exactly the six fields
    for secret in secrets_seen | {"manager-token", "regular-token"}:
        assert secret not in final
