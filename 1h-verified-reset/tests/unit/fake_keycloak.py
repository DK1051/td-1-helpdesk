"""An in-memory stand-in for app.keycloak.KeycloakClient (same methods, no server)."""

from app.keycloak import TokenInfo, UserInfo


class FakeKeycloak:
    def __init__(self) -> None:
        self.users: dict[str, UserInfo] = {}
        self.otp_codes: dict[str, str] = {}  # username -> the one currently valid code
        self.tokens: dict[str, TokenInfo] = {}  # bearer token -> who it belongs to
        self.password_history: list[tuple[str, str, bool]] = []  # (username, password, temporary)
        self.totp_setup_requested: list[str] = []

    # test setup helpers
    def add_user(self, username, phone, groups=(), otp_code=None) -> None:
        self.users[username] = UserInfo(id=f"id-{username}", username=username, phone=phone, groups=list(groups))
        if otp_code:
            self.otp_codes[username] = otp_code

    def add_token(self, token, username, roles=()) -> None:
        self.tokens[token] = TokenInfo(username=username, realm_roles=list(roles))

    def user_changed_own_password(self, username) -> None:
        self.users[username].required_actions.remove("UPDATE_PASSWORD")

    # same interface as KeycloakClient
    def get_user(self, username):
        return self.users.get(username)

    def introspect(self, token):
        return self.tokens.get(token)

    def has_otp_device(self, username) -> bool:
        return username in self.otp_codes

    def verify_otp(self, username, code) -> bool:
        return self.otp_codes.get(username) == code

    def set_password(self, username, password, temporary) -> None:
        self.password_history.append((username, password, temporary))
        actions = self.users[username].required_actions
        if temporary and "UPDATE_PASSWORD" not in actions:
            actions.append("UPDATE_PASSWORD")

    def remove_otp_device(self, username) -> None:
        self.otp_codes.pop(username, None)

    def require_totp_setup(self, username) -> None:
        self.totp_setup_requested.append(username)

    def set_phone(self, username, phone) -> None:
        self.users[username].phone = phone
