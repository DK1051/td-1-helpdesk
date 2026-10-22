"""An in-memory stand-in for app.keycloak.KeycloakClient (same methods, no server).

Used by the unit tests and by the offline mode of the replay runner (app/replay.py).
"""

import time

from .keycloak import KeycloakError, TokenInfo, UserInfo


class FakeKeycloak:
    def __init__(self) -> None:
        self.users: dict[str, UserInfo] = {}
        self.devices: set[str] = set()  # users who have a registered code device
        self.current_step = 1000  # the fake "clock" for one-time codes (one step = 30 seconds)
        self.tokens: dict[str, TokenInfo] = {}  # bearer token -> who it belongs to
        self.password_history: list[tuple[str, str, bool]] = []  # (username, password, temporary)
        self.totp_setup_requested: list[str] = []
        self.down = False  # True: get_user fails like a network error
        self.fail_set_password = False
        self.otp_delay = 0.0  # seconds; widens the race window in the concurrency test

    # test setup helpers
    def add_user(self, username, phone, groups=(), device=False) -> None:
        self.users[username] = UserInfo(id=f"id-{username}", username=username, phone=phone, groups=list(groups))
        if device:
            self.devices.add(username)

    # A code is just its time step written as six digits, e.g. step 1001 -> "001001".
    # Like a real authenticator, the fake accepts the current step and one step either side.
    def code(self, offset=0) -> str:
        return f"{self.current_step + offset:06d}"

    def fresh_code(self) -> str:
        """A correct code from a newer step than any used before."""
        self.current_step += 1
        return self.code()

    def tick(self) -> None:
        """30 seconds pass."""
        self.current_step += 1

    def add_token(self, token, username, roles=()) -> None:
        self.tokens[token] = TokenInfo(username=username, realm_roles=list(roles))

    def user_changed_own_password(self, username) -> None:
        self.users[username].required_actions.remove("UPDATE_PASSWORD")

    # same interface as KeycloakClient
    def get_user(self, username):
        if self.down:
            raise KeycloakError("network")
        return self.users.get(username)

    def introspect(self, token):
        return self.tokens.get(token)

    def has_otp_device(self, username) -> bool:
        return username in self.devices

    def verify_otp(self, username, code):
        time.sleep(self.otp_delay)
        if username not in self.devices or not (code.isascii() and code.isdigit()):
            return None
        step = int(code)
        return step if abs(step - self.current_step) <= 1 else None

    def set_password(self, username, password, temporary) -> None:
        if self.fail_set_password:
            raise KeycloakError("PUT /users/{id}/reset-password -> 500")
        self.password_history.append((username, password, temporary))
        actions = self.users[username].required_actions
        if temporary and "UPDATE_PASSWORD" not in actions:
            actions.append("UPDATE_PASSWORD")

    def remove_otp_device(self, username) -> None:
        self.devices.discard(username)

    def require_totp_setup(self, username) -> None:
        self.totp_setup_requested.append(username)

    def set_phone(self, username, phone) -> None:
        self.users[username].phone = phone


def dev_users_fake() -> FakeKeycloak:
    """The four dev users of keycloak-dev.sh (same names, groups, phones and devices)."""
    fake = FakeKeycloak()
    fake.add_user("priya.nair", "555-0101", device=True)  # regular, has a code device
    fake.add_user("daniel.okafor", "555-0104", groups=["privileged"], device=True)
    fake.add_user("sofia.alvarez", "555-0103")  # regular, NO code device
    fake.add_user("marcus.chen", "555-0102")  # the manager
    fake.add_token("manager-token", "marcus.chen", roles=["manager"])
    fake.add_token("regular-token", "priya.nair", roles=["offline_access"])
    return fake
