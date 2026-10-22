"""Shared pytest setup: skip Keycloak-dependent tests when the dev realm is not running."""

import os

import httpx
import pytest

# Same variables the service uses, so one setting moves both.
KEYCLOAK_URL = os.environ.get("KEYCLOAK_URL", "http://localhost:8080").rstrip("/")
REALM_URL = f"{KEYCLOAK_URL}/realms/{os.environ.get('KEYCLOAK_REALM', 'maple-harbour')}"


def _realm_is_up() -> bool:
    try:
        return httpx.get(REALM_URL, timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


def pytest_collection_modifyitems(config, items):
    keycloak_tests = [item for item in items if "keycloak" in item.keywords]
    if keycloak_tests and not _realm_is_up():
        skip = pytest.mark.skip(reason=f"Keycloak realm not reachable at {REALM_URL}; run scripts/keycloak-dev.sh")
        for item in keycloak_tests:
            item.add_marker(skip)
