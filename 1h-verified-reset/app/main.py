"""Verified Reset Service: the web endpoints.

A helpdesk agent drives one reset request through fixed steps:
  create -> callback -> otp -> (approve, privileged only) -> issue
Each step checks the request is in the right state, or answers 409 and logs
"out_of_order". Every decision is written to the audit log.

Run from 1h-verified-reset/:  uvicorn app.main:app --port 8000
"""

import functools
import secrets
import string

from fastapi import Depends, FastAPI, Header, HTTPException

from . import audit, clock
from .keycloak import KeycloakClient, KeycloakError
from .models import MFA_KINDS, CallbackBody, CreateResetRequest, Kind, MfaChangeEvent, OtpBody
from .state import (
    MAX_OTP_ATTEMPTS,
    REQUIRED_STATE,
    TEMP_PASSWORD_LIFETIME,
    ResetRequest,
    State,
    Store,
    TempPassword,
)

app = FastAPI(title="Verified Reset Service (lab)")

_store = Store()


@functools.lru_cache
def _real_keycloak() -> KeycloakClient:
    return KeycloakClient()  # no network call until first use


def get_keycloak():
    """Tests replace this with FakeKeycloak via app.dependency_overrides."""
    return _real_keycloak()


def get_store() -> Store:
    return _store


# ---- small helpers -----------------------------------------------------------
def log(req: ResetRequest | None, actor: str, action: str, outcome: str, **details) -> None:
    audit.record(
        {
            "request_id": req.id if req else None,
            "actor": actor,
            "action": action,
            "outcome": outcome,
            "details": details,
        }
    )


def find_request(store: Store, request_id: str) -> ResetRequest:
    req = store.get(request_id)
    if req is None:
        raise HTTPException(404, "unknown request id")
    return req


def require_step(req: ResetRequest, step: str, actor: str) -> None:
    """Refuse (409 + audit line) if this step is not allowed from the current state."""
    if req.state != REQUIRED_STATE[step]:
        log(req, actor, step, "out_of_order", expected=REQUIRED_STATE[step].value, actual=req.state.value)
        raise HTTPException(409, f"{step} is not allowed while the request is {req.state.value}")


def block(req: ResetRequest, actor: str, action: str, reason: str) -> dict:
    req.move_to(State.BLOCKED, action, reason)
    log(req, actor, action, "blocked", reason=reason)
    return req.public_view()


def bearer_token(authorization: str | None) -> str:
    """'Bearer abc' -> 'abc'; anything else -> '' (treated as no token)."""
    if authorization and authorization.startswith("Bearer "):
        return authorization[len("Bearer ") :].strip()
    return ""


def random_password() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(16))


def keycloak_call(req: ResetRequest | None, actor: str, action: str, fn, *args, **kwargs):
    """Run a Keycloak call; on failure log only the short error label and answer 502."""
    try:
        return fn(*args, **kwargs)
    except KeycloakError as e:
        log(req, actor, action, "keycloak_error", error=str(e))
        raise HTTPException(502, "identity provider error") from None


def alert_if_after_password_reset(store: Store, username: str, change: str, source: str, request_id=None) -> bool:
    """Rule 5: an MFA change within 24 h after a completed password reset raises an alert."""
    reset = store.recent_password_reset(username)
    if reset is None:
        return False
    alert = audit.record_alert(
        {
            "reason": "mfa_change_within_24h_of_password_reset",
            "username": username,
            "change": change,
            "source": source,
            "request_id": request_id,
            "password_reset_request_id": reset.id,
            "password_reset_completed_at": reset.completed_at.isoformat(),
        }
    )
    log(None, "system", "alert", "raised", username=username, change=change, alert_ts=alert["ts"])
    return True


# ---- endpoints -----------------------------------------------------------------
@app.post("/reset-requests", status_code=201)
def create_request(body: CreateResetRequest, kc=Depends(get_keycloak), store: Store = Depends(get_store)):
    if body.kind == Kind.mfa_change_phone and body.new_phone is None:
        raise HTTPException(422, "new_phone is required for mfa_change_phone")
    username = body.claimed_username.strip().lower()
    user = keycloak_call(None, body.agent_id, "create", kc.get_user, username)
    req = store.add(
        ResetRequest(
            kind=body.kind, username=username, agent_id=body.agent_id, channel=body.channel, new_phone=body.new_phone
        )
    )
    if user is None:
        return block(req, body.agent_id, "create", "unknown_user")

    req.phone_on_file = user.phone
    req.is_privileged = "privileged" in user.groups
    if body.kind in MFA_KINDS and alert_if_after_password_reset(
        store, username, f"request:{body.kind.value}", "reset-service", req.id
    ):
        req.forced_approval = True
    req.move_to(State.OPEN, "create")
    log(req, body.agent_id, "create", "ok", kind=body.kind.value, needs_approval=req.needs_approval)
    # The agent needs the number to dial; the callback itself happens outside the service.
    return {**req.public_view(), "phone_on_file": req.phone_on_file}


@app.get("/reset-requests/{request_id}")
def get_request(request_id: str, store: Store = Depends(get_store)):
    return find_request(store, request_id).public_view()


@app.post("/reset-requests/{request_id}/callback")
def callback(request_id: str, body: CallbackBody, store: Store = Depends(get_store)):
    req = find_request(store, request_id)
    require_step(req, "callback", req.agent_id)
    if body.number_dialed != req.phone_on_file:  # any other number is refused, even if someone answered
        return block(req, req.agent_id, "callback", "callback_wrong_number")
    if not body.reached:
        return block(req, req.agent_id, "callback", "callback_not_reached")
    req.move_to(State.CALLBACK_DONE, "callback")
    log(req, req.agent_id, "callback", "ok")
    return req.public_view()


