"""Verified Reset Service: the web endpoints.

A helpdesk agent drives one reset request through fixed steps:
  create -> callback -> otp -> (approve, privileged only) -> issue
Each step checks the request is in the right state, or answers 409 and logs
"out_of_order". Every decision is written to the audit log.

Run from 1h-verified-reset/:  uvicorn app.main:app --port 8000
"""

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
_client: KeycloakClient | None = None


def get_keycloak():
    """Build the real Keycloak client on first use. Tests replace this with FakeKeycloak
    through app.dependency_overrides."""
    global _client
    if _client is None:
        _client = KeycloakClient()  # makes no network call until first use
    return _client


def get_store() -> Store:
    return _store


# Concurrency: every step handler below runs entirely inside `with store.lock:`, so two
# parallel calls on the same request cannot both pass a state check (which would let
# someone beat the 3-try limit or skip a step). Simple and slow is fine for a lab.


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
    """End a request as BLOCKED. A stopped identity request is also an alert (once, since BLOCKED is final)."""
    req.move_to(State.BLOCKED, action, reason)
    log(req, actor, action, "blocked", reason=reason)
    raise_alert(
        req,
        {
            "reason": "blocked_identity_request",
            "username": req.username,
            "kind": req.kind.value,
            "blocked_because": reason,
            "agent_id": req.agent_id,
        },
    )
    return req.public_view()


def bearer_token(authorization: str | None) -> str:
    """'Bearer abc' -> 'abc'; anything else -> '' (treated as no token)."""
    if authorization and authorization[:7].lower() == "bearer ":  # the scheme name is case-insensitive
        return authorization[7:].strip()
    return ""


def random_password() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(16))


def keycloak_call(req: ResetRequest | None, actor: str, action: str, fn, *args, **kwargs):
    """Run a Keycloak call. On any failure (including network errors) log only the short
    error label and answer 502, never a traceback."""
    try:
        return fn(*args, **kwargs)
    except KeycloakError as e:
        log(req, actor, action, "keycloak_error", error=str(e))
        raise HTTPException(502, "identity provider error") from None


def raise_alert(req: ResetRequest | None, alert: dict) -> None:
    """Write the alert to alerts.jsonl and note it in the audit log."""
    alert = audit.record_alert({"request_id": req.id if req else None, **alert})
    log(req, "system", "alert", "raised", alert=alert["reason"], username=alert["username"])


def alert_if_after_password_reset(store: Store, username: str, change: str, source: str, request_id=None) -> bool:
    """Rule 5: an MFA change within 24 h after a completed password reset raises an alert."""
    reset = store.recent_password_reset(username)
    if reset is None:
        return False
    raise_alert(
        None if request_id is None else store.get(request_id),
        {
            "reason": "mfa_change_within_24h_of_password_reset",
            "username": username,
            "requested_change": change,
            "source": source,
            "password_reset_request_id": reset.id,
            "password_reset_completed_at": reset.completed_at.isoformat(),
        },
    )
    return True


def apply_rule5(store: Store, req: ResetRequest) -> bool:
    """Rule 5 for an MFA-kind request: if the user had a password reset completed in the last
    24 h, write one alert and force a manager's approval. Called at create, at the code step
    and at issue, because the reset can complete while this request is already open.
    Returns True only the first time it applies, so a request alerts once."""
    if req.kind not in MFA_KINDS or req.forced_approval:
        return False
    if alert_if_after_password_reset(store, req.username, req.kind.value, "reset-service", req.id):
        req.forced_approval = True
        return True
    return False


# ---- endpoints -----------------------------------------------------------------
@app.post("/reset-requests", status_code=201)
def create_request(body: CreateResetRequest, kc=Depends(get_keycloak), store: Store = Depends(get_store)):
    if body.kind == Kind.mfa_change_phone and body.new_phone is None:
        raise HTTPException(422, "new_phone is required for mfa_change_phone")
    username = body.claimed_username.strip().lower()
    with store.lock:
        user = keycloak_call(None, body.agent_id, "create", kc.get_user, username)
        req = store.add(
            ResetRequest(
                kind=body.kind,
                username=username,
                agent_id=body.agent_id,
                channel=body.channel,
                new_phone=body.new_phone,
            )
        )
        if user is None:
            return block(req, body.agent_id, "create", "unknown_user")
        if not user.phone:  # without a number on file there is nobody to call back
            return block(req, body.agent_id, "create", "no_phone_on_file")

        req.phone_on_file = user.phone
        req.is_privileged = "privileged" in user.groups
        apply_rule5(store, req)
        req.move_to(State.OPEN, "create")
        log(req, body.agent_id, "create", "ok", kind=body.kind.value, needs_approval=req.needs_approval)
        # The agent needs the number to dial; the callback itself happens outside the service.
        return {**req.public_view(), "phone_on_file": req.phone_on_file}


