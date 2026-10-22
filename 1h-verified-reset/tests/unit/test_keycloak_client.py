"""KeycloakClient behaviour with a pretend HTTP server (httpx.MockTransport): no real Keycloak."""

import httpx
import pytest
from app.keycloak import KeycloakClient, KeycloakError


def client_with(handler, monkeypatch) -> KeycloakClient:
    monkeypatch.setenv("RESET_SERVICE_SECRET", "not-a-real-secret")
    kc = KeycloakClient()
    kc._http = httpx.Client(transport=httpx.MockTransport(handler))
    return kc


def introspection(body):
    return lambda request: httpx.Response(200, json=body)


GOOD = {"active": True, "preferred_username": "marcus.chen", "aud": ["reset-service"], "typ": "Bearer",
        "realm_access": {"roles": ["manager"]}}  # fmt: skip


def test_introspect_accepts_a_token_meant_for_this_service(monkeypatch):
    info = client_with(introspection(GOOD), monkeypatch).introspect("t")
    assert info.username == "marcus.chen" and info.realm_roles == ["manager"]


@pytest.mark.parametrize(
    "change",
    [{"active": False}, {"aud": "someone-else"}, {"aud": None}, {"typ": "ID"}, {"preferred_username": None}],
)
def test_introspect_rejects_tokens_that_are_not_for_this_service(monkeypatch, change):
    assert client_with(introspection({**GOOD, **change}), monkeypatch).introspect("t") is None


def test_introspect_accepts_audience_as_a_plain_string(monkeypatch):
    assert client_with(introspection({**GOOD, "aud": "reset-service"}), monkeypatch).introspect("t") is not None


def test_connection_errors_become_a_short_keycloakerror(monkeypatch):
    def refuse(request):
        raise httpx.ConnectError("connection refused to somewhere secret")

    with pytest.raises(KeycloakError) as caught:
        client_with(refuse, monkeypatch).introspect("t")
    assert str(caught.value) == "network"


def test_token_response_without_access_token_is_a_clean_error(monkeypatch):
    kc = client_with(lambda request: httpx.Response(200, json={"oops": 1}), monkeypatch)
    with pytest.raises(KeycloakError) as caught:
        kc.get_user("priya.nair")
    assert str(caught.value) == "bad_token_response"


def test_error_labels_never_contain_user_ids(monkeypatch):
    user_id = "0f8fad5b-d9cb-469f-a165-70867728950e"

    def handler(request):
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "x", "expires_in": 60})
        return httpx.Response(500, json={"detail": user_id})

    kc = client_with(handler, monkeypatch)
    with pytest.raises(KeycloakError) as caught:
        kc._admin("PUT", f"/users/{user_id}/reset-password")
    assert user_id not in str(caught.value)
    assert str(caught.value) == "PUT /users/{id}/reset-password -> 500"
