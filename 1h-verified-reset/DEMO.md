# Demo output

Output of `bash 1h-verified-reset/demo.sh`, run on 2026-10-22 against the local Keycloak 26.8.1 dev server (not the fake). The service ran on port 8000 and was stopped by the script at the end.

What it shows:

1. A genuine reset for `priya.nair` (callback to the number on file, one-time code, issue) ends `COMPLETED`. The temporary password and the code are shown as `***`; the script also searched the audit log and this output for the real values and found none.
2. Replay case T07 (urgency) against the same live service: the agent's out-of-order attempts get HTTP 409, the callback is not reached, and the request ends `BLOCKED` with one alert.
3. The last ten audit lines. Request ids and timestamps differ on every run. The replay's printed paths show the request id of that run.

```text
--- 1. Keycloak and the dev realm (secrets go to .dev/, never printed)
keycloak-dev: realm maple-harbour exists
keycloak-dev: client reset-service exists
keycloak-dev: done: realm maple-harbour has 4 users (secrets are in 1h-verified-reset/.dev/, not shown)

--- 2. Start the service on port 8000
service is up

--- 3. A genuine, fully verified password reset for priya.nair
created request cf3a0609d165, state OPEN, number on file 555-0101
callback to the number on file -> state CALLBACK_DONE
one-time code (***) from her registered device -> state APPROVED
issue -> state COMPLETED, temporary password ***, expires_at 2026-10-22T13:16:34.798670+00:00
(the same call again) -> HTTP 409 because a step cannot be repeated

--- 4. Replay case T07 (urgency pressure) against the live service
== T07
   1. agent opens a password reset request
      POST /reset-requests -> HTTP 201, state OPEN
   2. urgency - agent tries the code step before any callback
      POST /reset-requests/ddf864cdf018/otp -> HTTP 409, state OPEN
   3. urgency - agent tries to issue the password straight away
      POST /reset-requests/ddf864cdf018/issue -> HTTP 409, state OPEN
   4. agent phones the number on file; nobody answers
      POST /reset-requests/ddf864cdf018/callback -> HTTP 200, state BLOCKED
T07: final BLOCKED; alerts 1; ok

1/1 cases as expected

--- 5. Alerts and the last ten audit lines (secrets masked)
alerts so far: 1 (the blocked T07 request raised one)
{"action":"create","actor":"agent.lee","details":{"kind":"password","needs_approval":false},"outcome":"ok","request_id":"cf3a0609d165","ts":"2026-10-22T12:16:34.667963+00:00"}
{"action":"callback","actor":"agent.lee","details":{},"outcome":"ok","request_id":"cf3a0609d165","ts":"2026-10-22T12:16:34.688871+00:00"}
{"action":"otp","actor":"agent.lee","details":{"next_state":"APPROVED"},"outcome":"ok","request_id":"cf3a0609d165","ts":"2026-10-22T12:16:34.742642+00:00"}
{"action":"issue","actor":"agent.lee","details":{"expires_at":"2026-10-22T13:16:34.798670+00:00","kind":"password","temporary_password_issued":true},"outcome":"ok","request_id":"cf3a0609d165","ts":"2026-10-22T12:16:34.798717+00:00"}
{"action":"issue","actor":"agent.lee","details":{"actual":"COMPLETED","expected":"APPROVED"},"outcome":"out_of_order","request_id":"cf3a0609d165","ts":"2026-10-22T12:16:34.819185+00:00"}
{"action":"create","actor":"agent.lee","details":{"kind":"password","needs_approval":true},"outcome":"ok","request_id":"ddf864cdf018","ts":"2026-10-22T12:16:34.985910+00:00"}
{"action":"otp","actor":"agent.lee","details":{"actual":"OPEN","expected":"CALLBACK_DONE"},"outcome":"out_of_order","request_id":"ddf864cdf018","ts":"2026-10-22T12:16:34.991389+00:00"}
{"action":"issue","actor":"agent.lee","details":{"actual":"OPEN","expected":"APPROVED"},"outcome":"out_of_order","request_id":"ddf864cdf018","ts":"2026-10-22T12:16:34.995478+00:00"}
{"action":"callback","actor":"agent.lee","details":{"reason":"callback_not_reached"},"outcome":"blocked","request_id":"ddf864cdf018","ts":"2026-10-22T12:16:34.999621+00:00"}
{"action":"alert","actor":"system","details":{"alert":"blocked_identity_request","username":"daniel.okafor"},"outcome":"raised","request_id":"ddf864cdf018","ts":"2026-10-22T12:16:34.999870+00:00"}

--- 6. Secret scan
the temporary password and the one-time code appear neither in the audit log nor in this output
stopping the service
```
