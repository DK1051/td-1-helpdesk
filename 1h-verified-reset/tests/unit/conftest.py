from datetime import UTC, datetime

import pytest
from app import clock
from app.fake_keycloak import FakeKeycloak, dev_users_fake
from app.main import app, get_keycloak, get_store
from app.state import Store
from fastapi.testclient import TestClient

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
    return dev_users_fake()


@pytest.fixture
def client(kc):
    store = Store()
    app.dependency_overrides[get_keycloak] = lambda: kc
    app.dependency_overrides[get_store] = lambda: store
    test_client = TestClient(app)
    test_client.kc = kc  # lets the helpers in flows.py fetch a fresh correct code
    yield test_client
    app.dependency_overrides.clear()
