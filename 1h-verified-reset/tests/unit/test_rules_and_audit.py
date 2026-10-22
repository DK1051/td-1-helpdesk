"""Temporary passwords, the 24-hour watch, and the audit log (no Keycloak server needed)."""

import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

from app import clock
from flows import (
    AUTH_MANAGER,
    audit_lines,
    call_back,
    completed_password_reset,
    create,
    issue,
    send_code,
    state_of,
    verify_until_approved,
)


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
    assert alerts(client)[0]["requested_change"] == "otp_device_added"


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


# ---- the 24-hour edge: inclusive at exactly 24 h, none one second later --------------------------
def test_24_hour_edge_for_requests(client, kc):
    completed_password_reset(client, kc, "priya.nair")
    clock.advance(timedelta(hours=24))
    verify_until_approved(client, kc, "mfa_reset", "priya.nair")
    assert len(alerts(client)) == 1  # exactly 24 h: still inside the window

    clock.advance(timedelta(seconds=1))
    verify_until_approved(client, kc, "mfa_enrol_device", "priya.nair")
    assert len(alerts(client)) == 1  # 24 h + 1 s: no new alert


def test_24_hour_edge_for_change_events(client, kc):
    completed_password_reset(client, kc, "priya.nair")
    body = {"username": "priya.nair", "change": "otp_device_added", "source": "keycloak-admin"}
    clock.advance(timedelta(hours=24))
    assert client.post("/mfa-change-events", json=body).json() == {"alerted": True}
    clock.advance(timedelta(seconds=1))
    assert client.post("/mfa-change-events", json=body).json() == {"alerted": False}


def test_a_damaged_alert_line_is_skipped_not_a_500(client, kc):
    completed_password_reset(client, kc, "priya.nair")
    client.post("/mfa-change-events", json={"username": "priya.nair", "change": "x", "source": "s"})
    with Path(os.environ["ALERTS_LOG_PATH"]).open("a") as f:
        f.write('{"half written\n')
    response = client.get("/alerts")
    assert response.status_code == 200 and len(response.json()) == 1


# ---- Keycloak trouble gives a clean error and an audit line, never a traceback ------------------------
def test_keycloak_down_gives_502_and_an_audit_line(client, kc):
    kc.down = True
    response = create(client)
    assert response.status_code == 502
    line = audit_lines()[-1]
    assert (line["action"], line["outcome"], line["details"]) == ("create", "keycloak_error", {"error": "network"})


def test_failed_rotation_is_retried_and_does_not_stop_other_users(client, kc):
    completed_password_reset(client, kc, "priya.nair")
    clock.advance(timedelta(minutes=61))
    kc.fail_set_password = True
    first = client.post("/maintenance/expire-temp-passwords").json()
    assert first == {"rotated": [], "failed": 1}
    kc.fail_set_password = False  # Keycloak recovers: the same password is rotated on the next run
    second = client.post("/maintenance/expire-temp-passwords").json()
    assert len(second["rotated"]) == 1 and second["failed"] == 0


def test_user_without_a_phone_on_file_is_blocked(client, kc):
    kc.add_user("no.phone", None, otp_code="123456")
    result = create(client, user="no.phone").json()
    assert (result["state"], result["reason"]) == ("BLOCKED", "no_phone_on_file")


# ---- two calls at once cannot beat the 3-try limit -------------------------------------------------
def test_parallel_wrong_codes_still_block_after_exactly_three_failures(client, kc):
    kc.otp_delay = 0.03  # makes an unlocked implementation fail this test reliably
    created = create(client).json()
    call_back(client, created["id"], "555-0101")
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda i: send_code(client, created["id"], f"00000{i}"), range(8)))
    assert state_of(client, created["id"]) == "BLOCKED"
    otp_lines = [x for x in audit_lines() if x["action"] == "otp"]
    counted = [x for x in otp_lines if x["outcome"] in ("wrong_code", "blocked")]
    assert len(counted) == 3  # exactly three wrong codes were ever evaluated
    assert sorted(r.status_code for r in results).count(409) == 5


# ---- rule 5 is re-checked when the reset completes while an MFA request is already open ----------------
def test_mfa_request_opened_before_the_reset_is_caught_at_the_code_step(client, kc):
    mfa = create(client, "mfa_reset", "priya.nair").json()  # opened first: no reset yet, no alert
    assert alerts(client) == []
    completed_password_reset(client, kc, "priya.nair")  # a password reset completes meanwhile
    call_back(client, mfa["id"], "555-0101")
    assert send_code(client, mfa["id"]).json()["state"] == "AWAITING_APPROVAL"
    assert len(alerts(client)) == 1


def test_mfa_request_approved_before_the_reset_is_caught_at_issue(client, kc):
    request_id = verify_until_approved(client, kc, "mfa_reset", "priya.nair")
    assert state_of(client, request_id) == "APPROVED"  # regular user, no reset yet
    completed_password_reset(client, kc, "priya.nair")

    refused = issue(client, request_id)
    assert refused.status_code == 409
    assert state_of(client, request_id) == "AWAITING_APPROVAL"
    assert len(alerts(client)) == 1
    assert kc.has_otp_device("priya.nair")  # nothing was changed
    assert any(x["details"].get("reason") == "needs_approval_rule5" for x in audit_lines())

    assert issue(client, request_id).status_code == 409  # still waiting; no second alert
    assert len(alerts(client)) == 1
    client.post(f"/reset-requests/{request_id}/approve", headers=AUTH_MANAGER)
    assert issue(client, request_id).json()["state"] == "COMPLETED"
    assert not kc.has_otp_device("priya.nair")
