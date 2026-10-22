"""Temporary passwords, the 24-hour watch, and the audit log (no Keycloak server needed)."""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from app import clock
from flows import audit_lines, completed_password_reset, create, verify_until_approved


def alerts(client) -> list[dict]:
    return client.get("/alerts").json()


# ---- temporary password -------------------------------------------------------------
def test_temp_password_is_random_returned_once_and_never_logged(client, kc):
    first = completed_password_reset(client, kc, "priya.nair")
    second = completed_password_reset(client, kc, "priya.nair")
    pw1, pw2 = first["temporary_password"], second["temporary_password"]
    assert len(pw1) >= 16 and pw1 != pw2  # random
    assert datetime.fromisoformat(first["expires_at"]) == clock.now() + timedelta(minutes=60)
    assert kc.password_history[0] == ("priya.nair", pw1, True)  # set as a temporary password in Keycloak

    # Reading the request again never shows it.
    assert pw1 not in json.dumps(client.get(f"/reset-requests/{first['id']}").json())
    # The audit log says one was issued, but never what it was.
    log_text = Path(os.environ["AUDIT_LOG_PATH"]).read_text()
    assert pw1 not in log_text and pw2 not in log_text
    assert '"temporary_password_issued": true' in log_text


def test_temp_password_is_rotated_after_60_minutes(client, kc):
    pw = completed_password_reset(client, kc)["temporary_password"]
    clock.advance(timedelta(minutes=59))
    assert client.post("/maintenance/expire-temp-passwords").json()["rotated"] == []
    assert len(kc.password_history) == 1

    clock.advance(timedelta(minutes=1))  # exactly 60 minutes
    assert len(client.post("/maintenance/expire-temp-passwords").json()["rotated"]) == 1
    username, new_pw, _ = kc.password_history[-1]
    assert username == "priya.nair" and new_pw != pw
    assert new_pw not in Path(os.environ["AUDIT_LOG_PATH"]).read_text()
    assert client.post("/maintenance/expire-temp-passwords").json()["rotated"] == []  # only once


def test_rotation_skips_a_user_who_already_chose_their_own_password(client, kc):
    completed_password_reset(client, kc)
    kc.user_changed_own_password("priya.nair")
    clock.advance(timedelta(minutes=61))
    assert client.post("/maintenance/expire-temp-passwords").json()["rotated"] == []
    assert len(kc.password_history) == 1


# ---- the 24-hour watch (rule 5) ---------------------------------------------------------
def test_mfa_request_23_hours_after_a_reset_raises_an_alert_and_needs_approval(client, kc):
    completed_password_reset(client, kc, "priya.nair")
    clock.advance(timedelta(hours=23))
    request_id = verify_until_approved(client, kc, "mfa_reset", "priya.nair")
    assert len(alerts(client)) == 1
    assert alerts(client)[0]["reason"] == "mfa_change_within_24h_of_password_reset"
    # Priya is a regular user, but rule 5 still makes a manager look first.
    assert client.get(f"/reset-requests/{request_id}").json()["state"] == "AWAITING_APPROVAL"


def test_mfa_request_25_hours_after_a_reset_raises_no_alert(client, kc):
    completed_password_reset(client, kc, "priya.nair")
    clock.advance(timedelta(hours=25))
    request_id = verify_until_approved(client, kc, "mfa_reset", "priya.nair")
    assert alerts(client) == []
    assert client.get(f"/reset-requests/{request_id}").json()["state"] == "APPROVED"


def test_a_password_request_never_triggers_the_watch(client, kc):
    completed_password_reset(client, kc, "priya.nair")
    create(client, "password", "priya.nair")
    assert alerts(client) == []


def test_mfa_change_event_inside_24_hours_alerts(client, kc):
    completed_password_reset(client, kc, "priya.nair")
    clock.advance(timedelta(hours=23))
    body = {"username": "priya.nair", "change": "otp_device_added", "source": "keycloak-admin"}
    assert client.post("/mfa-change-events", json=body).json() == {"alerted": True}
    assert alerts(client)[0]["change"] == "otp_device_added"


def test_mfa_change_event_outside_24_hours_does_not_alert(client, kc):
    completed_password_reset(client, kc, "priya.nair")
    clock.advance(timedelta(hours=25))
    body = {"username": "priya.nair", "change": "otp_device_added", "source": "keycloak-admin"}
    assert client.post("/mfa-change-events", json=body).json() == {"alerted": False}
    assert alerts(client) == []


def test_mfa_change_event_for_a_user_with_no_reset_does_not_alert(client):
    body = {"username": "sofia.alvarez", "change": "otp_device_added", "source": "keycloak-admin"}
    assert client.post("/mfa-change-events", json=body).json() == {"alerted": False}


# ---- audit log shape ------------------------------------------------------------------------
def test_every_audit_line_is_json_with_the_required_fields(client, kc):
    completed_password_reset(client, kc, "priya.nair")  # normal steps
    create(client, user="nobody.here")  # a block
    request_id = create(client).json()["id"]
    client.post(f"/reset-requests/{request_id}/otp", json={"code": "1"})  # out of order
    lines = audit_lines()
    assert len(lines) == 7
    for line in lines:
        assert set(line) == {"ts", "request_id", "actor", "action", "outcome", "details"}
        assert isinstance(line["details"], dict)
        datetime.fromisoformat(line["ts"])
    assert {"ok", "blocked", "out_of_order"} <= {x["outcome"] for x in lines}
