# 1H Verified Reset Service

**Status: draft (T1-S02).** The core service, the dev-realm script and the tests exist. Replay tests, the final audit-log checks, the diagram and the demo come in T1-S03.

## What it does

A helpdesk agent uses this small web service (built with FastAPI, a Python web framework) to run a password or MFA (multi-factor authentication, the second proof of identity such as a phone app code) reset. The service refuses out-of-order steps. A reset only moves forward through these checks:

1. **Callback.** The agent phones the number on file for the user (not a number the caller gives) and records what happened.
2. **One-time code.** The user reads out the 6-digit code from their registered phone app.
3. **Manager approval.** Needed for accounts in the `privileged` group, and also when rule 5 (below) applies. The approver must hold a valid Keycloak login token with the `manager` role and must not be the person being reset.
4. **Issue.** For a password reset, a random temporary password is set and shown **once**; it is only good for 60 minutes. MFA requests have their own actions (remove the device, require a new device setup, change the phone number).

Every request and every refusal is written to an audit log (`audit.jsonl`, one JSON object per line). An MFA change soon after a password reset writes an alert (`alerts.jsonl`).

The reason for the design is the public advisory AL26-010 ("out-of-band verification procedures for identity-related requests"). The pattern it describes: an attacker phones the helpdesk, gets a password reset, then asks for the MFA to be reset too. This tool makes the helpdesk's checks happen in a fixed order and leaves a record.

Keycloak (an open-source identity server) plays the company's login system. All people, phones and emails are fictional (`mapleharbour.example`).

## How to run

Run these from the repository root unless stated.

1. **Python environment** (never install system-wide):
   `python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt`
2. **Start Keycloak and build the dev realm.** `bash 1h-verified-reset/scripts/keycloak-dev.sh` starts Keycloak if port 8080 is silent (about 45 seconds on first start; log in `/tmp/keycloak.log`), then creates realm `maple-harbour`. Running it again changes nothing. It prints status lines only. Secrets go to `1h-verified-reset/.dev/` (gitignored) and are never printed.
   The Keycloak admin password is a documented throwaway for a local test server: `dev-only-not-secret`. Keycloak data may be gone next session, so re-run the script.
3. **Start the service** (port 8080 belongs to Keycloak, so the service uses 8000):
   `cd 1h-verified-reset && uvicorn app.main:app --port 8000`
   Settings by environment variable: `KEYCLOAK_URL` (default `http://localhost:8080`), `KEYCLOAK_REALM` (`maple-harbour`), `AUDIT_LOG_PATH` (`audit.jsonl`), `ALERTS_LOG_PATH` (`alerts.jsonl`), `SEEDS_PATH` and `CLIENT_SECRET_PATH` (default to files in `.dev/`).
4. **Tests.**
   - Unit tests (no Keycloak needed; Keycloak is replaced by a fake): `pytest -q 1h-verified-reset/tests/unit`
   - Integration tests against the real Keycloak: `pytest -q -m keycloak`
   - `pytest -q` runs everything. If `GET <KEYCLOAK_URL>/realms/maple-harbour` does not answer 200, `tests/conftest.py` marks the integration tests **skipped**, not failed.

Dev users (from the 1E tickets, all fictional): `priya.nair` (regular, has a code device), `daniel.okafor` (group `privileged`, has a device), `marcus.chen` (role `manager`, password generated into `.dev/`), `sofia.alvarez` (regular, no device).

## Endpoints

| Call | What it does |
|---|---|
| `POST /reset-requests` `{kind, claimed_username, agent_id, channel}` (+ `new_phone` for `mfa_change_phone`) | `kind` is `password`, `mfa_reset`, `mfa_enrol_device` or `mfa_change_phone`. Shows the phone number on file. |
| `POST /reset-requests/{id}/callback` `{number_dialed, reached}` | Records the callback. |
| `POST /reset-requests/{id}/otp` `{code}` | Checks the one-time code. |
| `POST /reset-requests/{id}/approve` (header `Authorization: Bearer <token>`) | Manager approval. |
| `POST /reset-requests/{id}/issue` | Does the reset. |
| `GET /reset-requests/{id}` | State and history, no secrets. |
| `POST /mfa-change-events` `{username, change, source}` | Reports an MFA change seen outside the service (the lab, tests and demo send these). |
| `GET /alerts` | Lists alerts. |
| `POST /maintenance/expire-temp-passwords` | Rotates temporary passwords older than 60 minutes. |

## State machine

Normal path: `OPEN` -> `CALLBACK_DONE` -> `OTP_VERIFIED` -> (`AWAITING_APPROVAL` ->) `APPROVED` -> `COMPLETED`.