@app.get("/reset-requests/{request_id}")
def get_request(request_id: str, store: Store = Depends(get_store)):
    with store.lock:
        return find_request(store, request_id).public_view()


@app.post("/reset-requests/{request_id}/callback")
def callback(request_id: str, body: CallbackBody, store: Store = Depends(get_store)):
    with store.lock:
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
    with store.lock:
        req = find_request(store, request_id)
        actor = req.agent_id
        require_step(req, "otp", actor)
        if not keycloak_call(req, actor, "otp", kc.has_otp_device, req.username):
            req.move_to(State.ESCALATED, "otp", "no_registered_device")
            log(req, actor, "otp", "escalated", reason="no_registered_device")
            return req.public_view()
        step = keycloak_call(req, actor, "otp", kc.verify_otp, req.username, body.code)
        problem = None
        if step is None:
            problem = "wrong_code"
        elif step <= store.last_otp_step.get(req.username, -1):
            problem = "otp_reused"  # a correct code, but one already used: replay
        if problem:
            req.otp_failures += 1
            if req.otp_failures >= MAX_OTP_ATTEMPTS:
                return block(req, actor, "otp", "otp_failed")
            log(req, actor, "otp", "wrong_code", reason=problem, attempts_left=MAX_OTP_ATTEMPTS - req.otp_failures)
            return req.public_view()  # state unchanged: the agent may try again
        store.last_otp_step[req.username] = step  # this code (and any older one) can never be used again
        req.move_to(State.OTP_VERIFIED, "otp")
        apply_rule5(store, req)  # a password reset may have completed since this request was opened
        if req.needs_approval:
            req.move_to(State.AWAITING_APPROVAL, "otp", "privileged" if req.is_privileged else "forced_approval")
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
    with store.lock:
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
        if who.username.lower() == req.agent_id.lower():  # the person running the request cannot approve it
            log(req, who.username, "approve", "refused", reason="approver_is_agent")
            raise HTTPException(403, "the agent running the request cannot approve it")
        require_step(req, "approve", who.username)
        req.approver = who.username
        req.move_to(State.APPROVED, "approve")
        log(req, who.username, "approve", "ok")
        return req.public_view()


@app.post("/reset-requests/{request_id}/issue")
def issue(request_id: str, kc=Depends(get_keycloak), store: Store = Depends(get_store)):
    with store.lock:
        req = find_request(store, request_id)
        actor = req.agent_id
        require_step(req, "issue", actor)
        if apply_rule5(store, req) and req.approver is None:
            # Approved without a manager, but a password reset completed in the meantime.
            req.move_to(State.AWAITING_APPROVAL, "issue", "needs_approval_rule5")
            log(req, actor, "issue", "refused", reason="needs_approval_rule5")
            raise HTTPException(409, "a password reset completed recently: a manager must approve first")
        # (If a manager had already approved, apply_rule5 still wrote its alert; no 409 is needed.)
        result: dict = {}

        if req.kind == Kind.password:
            password = random_password()
            keycloak_call(req, actor, "issue", kc.set_password, req.username, password, True)
            now = clock.now()
            expires_at = now + TEMP_PASSWORD_LIFETIME
            store.add_temp_password(TempPassword(req.id, req.username, now, expires_at))
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
    with store.lock:
        log(None, body.source, "mfa_change_event", "recorded", username=username, requested_change=body.change)
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
    failed = 0
    with store.lock:
        for item in store.temp_passwords:
            if item.rotated_at is not None or item.superseded or clock.now() < item.expires_at:
                continue  # (an older password of a user who got a newer one is never rotated)
            try:
                user = keycloak_call(None, "system", "expire", kc.get_user, item.username)
                if user is None or "UPDATE_PASSWORD" not in user.required_actions:
                    # Nothing to rotate: the account is gone, or the user already chose their own
                    # password (rotating that one would lock them out).
                    skip_reason = "user_not_found" if user is None else "already_changed"
                    log(
                        None,
                        "system",
                        "temp_password_expiry",
                        "skipped",
                        request_id=item.request_id,
                        reason=skip_reason,
                    )
                else:
                    keycloak_call(None, "system", "expire", kc.set_password, item.username, random_password(), True)
                    log(None, "system", "temp_password_expiry", "rotated", request_id=item.request_id)
                    rotated.append(item.request_id)
                # Marked done only after success, so a failed rotation is retried on the next run.
                item.rotated_at = clock.now()
            except HTTPException:  # already logged by keycloak_call; carry on with the other users
                failed += 1
    return {"rotated": rotated, "failed": failed}
