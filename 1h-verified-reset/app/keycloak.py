"""Talks to Keycloak (the lab's stand-in for the company login system).

Everything the service needs from Keycloak is a method on KeycloakClient. The unit
tests use FakeKeycloak, which has the same methods, so no server is needed.

Safety: errors carry only an HTTP status code, never Keycloak's response body
(bodies can contain object IDs and this repo's CI logs are public).

D1 (dev only): Keycloak has no API that says "is this 6-digit code right for user X".
So the dev script keeps a copy of each test user's TOTP seed in .dev/seeds.json and
we check codes with pyotp. A real deployment must never hold seeds outside the
identity provider.
"""

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import pyotp

DEV_DIR = Path(__file__).resolve().parent.parent / ".dev"


class KeycloakError(Exception):
    """A Keycloak call failed. Message is a status code or short label only."""


@dataclass
class UserInfo:
    id: str
    username: str
    phone: str | None
    groups: list[str] = field(default_factory=list)
    required_actions: list[str] = field(default_factory=list)


@dataclass
class TokenInfo:
    username: str
    realm_roles: list[str]


class KeycloakClient:
    def __init__(self) -> None:
        self.base = os.environ.get("KEYCLOAK_URL", "http://localhost:8080").rstrip("/")
        self.realm = os.environ.get("KEYCLOAK_REALM", "maple-harbour")
        self.client_id = os.environ.get("KEYCLOAK_CLIENT_ID", "reset-service")
        self.seeds_path = Path(os.environ.get("SEEDS_PATH", DEV_DIR / "seeds.json"))
        self._secret_path = Path(os.environ.get("CLIENT_SECRET_PATH", DEV_DIR / "reset-service.secret"))
        self._http = httpx.Client(timeout=10)
        self._admin_token: str | None = None
        self._admin_token_expires = 0.0

    # ---- plumbing -------------------------------------------------------
    def _client_secret(self) -> str:
        secret = os.environ.get("RESET_SERVICE_SECRET")
        if secret:
            return secret
        try:
            return self._secret_path.read_text().strip()
        except OSError:
            raise KeycloakError("client_secret_missing") from None

    def _token(self) -> str:
        """Token for the service's own Keycloak account (client-credentials grant)."""
        if self._admin_token and time.monotonic() < self._admin_token_expires:
            return self._admin_token
        resp = self._http.post(
            f"{self.base}/realms/{self.realm}/protocol/openid-connect/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self._client_secret(),
            },
        )
        if resp.status_code != 200:
            raise KeycloakError(f"token_{resp.status_code}")
        body = resp.json()
        self._admin_token = body["access_token"]
        self._admin_token_expires = time.monotonic() + body.get("expires_in", 60) - 10
        return self._admin_token

    def _admin(self, method: str, path: str, **kwargs) -> httpx.Response:
        url = f"{self.base}/admin/realms/{self.realm}{path}"
        resp = self._http.request(method, url, headers={"Authorization": f"Bearer {self._token()}"}, **kwargs)
        if resp.status_code >= 400:
            raise KeycloakError(f"{method} {path.split('?')[0]} -> {resp.status_code}")
        return resp

    def _raw_user(self, username: str) -> dict | None:
        found = self._admin("GET", "/users", params={"username": username, "exact": "true"}).json()
        return found[0] if found else None

    def _require_user(self, username: str) -> dict:
        user = self._raw_user(username)
        if user is None:
            raise KeycloakError("user_not_found")
        return user

    # ---- lookups ----------------------------------------------------------
    def get_user(self, username: str) -> UserInfo | None:
        raw = self._raw_user(username)
        if raw is None:
            return None
        groups = self._admin("GET", f"/users/{raw['id']}/groups").json()
        phones = (raw.get("attributes") or {}).get("phone") or [None]
        return UserInfo(
            id=raw["id"],
            username=raw["username"],
            phone=phones[0],
            groups=[g["name"] for g in groups],
            required_actions=raw.get("requiredActions") or [],
        )

    def introspect(self, token: str) -> TokenInfo | None:
        """Ask Keycloak whether a login token is still valid and whose it is (D2a)."""
        resp = self._http.post(
            f"{self.base}/realms/{self.realm}/protocol/openid-connect/token/introspect",
            data={"token": token},
            auth=(self.client_id, self._client_secret()),
        )
        if resp.status_code != 200:
            raise KeycloakError(f"introspect_{resp.status_code}")
        body = resp.json()
        if not body.get("active"):
            return None
        username = body.get("preferred_username") or body.get("username")
        if not username:
            return None
        return TokenInfo(username=username, realm_roles=(body.get("realm_access") or {}).get("roles", []))

    # ---- one-time codes (D1, dev copy of seeds) ----------------------------
    def _seeds(self) -> dict[str, str]:
        try:
            return json.loads(self.seeds_path.read_text())
        except (OSError, ValueError):
            return {}

    def has_otp_device(self, username: str) -> bool:
        return username in self._seeds()

    def verify_otp(self, username: str, code: str) -> bool:
        seed = self._seeds().get(username)
        if seed is None or not code.isdigit():
            return False
        return pyotp.TOTP(seed).verify(code, valid_window=1)  # allows one 30-second step of clock drift

    # ---- changes ------------------------------------------------------------
    def set_password(self, username: str, password: str, temporary: bool) -> None:
        user = self._require_user(username)
        self._admin(
            "PUT",
            f"/users/{user['id']}/reset-password",
            json={"type": "password", "value": password, "temporary": temporary},
        )

    def remove_otp_device(self, username: str) -> None:
        """Delete the user's OTP credentials in Keycloak and the dev seed copy."""
        user = self._require_user(username)
        for cred in self._admin("GET", f"/users/{user['id']}/credentials").json():
            if cred.get("type") == "otp":
                self._admin("DELETE", f"/users/{user['id']}/credentials/{cred['id']}")
        seeds = self._seeds()
        if seeds.pop(username, None) is not None:
            self.seeds_path.write_text(json.dumps(seeds))

    def require_totp_setup(self, username: str) -> None:
        """Make Keycloak ask the user to set up an authenticator app at next login."""
        user = self._require_user(username)
        actions = sorted(set(user.get("requiredActions") or []) | {"CONFIGURE_TOTP"})
        self._admin("PUT", f"/users/{user['id']}", json={**user, "requiredActions": actions})

    def set_phone(self, username: str, phone: str) -> None:
        user = self._require_user(username)
        attributes = {**(user.get("attributes") or {}), "phone": [phone]}
        self._admin("PUT", f"/users/{user['id']}", json={**user, "attributes": attributes})
