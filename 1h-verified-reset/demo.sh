#!/usr/bin/env bash
# One-command demo of the Verified Reset Service against a real local Keycloak.
#
#   bash 1h-verified-reset/demo.sh
#
# 1. starts Keycloak if needed and builds the dev realm (scripts/keycloak-dev.sh)
# 2. starts the service on port 8000 in the background
# 3. runs ONE verified password reset for priya.nair with curl (the one-time code is computed from
#    the dev seed file; the code and the temporary password are shown as ***)
# 4. replays the T07 attack case against the live service
# 5. prints the last ten audit lines (secrets masked) and stops the service
#
# Set DEMO_OUT=/some/file to also save the output there. Nothing secret is printed.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"
[ -f "$HERE/../.venv/bin/activate" ] && . "$HERE/../.venv/bin/activate"

BASE="http://localhost:8000"
DEV_DIR="$HERE/.dev"
mkdir -p "$DEV_DIR"
umask 077
rm -rf "$DEV_DIR"/demo.*   # logs of earlier demo runs
WORK="$(mktemp -d -p "$DEV_DIR" demo.XXXXXX)"   # fresh audit/alert files for this run; inside gitignored .dev/
OUT="${DEMO_OUT:-$WORK/output.txt}"
: > "$OUT"
exec > >(tee "$OUT") 2>&1                          # everything printed below is also saved

SERVER_PID=""
cleanup() {
  [ -n "$SERVER_PID" ] && kill "$SERVER_PID" 2>/dev/null || true   # stops only the process we started
  [ -n "$SERVER_PID" ] && wait "$SERVER_PID" 2>/dev/null || true
}
trap cleanup EXIT

step() { printf '\n--- %s\n' "$*"; }
api() { curl -s -X "$1" "$BASE$2" -H 'Content-Type: application/json' ${3:+-d "$3"}; }

step "1. Keycloak and the dev realm (secrets go to .dev/, never printed)"
bash "$HERE/scripts/keycloak-dev.sh"

step "2. Start the service on port 8000"
if curl -s -o /dev/null "$BASE/alerts"; then
  echo "something already answers on port 8000; stop it first"; exit 1
fi
export AUDIT_LOG_PATH="$WORK/audit.jsonl" ALERTS_LOG_PATH="$WORK/alerts.jsonl"
nohup uvicorn app.main:app --port 8000 > "$WORK/uvicorn.log" 2>&1 &
SERVER_PID=$!
for _ in $(seq 1 30); do
  curl -s -o /dev/null "$BASE/alerts" && break
  sleep 1
done
curl -s -o /dev/null "$BASE/alerts" || { echo "service did not start; see $WORK/uvicorn.log"; exit 1; }
echo "service is up"

step "3. A genuine, fully verified password reset for priya.nair"
CREATED="$(api POST /reset-requests '{"kind":"password","claimed_username":"priya.nair","agent_id":"agent.lee","channel":"phone"}')"
RID="$(echo "$CREATED" | jq -r .id)"
PHONE="$(echo "$CREATED" | jq -r .phone_on_file)"
echo "created request $RID, state $(echo "$CREATED" | jq -r .state), number on file $PHONE"

R="$(api POST "/reset-requests/$RID/callback" "{\"number_dialed\":\"$PHONE\",\"reached\":true}")"
echo "callback to the number on file -> state $(echo "$R" | jq -r .state)"

CODE="$(SEEDS="$DEV_DIR/seeds.json" python -c 'import json,os,pyotp;print(pyotp.TOTP(json.load(open(os.environ["SEEDS"]))["priya.nair"]).now())')"
R="$(api POST "/reset-requests/$RID/otp" "{\"code\":\"$CODE\"}")"
echo "one-time code (***) from her registered device -> state $(echo "$R" | jq -r .state)"

R="$(api POST "/reset-requests/$RID/issue")"
TEMP_PW="$(echo "$R" | jq -r '.temporary_password // empty')"
[ -n "$TEMP_PW" ] || { echo "issue did not return a password"; exit 1; }
echo "issue -> state $(echo "$R" | jq -r .state), temporary password ***, expires_at $(echo "$R" | jq -r .expires_at)"
echo "(the same call again) -> HTTP $(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/reset-requests/$RID/issue") because a step cannot be repeated"

step "4. Replay case T07 (urgency pressure) against the live service"
python -m app.replay --base-url "$BASE" tests/replay/T07.yaml 2>&1 | grep -v -i "StarletteDeprecation\|from starlette"

step "5. Alerts and the last ten audit lines (secrets masked)"
echo "alerts so far: $(api GET /alerts | jq length) (the blocked T07 request raised one)"
tail -n 10 "$WORK/audit.jsonl" | sed -e "s/$TEMP_PW/***/g" -e "s/$CODE/***/g" | jq -c .

step "6. Secret scan"
sleep 1   # let the output copy catch up
if grep -qF -e "$TEMP_PW" -e "$CODE" "$WORK/audit.jsonl" "$OUT"; then
  echo "FOUND a secret in the audit log or this output"; exit 1
fi
echo "the temporary password and the one-time code appear neither in the audit log nor in this output"
echo "stopping the service"
