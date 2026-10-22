from datetime import UTC, datetime

import pytest
from app import clock
from app.main import app, get_keycloak, get_store
from app.state import Store
from fake_keycloak import FakeKeycloak
from fastapi.testclient import TestClient
from flows import GOOD_CODE

START = datetime(2026, 10, 22, 9, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Fresh log files and a frozen clock for every test."""
    monkeypatch.setenv("AUDIT_LOG_PATH", str(tmp_path / "audit.jsonl"))
    monkeypatch.setenv("ALERTS_LOG_PATH", str(tmp_path / "alerts.jsonl"))
    clock.freeze(START)
    yield
    clock.unfreeze()


@pytest.fixture
def kc() -> FakeKeycloak:
    fake = FakeKeycloak()
    fake.add_user("priya.nair", "555-0101", otp_code=GOOD_CODE)  # regular, has a device
    fake.add_user("daniel.okafor", "555-0104", groups=["privileged"], otp_code=GOOD_CODE)
    fake.add_user("sofia.alvarez", "555-0103")  # regular, NO device
    fake.add_user("marcus.chen", "555-0102")
    fake.add_token("manager-token", "marcus.chen", roles=["manager"])
    fake.add_token("regular-token", "priya.nair", roles=["offline_access"])
    return fake


@pytest.fixture
def client(kc):
    store = Store()
    app.dependency_overrides[get_keycloak] = lambda: kc
    app.dependency_overrides[get_store] = lambda: store
    yield TestClient(app)
    app.dependency_overrides.clear()