- `OPEN`: request created, user found, phone number on file shown.
- `CALLBACK_DONE`: callback reached the number on file.
- `OTP_VERIFIED`: code correct. This moves on at once to `AWAITING_APPROVAL` (privileged user, or rule 5) or `APPROVED`.
- `AWAITING_APPROVAL`: waiting for a manager.
- `APPROVED`: ready to issue.
- `COMPLETED`: the reset was done.
- `BLOCKED`: a check failed. Reasons: `unknown_user`, `no_phone_on_file`, `callback_wrong_number`, `callback_not_reached`, `otp_failed` (three wrong codes).
- `ESCALATED`: the user has no registered device (`no_registered_device`), so a person must handle it outside this tool.

Each step works from exactly one state: callback from `OPEN`, code from `CALLBACK_DONE`, approve from `AWAITING_APPROVAL`, issue from `APPROVED`. Anything else gets **HTTP 409** and an `out_of_order` audit line.

## Rule 5: the 24-hour watch

An MFA-kind request (`mfa_reset`, `mfa_enrol_device`, `mfa_change_phone`) created within 24 hours after a **completed** password reset for the same user writes an alert **and** is forced to `AWAITING_APPROVAL`, even for a regular user. Why: "reset the password, then reset the MFA" is the takeover pattern in AL26-010, so a second person must look before the second step. `POST /mfa-change-events` applies the same alert rule to MFA changes made elsewhere. The window is inclusive: exactly 24 hours still alerts, 24 hours and one second does not. Time comes from `clock.now()`, which tests move.

## Design decisions

**D1 - how the service checks a one-time code (option 2, chosen).** Keycloak has no admin call that says "is this code valid for user X". So `keycloak-dev.sh` keeps a copy of each test user's authenticator secret (the "seed") in `.dev/seeds.json` and the service checks codes with the `pyotp` library. Honest limit: a real deployment would never hold seeds outside the identity provider. Option 1 (a special direct-grant login flow without the password step, asking Keycloak itself) was not attempted; `TODO(verify)` against the Keycloak 26 documentation if it is ever tried.

**D2 - how the service checks the manager's token (option a, chosen).** The service asks Keycloak to introspect the token ("is this login ticket still valid, and whose is it?") using the confidential client `reset-service`, whose secret the script generates into `.dev/reset-service.secret`. The service then also requires `reset-service` as the token's audience and type `Bearer`, the `manager` realm role, and an approver different from the person being reset. No extra library is needed.

## Things the build needed that the brief did not spell out

- Keycloak 26 silently drops custom user attributes, so the script declares `phone` in the realm's user profile.
- A second client, `helpdesk-console` (public), exists so a manager can log in and get a token. It has an audience mapper adding `reset-service`, because on Keycloak 26.8.1 introspection answered "not active" without it. `TODO(verify)`: that this is documented Keycloak behaviour.
- The service uses its own Keycloak account (service account of `reset-service`) with only manage-users, view-users, query-users and query-groups. It never holds an admin password.
- `mfa_change_phone` needs the new number, so create takes an optional `new_phone` (required for that kind, otherwise 422).
- A wrong code answers 200 with the state unchanged and `otp_attempts_left`; the third wrong code blocks.
- `approve` checks the token first (403 plus audit line for a missing, invalid, non-manager or self-approver token), then the step order (409).
- Temporary-password rotation skips a user who has already chosen their own password (Keycloak's `UPDATE_PASSWORD` action is gone), because rotating would lock them out.
- A rule-5 alert is written when the MFA request is created, even if the request is later blocked.
- `mfa_enrol_device` only asks Keycloak to require TOTP setup; the new device's seed is not in the dev copy (D1), so that user has no code device the service can verify. A later request for that user ends `ESCALATED`.
- Concurrency: each step handler holds one lock for its whole body, so two parallel calls cannot both pass a state check or beat the three-try limit (tested with parallel wrong codes).

## Limits

- **A lab, not a product.** Requests, temporary-password bookkeeping and the 24-hour watch live in memory. A restart forgets them, including any "recent password reset" the watch relied on.
- **The callback result is self-reported by the agent.** The service refuses out-of-order steps; it cannot stop an agent from lying about having called.
- **No endpoint authenticates the agent.** That includes `/mfa-change-events` and `/maintenance/*`. Only `approve` checks a token.
- **Rule 5 only sees password resets completed through this service.** Resets done any other way are invisible to it.
- **Temporary passwords:** Keycloak's "temporary" flag forces a change at next login but does not time-limit the password. The 60-minute expiry is enforced by this service, by calling the maintenance endpoint; nothing calls it on a schedule yet.
- **Code replay:** a valid 6-digit code can be used again within its 30-second window (and `pyotp` is asked to accept one step either side). The first replay test planned for T1-S03 targets this.
- **Seeds outside the identity provider** (D1) would never be acceptable in production.
- **`mfa_enrol_device`** for a user with no device ends `ESCALATED` at the code step, since there is no device to check a code against.
- **Single node, plain HTTP, `start-dev` Keycloak:** lab settings only.

## Who did what

Eojin chooses the design decisions, reviews the code and explains it back. Claude wrote the code, tests and this draft under the repo's `CLAUDE.md` rules; the AI-use details are in `AI-USE.md`.
