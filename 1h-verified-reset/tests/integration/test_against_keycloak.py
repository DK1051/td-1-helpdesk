"""Integration tests against the real local Keycloak (marker: keycloak).

They are skipped automatically when http://localhost:8080/realms/maple-harbour does not
answer 200 (see tests/conftest.py). Start it with scripts/keycloak-dev.sh.
Secrets (TOTP seeds, the manager's password) are read from .dev/ and never printed.
"""

import json
import os
import subprocess
from pathlib import Path

import httpx
import pyotp
import pytest
from app.keycloak import KeycloakClient
from app.main import app, get_store
from app.state import Store
from fastapi.testclient import TestClient

pytestmark = pytest.mark.keycloak

SERVICE_DIR = Path(__file__).resolve().parents[2]
DEV_DIR = SERVICE_DIR / ".dev"
SCRIPT = SERVICE_DIR / "scripts" / "keycloak-dev.sh"
KEYCLOAK_URL = os.environ.get("KEYCLOAK_URL", "http://localhost:8080").rstrip("/")
REALM = os.environ.get("KEYCLOAK_REALM", "maple-harbour")
TOKEN_URL = f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/token"
USERNAMES = ["daniel.okafor", "marcus.chen", "priya.nair", "sofia.alvarez"]


@pytest.fixture
def real_client(tmp_path, monkeypatch):
    """The real service talking to the real Keycloak (only the in-memory store is fresh)."""
    monkeypatch.setenv("AUDIT_LOG_PATH", str(tmp_path / "audit.jsonl"))
    monkeypatch.setenv("ALERTS_LOG_PATH", str(tmp_path / "alerts.jsonl"))
    store = Store()
    app.dependency_overrides[get_store] = lambda: store
    yield TestClient(app)
    app.dependency_overrides.clear()


def current_code(username: str) -> str:
    seeds = json.loads((DEV_DIR / "seeds.json").read_text())
    return pyotp.TOTP(seeds[username]).now()


def manager_token() -> str:
    password = (DEV_DIR / "manager.password").read_text().strip()
    response = httpx.post(
        TOKEN_URL,
        data={
            "grant_type": "password",
            "client_id": "helpdesk-console",
            "username": "marcus.chen",
            "password": password,
        },
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def start_request(client, kind, user):
    body = {"kind": kind, "claimed_username": user, "agent_id": "agent.lee", "channel": "phone"}
    created = client.post("/reset-requests", json=body)
    assert created.status_code == 201
    return created.json()


def verify_identity(client, created, user):
    rid = created["id"]
    client.post(f"/reset-requests/{rid}/callback", json={"number_dialed": created["phone_on_file"], "reached": True})
    return client.post(f"/reset-requests/{rid}/otp", json={"code": current_code(user)}).json()


def test_realm_exists():
    assert httpx.get(f"{KEYCLOAK_URL}/realms/{REALM}").status_code == 200


def test_dev_script_run_again_leaves_the_same_users():
    kc = KeycloakClient()

    def user_names():
        return sorted(u["username"] for u in kc._admin("GET", "/users").json())

    before = user_names()
    run = subprocess.run(["bash", str(SCRIPT)], check=False, capture_output=True, text=True, timeout=120)
    assert run.returncode == 0
    assert user_names() == before == USERNAMES


def test_users_have_the_expected_shape():
    kc = KeycloakClient()
    daniel, sofia = kc.get_user("daniel.okafor"), kc.get_user("sofia.alvarez")
    assert daniel.groups == ["privileged"] and daniel.phone == "555-0104"
    assert kc.has_otp_device("priya.nair") and kc.has_otp_device("daniel.okafor")
    assert sofia.groups == [] and not kc.has_otp_device("sofia.alvarez")


def test_happy_path_regular_user_against_keycloak(real_client):
    created = start_request(real_client, "password", "priya.nair")
    assert created["phone_on_file"] == "555-0101"
    assert verify_identity(real_client, created, "priya.nair")["state"] == "APPROVED"
    done = real_client.post(f"/reset-requests/{created['id']}/issue").json()
    assert done["state"] == "COMPLETED" and len(done["temporary_password"]) >= 16
    # Keycloak now demands a password change at next login.
    assert "UPDATE_PASSWORD" in KeycloakClient().get_user("priya.nair").required_actions


def test_privileged_user_needs_a_real_manager_token(real_client):
    created = start_request(real_client, "password", "daniel.okafor")
    assert verify_identity(real_client, created, "daniel.okafor")["state"] == "AWAITING_APPROVAL"
    url = f"/reset-requests/{created['id']}/approve"
    assert real_client.post(url, headers={"Authorization": "Bearer not-a-real-token"}).status_code == 403
    approved = real_client.post(url, headers={"Authorization": f"Bearer {manager_token()}"})
    assert approved.status_code == 200 and approved.json()["approver"] == "marcus.chen"
    assert real_client.post(f"/reset-requests/{created['id']}/issue").json()["state"] == "COMPLETED"


def test_user_without_device_is_escalated_against_keycloak(real_client):
    created = start_request(real_client, "password", "sofia.alvarez")
    real_client.post(f"/reset-requests/{created['id']}/callback", json={"number_dialed": "555-0103", "reached": True})
    result = real_client.post(f"/reset-requests/{created['id']}/otp", json={"code": "000000"}).json()
    assert result["state"] == "ESCALATED"


def test_a_code_cannot_be_used_twice_against_keycloak(real_client):
    """The real seed produces the code; the second request with the same code is refused (replay)."""
    first = start_request(real_client, "password", "priya.nair")
    real_client.post(
        f"/reset-requests/{first['id']}/callback", json={"number_dialed": first["phone_on_file"], "reached": True}
    )
    code = current_code("priya.nair")
    assert real_client.post(f"/reset-requests/{first['id']}/otp", json={"code": code}).json()["state"] == "APPROVED"

    second = start_request(real_client, "password", "priya.nair")
    real_client.post(
        f"/reset-requests/{second['id']}/callback", json={"number_dialed": second["phone_on_file"], "reached": True}
    )
    replay = real_client.post(f"/reset-requests/{second['id']}/otp", json={"code": code}).json()
    assert replay["state"] == "CALLBACK_DONE" and replay["otp_attempts_left"] == 2
