"""Step order, verification outcomes and approval rules (no Keycloak server needed)."""

from flows import (
    AUTH_MANAGER,
    GOOD_CODE,
    audit_lines,
    call_back,
    create,
    issue,
    send_code,
    state_of,
    verify_until_approved,
)


def test_happy_path_regular_user(client, kc):
    created = create(client).json()
    assert created["state"] == "OPEN"
    assert created["phone_on_file"] == "555-0101"
    assert call_back(client, created["id"], "555-0101").json()["state"] == "CALLBACK_DONE"
    assert send_code(client, created["id"]).json()["state"] == "APPROVED"  # regular user: no manager needed
    done = issue(client, created["id"]).json()
    assert done["state"] == "COMPLETED"
    assert "temporary_password" in done


def test_callback_to_a_different_number_is_blocked(client):
    created = create(client).json()
    result = call_back(client, created["id"], "555-9999").json()  # even if "reached"
    assert result["state"] == "BLOCKED"
    assert result["reason"] == "callback_wrong_number"


def test_callback_not_reached_is_blocked(client):
    created = create(client).json()
    result = call_back(client, created["id"], "555-0101", reached=False).json()
    assert (result["state"], result["reason"]) == ("BLOCKED", "callback_not_reached")


def test_three_wrong_codes_block_the_request(client):
    created = create(client).json()
    call_back(client, created["id"], "555-0101")
    first = send_code(client, created["id"], "000000").json()
    assert first["state"] == "CALLBACK_DONE" and first["otp_attempts_left"] == 2
    send_code(client, created["id"], "000001")
    third = send_code(client, created["id"], "000002").json()
    assert (third["state"], third["reason"]) == ("BLOCKED", "otp_failed")
    assert send_code(client, created["id"], GOOD_CODE).status_code == 409  # too late, even with the right code


def test_otp_before_callback_is_409_and_audited(client):
    created = create(client).json()
    response = send_code(client, created["id"])
    assert response.status_code == 409
    assert state_of(client, created["id"]) == "OPEN"
    line = next(x for x in audit_lines() if x["outcome"] == "out_of_order")
    assert line["request_id"] == created["id"]
    assert line["action"] == "otp"
    assert line["details"] == {"expected": "CALLBACK_DONE", "actual": "OPEN"}


def test_privileged_user_needs_a_manager(client, kc):
    request_id = verify_until_approved(client, kc, "password", "daniel.okafor")
    assert state_of(client, request_id) == "AWAITING_APPROVAL"
    assert issue(client, request_id).status_code == 409  # cannot skip approval
    assert state_of(client, request_id) == "AWAITING_APPROVAL"

    url = f"/reset-requests/{request_id}/approve"
    assert client.post(url).status_code == 403  # no token
    assert client.post(url, headers={"Authorization": "Bearer bogus"}).status_code == 403  # unknown token
    assert client.post(url, headers={"Authorization": "Bearer regular-token"}).status_code == 403  # not a manager
    approved = client.post(url, headers=AUTH_MANAGER).json()
    assert approved["state"] == "APPROVED" and approved["approver"] == "marcus.chen"
    assert issue(client, request_id).json()["state"] == "COMPLETED"


def test_self_approval_is_refused(client, kc):
    kc.add_token("daniel-token", "daniel.okafor", roles=["manager"])  # a manager approving himself
    request_id = verify_until_approved(client, kc, "password", "daniel.okafor")
    response = client.post(f"/reset-requests/{request_id}/approve", headers={"Authorization": "Bearer daniel-token"})
    assert response.status_code == 403
    assert state_of(client, request_id) == "AWAITING_APPROVAL"
    assert [x["details"]["reason"] for x in audit_lines() if x["outcome"] == "refused"] == ["self_approval"]


def test_refused_approvals_are_audited(client, kc):
    request_id = verify_until_approved(client, kc, "password", "daniel.okafor")
    client.post(f"/reset-requests/{request_id}/approve", headers={"Authorization": "Bearer regular-token"})
    refused = [x for x in audit_lines() if x["action"] == "approve" and x["outcome"] == "refused"]
    assert refused[0]["actor"] == "priya.nair" and refused[0]["details"]["reason"] == "not_a_manager"


def test_approving_a_request_that_is_not_waiting_is_409(client, kc):
    created = create(client).json()
    response = client.post(f"/reset-requests/{created['id']}/approve", headers=AUTH_MANAGER)
    assert response.status_code == 409


def test_user_without_an_otp_device_is_escalated(client):
    created = create(client, user="sofia.alvarez").json()
    call_back(client, created["id"], "555-0103")
    result = send_code(client, created["id"]).json()
    assert (result["state"], result["reason"]) == ("ESCALATED", "no_registered_device")
    assert issue(client, created["id"]).status_code == 409


def test_unknown_user_is_blocked(client):
    response = create(client, user="nobody.here")
    assert response.json()["state"] == "BLOCKED"
    assert response.json()["reason"] == "unknown_user"
    assert call_back(client, response.json()["id"], "555-0101").status_code == 409


def test_get_unknown_request_is_404(client):
    assert client.get("/reset-requests/doesnotexist").status_code == 404


def test_mfa_reset_removes_the_device(client, kc):
    request_id = verify_until_approved(client, kc, "mfa_reset", "priya.nair")
    assert issue(client, request_id).json()["state"] == "COMPLETED"
    assert not kc.has_otp_device("priya.nair")


def test_mfa_enrol_device_asks_for_totp_setup(client, kc):
    request_id = verify_until_approved(client, kc, "mfa_enrol_device", "priya.nair")
    issue(client, request_id)
    assert kc.totp_setup_requested == ["priya.nair"]


def test_mfa_change_phone_updates_the_number(client, kc):
    request_id = verify_until_approved(client, kc, "mfa_change_phone", "priya.nair", new_phone="555-0188")
    issue(client, request_id)
    assert kc.users["priya.nair"].phone == "555-0188"


def test_change_phone_requires_a_new_number(client):
    assert create(client, "mfa_change_phone").status_code == 422


def test_a_second_approval_is_409(client, kc):
    request_id = verify_until_approved(client, kc, "password", "daniel.okafor")
    url = f"/reset-requests/{request_id}/approve"
    assert client.post(url, headers=AUTH_MANAGER).status_code == 200
    assert client.post(url, headers=AUTH_MANAGER).status_code == 409  # already APPROVED


def test_approving_a_blocked_request_is_409(client, kc):
    created = create(client, user="daniel.okafor").json()
    call_back(client, created["id"], "555-9999")  # wrong number -> BLOCKED
    response = client.post(f"/reset-requests/{created['id']}/approve", headers=AUTH_MANAGER)
    assert response.status_code == 409


def test_bearer_scheme_is_case_insensitive(client, kc):
    request_id = verify_until_approved(client, kc, "password", "daniel.okafor")
    response = client.post(f"/reset-requests/{request_id}/approve", headers={"Authorization": "bearer manager-token"})
    assert response.status_code == 200
