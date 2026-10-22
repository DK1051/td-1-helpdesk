"""Helpers that drive the service the way a helpdesk agent would."""

import json
import os
from pathlib import Path

GOOD_CODE = "123456"
AUTH_MANAGER = {"Authorization": "Bearer manager-token"}


def create(client, kind="password", user="priya.nair", **extra):
    body = {"kind": kind, "claimed_username": user, "agent_id": "agent.lee", "channel": "phone", **extra}
    return client.post("/reset-requests", json=body)


def call_back(client, request_id, number, reached=True):
    return client.post(f"/reset-requests/{request_id}/callback", json={"number_dialed": number, "reached": reached})


def send_code(client, request_id, code=GOOD_CODE):
    return client.post(f"/reset-requests/{request_id}/otp", json={"code": code})


def issue(client, request_id):
    return client.post(f"/reset-requests/{request_id}/issue")


def verify_until_approved(client, kc, kind="password", user="priya.nair", **extra) -> str:
    """create -> callback -> code; returns the request id (state APPROVED or AWAITING_APPROVAL)."""
    created = create(client, kind, user, **extra).json()
    call_back(client, created["id"], kc.users[user].phone)
    send_code(client, created["id"])
    return created["id"]


def state_of(client, request_id) -> str:
    return client.get(f"/reset-requests/{request_id}").json()["state"]


def audit_lines() -> list[dict]:
    path = Path(os.environ["AUDIT_LOG_PATH"])
    return [json.loads(line) for line in path.read_text().splitlines()]


def completed_password_reset(client, kc, user="priya.nair") -> dict:
    """Run a whole password reset for a regular user; returns the issue response."""
    request_id = verify_until_approved(client, kc, "password", user)
    return issue(client, request_id).json()
