"""Tests for the gaps found in the T1-S02 reviews (G1-G5) and the blocked-request alert (Q2)."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import httpx
import pyotp
import pytest
from app import clock
from app.keycloak import KeycloakClient, KeycloakError
from app.main import app, get_keycloak, get_store
from app.state import Store
from fastapi.testclient import TestClient
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


def open_request_at_callback_done(client, kind="password", user="priya.nair") -> str:
    created = create(client, kind, user).json()
    call_back(client, created["id"], client.kc.users[user].phone)
    return created["id"]


# ---- G1: a one-time code cannot be used twice -------------------------------------------------------
def test_a_code_used_once_is_refused_in_a_second_request(client, kc):
    first = open_request_at_callback_done(client)
    code = kc.fresh_code()
    assert send_code(client, first, code).json()["state"] == "APPROVED"

    second = open_request_at_callback_done(client)  # same user, a new request
    refused = send_code(client, second, code).json()
    assert refused["state"] == "CALLBACK_DONE" and refused["otp_attempts_left"] == 2
    line = [x for x in audit_lines() if x["request_id"] == second and x["action"] == "otp"][-1]
    assert line["details"]["reason"] == "otp_reused"
    assert send_code(client, second).json()["state"] == "APPROVED"  # a fresh code still works


def test_an_older_code_is_refused_after_a_newer_one_was_used(client, kc):
    first = open_request_at_callback_done(client)
    assert send_code(client, first, kc.code(+1)).json()["state"] == "APPROVED"  # a code from the next step

    second = open_request_at_callback_done(client)
    assert send_code(client, second, kc.code(0)).json()["state"] == "CALLBACK_DONE"  # older step: refused
    assert send_code(client, second, kc.code(+1)).json()["state"] == "CALLBACK_DONE"  # same step: refused
    kc.tick()  # 30 seconds later
    assert send_code(client, second, kc.code(+1)).json()["state"] == "APPROVED"  # the next step works


def test_replayed_codes_count_toward_three_strikes(client, kc):
    first = open_request_at_callback_done(client)
    code = kc.fresh_code()
    send_code(client, first, code)
    second = open_request_at_callback_done(client)
    for _ in range(3):
        result = send_code(client, second, code).json()
    assert (result["state"], result["reason"]) == ("BLOCKED", "otp_failed")


def test_verify_otp_returns_the_matched_time_step(tmp_path, monkeypatch):
    seed = pyotp.random_base32()
    (tmp_path / "seeds.json").write_text(json.dumps({"priya.nair": seed}))
    monkeypatch.setenv("SEEDS_PATH", str(tmp_path / "seeds.json"))
    real, totp = KeycloakClient(), pyotp.TOTP(seed)

    before = totp.timecode(datetime.now(UTC))
    step = real.verify_otp("priya.nair", totp.generate_otp(before))
    after = totp.timecode(datetime.now(UTC))
    assert step in (before, after)
    assert real.verify_otp("priya.nair", totp.generate_otp(before - 1)) in (before - 1, after - 1)  # drift allowed
    assert real.verify_otp("priya.nair", totp.generate_otp(after + 2)) is None  # too far ahead
    assert real.verify_otp("priya.nair", "12345x") is None and real.verify_otp("priya.nair", "١٢٣٤٥٦") is None
    assert real.verify_otp("nobody", totp.generate_otp(before)) is None


# ---- G2: only the newest temporary password of a user is rotated -------------------------------------------
def test_two_resets_50_minutes_apart_rotate_only_the_latest(client, kc):
    completed_password_reset(client, kc)
    clock.advance(timedelta(minutes=50))
    completed_password_reset(client, kc)

    clock.advance(timedelta(minutes=10))  # minute 60: the first has expired, but it was replaced
    assert client.post("/maintenance/expire-temp-passwords").json()["rotated"] == []
    assert len(kc.password_history) == 2

    clock.advance(timedelta(minutes=50))  # minute 110: the second one expires
    assert len(client.post("/maintenance/expire-temp-passwords").json()["rotated"]) == 1
    assert len(kc.password_history) == 3


def test_expiry_for_a_user_who_no_longer_exists_says_so(client, kc):
    completed_password_reset(client, kc)
    del kc.users["priya.nair"]
    clock.advance(timedelta(minutes=61))
    client.post("/maintenance/expire-temp-passwords")
    line = next(x for x in audit_lines() if x["action"] == "temp_password_expiry")
    assert (line["outcome"], line["details"]["reason"]) == ("skipped", "user_not_found")


# ---- G3: a manager-approved request still raises the rule 5 alert at issue ---------------------------------------
def test_manager_approved_privileged_mfa_request_still_alerts_when_a_reset_completes_meanwhile(client, kc):
    mfa = verify_until_approved(client, kc, "mfa_reset", "daniel.okafor")  # privileged: waits for a manager
    assert client.post(f"/reset-requests/{mfa}/approve", headers=AUTH_MANAGER).status_code == 200
    assert alerts(client) == []

    reset = verify_until_approved(client, kc, "password", "daniel.okafor")  # a password reset completes meanwhile
    client.post(f"/reset-requests/{reset}/approve", headers=AUTH_MANAGER)
    assert issue(client, reset).json()["state"] == "COMPLETED"

    done = issue(client, mfa)
    assert done.status_code == 200 and done.json()["state"] == "COMPLETED"  # a human approved: no 409
    assert [a["reason"] for a in alerts(client)] == ["mfa_change_within_24h_of_password_reset"]  # exactly one


# ---- G4: the agent cannot approve their own request -----------------------------------------------------------------
def test_approver_who_is_the_agent_gets_403(client, kc):
    kc.add_token("agent-token", "Agent.Lee", roles=["manager"])  # same name as agent_id, different capitals
    request_id = verify_until_approved(client, kc, "password", "daniel.okafor")
    response = client.post(f"/reset-requests/{request_id}/approve", headers={"Authorization": "Bearer agent-token"})
    assert response.status_code == 403
    assert state_of(client, request_id) == "AWAITING_APPROVAL"
    assert any(x["details"].get("reason") == "approver_is_agent" for x in audit_lines())


# ---- G5: odd answers from Keycloak fail closed (502 + audit line), never a 500 ---------------------------------------------
def real_client_answering(handler, monkeypatch) -> KeycloakClient:
    monkeypatch.setenv("RESET_SERVICE_SECRET", "not-a-real-secret")
    kc = KeycloakClient()
    kc._http = httpx.Client(transport=httpx.MockTransport(handler))
    return kc


def keycloak_that_answers(users, groups=None, credentials=None):
    def handler(request):
        path = request.url.path
        if path.endswith("/openid-connect/token"):
            return httpx.Response(200, json={"access_token": "x", "expires_in": 60})
        if path.endswith("/groups"):
            return httpx.Response(200, json=groups if groups is not None else [])
        if path.endswith("/credentials"):
            return httpx.Response(200, json=credentials if credentials is not None else [])
        return httpx.Response(200, json=users)

    return handler


@pytest.mark.parametrize(
    "users, groups",
    [
        ([{"username": "priya.nair"}], []),  # no id
        ([{"id": "abc"}], []),  # no username
        (["not-an-object"], []),
        ([{"id": "abc", "username": "priya.nair"}], [{"no_name": 1}]),  # group without a name
        ([{"id": "abc", "username": "priya.nair", "attributes": "oops"}], []),
    ],
)
def test_odd_keycloak_user_answers_become_bad_response(monkeypatch, users, groups):
    kc = real_client_answering(keycloak_that_answers(users, groups), monkeypatch)
    with pytest.raises(KeycloakError) as caught:
        kc.get_user("priya.nair")
    assert str(caught.value) == "bad_response"


def test_credential_without_an_id_becomes_bad_response(monkeypatch, tmp_path):
    monkeypatch.setenv("SEEDS_PATH", str(tmp_path / "seeds.json"))
    users = [{"id": "abc", "username": "priya.nair"}]
    kc = real_client_answering(keycloak_that_answers(users, credentials=[{"type": "otp"}]), monkeypatch)
    with pytest.raises(KeycloakError) as caught:
        kc.remove_otp_device("priya.nair")
    assert str(caught.value) == "bad_response"


def test_the_service_answers_502_and_audits_when_keycloak_sends_a_user_without_an_id(monkeypatch):
    real = real_client_answering(keycloak_that_answers([{"username": "priya.nair"}]), monkeypatch)
    store = Store()
    app.dependency_overrides[get_keycloak] = lambda: real
    app.dependency_overrides[get_store] = lambda: store
    try:
        response = create(TestClient(app))
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 502
    line = audit_lines()[-1]
    assert (line["outcome"], line["details"]) == ("keycloak_error", {"error": "bad_response"})


# ---- Q2: every request that ends BLOCKED also raises one alert ----------------------------------------------------------------
def blocked_alerts(client) -> list[dict]:
    return [a for a in alerts(client) if a["reason"] == "blocked_identity_request"]


def test_unknown_user_and_missing_phone_raise_no_alert_but_are_audited(client, kc):
    kc.add_user("no.phone", None, device=True)
    unknown = create(client, user="nobody.here").json()
    no_phone = create(client, user="no.phone").json()
    assert (unknown["reason"], no_phone["reason"]) == ("unknown_user", "no_phone_on_file")
    assert alerts(client) == []  # no real account was at risk
    blocked_lines = [x for x in audit_lines() if x["outcome"] == "blocked"]
    assert [x["details"]["reason"] for x in blocked_lines] == ["unknown_user", "no_phone_on_file"]


def test_wrong_callback_number_raises_one_blocked_alert(client):
    request_id = create(client).json()["id"]
    call_back(client, request_id, "555-9999")
    call_back(client, request_id, "555-9999")  # a second try is out of order: no second alert
    assert [a["blocked_because"] for a in blocked_alerts(client)] == ["callback_wrong_number"]


def test_three_wrong_codes_raise_one_blocked_alert(client):
    request_id = open_request_at_callback_done(client)
    for _ in range(3):
        send_code(client, request_id, "000000")
    assert [a["blocked_because"] for a in blocked_alerts(client)] == ["otp_failed"]


def test_escalated_and_completed_requests_raise_no_blocked_alert(client, kc):
    completed_password_reset(client, kc, "priya.nair")
    request_id = open_request_at_callback_done(client, user="sofia.alvarez")
    assert send_code(client, request_id, "000000").json()["state"] == "ESCALATED"
    assert blocked_alerts(client) == []


# ---- review items -------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("agent_spelling", [" marcus.chen", "Marcus.Chen ", "MARCUS.CHEN"])
def test_agent_id_is_normalised_so_the_approver_check_cannot_be_dodged(client, kc, agent_spelling):
    created = create(client, "password", "daniel.okafor", agent_id=agent_spelling).json()
    assert created["agent_id"] == "marcus.chen"
    call_back(client, created["id"], "555-0104")
    send_code(client, created["id"])
    response = client.post(f"/reset-requests/{created['id']}/approve", headers=AUTH_MANAGER)  # marcus.chen's token
    assert response.status_code == 403
    assert any(x["details"].get("reason") == "approver_is_agent" for x in audit_lines())


def test_one_code_sent_eight_times_in_parallel_across_two_requests_passes_once(client, kc):
    kc.otp_delay = 0.03  # widens the race window; an unlocked version would let several through
    first, second = open_request_at_callback_done(client), open_request_at_callback_done(client)
    code = kc.fresh_code()
    ids = [first, second] * 4
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda rid: send_code(client, rid, code).json(), ids))
    assert [r.get("state") for r in results].count("APPROVED") == 1  # the rest: refused, blocked or 409


def test_escalated_mfa_request_opened_before_a_reset_still_alerts(client, kc):
    mfa = create(client, "mfa_reset", "priya.nair").json()["id"]  # opened first, no alert yet
    completed_password_reset(client, kc, "priya.nair")
    kc.devices.discard("priya.nair")  # her device is gone by the time the code step comes
    call_back(client, mfa, "555-0101")
    assert send_code(client, mfa).json()["state"] == "ESCALATED"
    assert [a["reason"] for a in alerts(client)] == ["mfa_change_within_24h_of_password_reset"]


def test_odd_attributes_make_set_phone_and_totp_setup_fail_closed(monkeypatch):
    bad_user = [{"id": "abc", "username": "priya.nair", "attributes": "oops", "requiredActions": 5}]
    kc = real_client_answering(keycloak_that_answers(bad_user), monkeypatch)
    for call in (lambda: kc.set_phone("priya.nair", "555-0188"), lambda: kc.require_totp_setup("priya.nair")):
        with pytest.raises(KeycloakError) as caught:
            call()
        assert str(caught.value) == "bad_response"


def test_phone_attribute_that_is_not_a_list_is_bad_response(monkeypatch):
    user = [{"id": "abc", "username": "priya.nair", "attributes": {"phone": 5550101}}]
    kc = real_client_answering(keycloak_that_answers(user), monkeypatch)
    with pytest.raises(KeycloakError):
        kc.get_user("priya.nair")


def test_service_answers_502_when_keycloak_data_is_odd_at_issue_time(monkeypatch, tmp_path):
    """create/callback/code work against a normal user, then the user record turns odd: issue gives 502 + audit."""
    seed = pyotp.random_base32()
    (tmp_path / "seeds.json").write_text(json.dumps({"priya.nair": seed}))
    monkeypatch.setenv("SEEDS_PATH", str(tmp_path / "seeds.json"))
    good = {"id": "abc", "username": "priya.nair", "attributes": {"phone": ["555-0101"]}}
    calls = {"users": 0}

    def handler(request):
        path = request.url.path
        if path.endswith("/openid-connect/token"):
            return httpx.Response(200, json={"access_token": "x", "expires_in": 60})
        if path.endswith("/groups"):
            return httpx.Response(200, json=[])
        calls["users"] += 1
        return httpx.Response(200, json=[good] if calls["users"] == 1 else [{**good, "attributes": "oops"}])

    real = real_client_answering(handler, monkeypatch)
    app.dependency_overrides[get_keycloak] = lambda: real
    store = Store()
    app.dependency_overrides[get_store] = lambda: store
    try:
        http = TestClient(app)
        created = create(http, "mfa_change_phone", "priya.nair", new_phone="555-0188").json()
        call_back(http, created["id"], "555-0101")
        code = pyotp.TOTP(seed).now()
        assert http.post(f"/reset-requests/{created['id']}/otp", json={"code": code}).json()["state"] == "APPROVED"
        assert issue(http, created["id"]).status_code == 502
    finally:
        app.dependency_overrides.clear()
    assert audit_lines()[-1]["details"] == {"error": "bad_response"}