@app.post("/reset-requests/{request_id}/otp")
def check_otp(request_id: str, body: OtpBody, kc=Depends(get_keycloak), store: Store = Depends(get_store)):
    req = find_request(store, request_id)
    actor = req.agent_id
    require_step(req, "otp", actor)
    if not keycloak_call(req, actor, "otp", kc.has_otp_device, req.username):
        req.move_to(State.ESCALATED, "otp", "no_registered_device")
        log(req, actor, "otp", "escalated", reason="no_registered_device")
        return req.public_view()
    if not keycloak_call(req, actor, "otp", kc.verify_otp, req.username, body.code):
        req.otp_failures += 1
        if req.otp_failures >= MAX_OTP_ATTEMPTS:
            return block(req, actor, "otp", "otp_failed")
        log(req, actor, "otp", "wrong_code", attempts_left=MAX_OTP_ATTEMPTS - req.otp_failures)
        return req.public_view()  # state unchanged: the agent may try again
    req.move_to(State.OTP_VERIFIED, "otp")
    if req.needs_approval:
        req.move_to(State.AWAITING_APPROVAL, "otp", "forced_approval" if not req.is_privileged else "privileged")
    else:
        req.move_to(State.APPROVED, "otp")
    log(req, actor, "otp", "ok", next_state=req.state.value)
    return req.public_view()


@app.post("/reset-requests/{request_id}/approve")
def approve(
    request_id: str,
    authorization: str | None = Header(default=None),
    kc=Depends(get_keycloak),
    store: Store = Depends(get_store),
):
    req = find_request(store, request_id)
    token = bearer_token(authorization)
    who = keycloak_call(req, "unknown", "approve", kc.introspect, token) if token else None
    if who is None:
        log(req, "unknown", "approve", "refused", reason="invalid_token")
        raise HTTPException(403, "valid manager token required")
    if "manager" not in who.realm_roles:
        log(req, who.username, "approve", "refused", reason="not_a_manager")
        raise HTTPException(403, "approver must have the manager role")
    if who.username.lower() == req.username:
        log(req, who.username, "approve", "refused", reason="self_approval")
        raise HTTPException(403, "nobody can approve their own request")
    require_step(req, "approve", who.username)
    req.approver = who.username
    req.move_to(State.APPROVED, "approve")
    log(req, who.username, "approve", "ok")
    return req.public_view()


@app.post("/reset-requests/{request_id}/issue")
def issue(request_id: str, kc=Depends(get_keycloak), store: Store = Depends(get_store)):
    req = find_request(store, request_id)
    actor = req.agent_id
    require_step(req, "issue", actor)
    result: dict = {}

    if req.kind == Kind.password:
        password = random_password()
        keycloak_call(req, actor, "issue", kc.set_password, req.username, password, True)
        now = clock.now()
        expires_at = now + TEMP_PASSWORD_LIFETIME
        store.temp_passwords.append(TempPassword(req.id, req.username, now, expires_at))
        # The only place the password is ever returned. It is not stored or logged.
        result = {"temporary_password": password, "expires_at": expires_at.isoformat()}
        details = {"temporary_password_issued": True, "expires_at": expires_at.isoformat()}
    elif req.kind == Kind.mfa_reset:
        keycloak_call(req, actor, "issue", kc.remove_otp_device, req.username)
        details = {"otp_removed": True}
    elif req.kind == Kind.mfa_enrol_device:
        keycloak_call(req, actor, "issue", kc.require_totp_setup, req.username)
        details = {"totp_setup_required": True}
    else:  # mfa_change_phone
        keycloak_call(req, actor, "issue", kc.set_phone, req.username, req.new_phone)
        details = {"phone_updated": True}

    req.move_to(State.COMPLETED, "issue")
    log(req, actor, "issue", "ok", kind=req.kind.value, **details)
    return {**req.public_view(), **result}


@app.post("/mfa-change-events")
def mfa_change_event(body: MfaChangeEvent, store: Store = Depends(get_store)):
    """An MFA change seen outside this service (in the lab, tests and the demo send these)."""
    username = body.username.strip().lower()
    log(None, body.source, "mfa_change_event", "recorded", username=username, change=body.change)
    alerted = alert_if_after_password_reset(store, username, body.change, body.source)
    return {"alerted": alerted}


@app.get("/alerts")
def list_alerts():
    return audit.read_alerts()


@app.post("/maintenance/expire-temp-passwords")
def expire_temp_passwords(kc=Depends(get_keycloak), store: Store = Depends(get_store)):
    """Keycloak's 'temporary' flag only forces a change at next login; it is not a timer.
    So this job rotates any temporary password that is 60+ minutes old to a random value nobody is told."""
    rotated = []
    for item in store.temp_passwords:
        if item.rotated_at is not None or clock.now() < item.expires_at:
            continue
        user = keycloak_call(None, "system", "expire", kc.get_user, item.username)
        item.rotated_at = clock.now()
        if user is None or "UPDATE_PASSWORD" not in user.required_actions:
            # The user already chose their own password; rotating would lock them out.
            log(None, "system", "temp_password_expiry", "skipped", request_id=item.request_id, reason="already_changed")
            continue
        keycloak_call(None, "system", "expire", kc.set_password, item.username, random_password(), True)
        log(None, "system", "temp_password_expiry", "rotated", request_id=item.request_id)
        rotated.append(item.request_id)
    return {"rotated": rotated}
