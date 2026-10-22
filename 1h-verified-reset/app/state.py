"""The reset state machine and the in-memory store.

Normal path:
  OPEN -> CALLBACK_DONE -> OTP_VERIFIED -> (AWAITING_APPROVAL ->) APPROVED -> COMPLETED
Dead ends: BLOCKED (verification failed), ESCALATED (needs a human process).

Each step may only be taken from one state (REQUIRED_STATE). Anything else is
"out of order" and main.py answers HTTP 409.
"""

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

from . import clock
from .models import Kind


class State(str, Enum):
    OPEN = "OPEN"
    CALLBACK_DONE = "CALLBACK_DONE"
    OTP_VERIFIED = "OTP_VERIFIED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    ESCALATED = "ESCALATED"


# The only state each step may be called from.
REQUIRED_STATE = {
    "callback": State.OPEN,
    "otp": State.CALLBACK_DONE,
    "approve": State.AWAITING_APPROVAL,
    "issue": State.APPROVED,
}

MAX_OTP_ATTEMPTS = 3
TEMP_PASSWORD_LIFETIME = timedelta(minutes=60)
WATCH_WINDOW = timedelta(hours=24)


@dataclass
class ResetRequest:
    kind: Kind
    username: str
    agent_id: str
    channel: str
    phone_on_file: str | None = None
    new_phone: str | None = None
    is_privileged: bool = False
    # True when rule 5 forces a manager to approve even a regular user.
    forced_approval: bool = False
    state: State = State.OPEN
    reason: str | None = None
    approver: str | None = None
    otp_failures: int = 0
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: datetime = field(default_factory=clock.now)
    completed_at: datetime | None = None
    history: list[dict] = field(default_factory=list)

    @property
    def needs_approval(self) -> bool:
        return self.is_privileged or self.forced_approval

    def move_to(self, new_state: State, action: str, reason: str | None = None) -> None:
        """Change state and remember when and why. Never stores secrets."""
        self.state = new_state
        self.reason = reason
        self.history.append(
            {"ts": clock.now().isoformat(), "action": action, "state": new_state.value, "reason": reason}
        )
        if new_state == State.COMPLETED:
            self.completed_at = clock.now()

    def public_view(self) -> dict:
        """What GET returns. No codes, tokens, passwords or seeds."""
        return {
            "id": self.id,
            "kind": self.kind.value,
            "claimed_username": self.username,
            "agent_id": self.agent_id,
            "channel": self.channel,
            "state": self.state.value,
            "reason": self.reason,
            "needs_approval": self.needs_approval,
            "approver": self.approver,
            "otp_attempts_left": max(MAX_OTP_ATTEMPTS - self.otp_failures, 0),
            "created_at": self.created_at.isoformat(),
            "history": self.history,
        }


@dataclass
class TempPassword:
    """Bookkeeping for one issued temporary password. The value is NOT kept."""

    request_id: str
    username: str
    issued_at: datetime
    expires_at: datetime
    rotated_at: datetime | None = None
    # True once the same user was issued a newer temporary password: only the latest one is rotated.
    superseded: bool = False


class Store:
    """All requests live in memory: a lab, not a product. A restart forgets them."""

    def __init__(self) -> None:
        self.requests: dict[str, ResetRequest] = {}
        self.temp_passwords: list[TempPassword] = []
        # Newest one-time-code time step accepted per user; a code from that step or an older one is a replay.
        self.last_otp_step: dict[str, int] = {}
        # Held by each step handler for its whole body (see main.py).
        self.lock = threading.Lock()

    def add(self, request: ResetRequest) -> ResetRequest:
        self.requests[request.id] = request
        return request

    def get(self, request_id: str) -> ResetRequest | None:
        return self.requests.get(request_id)

    def add_temp_password(self, item: TempPassword) -> None:
        for older in self.temp_passwords:
            if older.username == item.username:
                older.superseded = True
        self.temp_passwords.append(item)

    def recent_password_reset(self, username: str) -> ResetRequest | None:
        """The latest COMPLETED password reset for this user within the last 24 h, if any."""
        cutoff = clock.now() - WATCH_WINDOW
        done = [
            r
            for r in self.requests.values()
            if r.username == username
            and r.kind == Kind.password
            and r.state == State.COMPLETED
            and r.completed_at is not None
            and r.completed_at >= cutoff
        ]
        return max(done, key=lambda r: r.completed_at, default=None)
