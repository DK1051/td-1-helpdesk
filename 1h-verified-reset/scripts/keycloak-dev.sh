#!/usr/bin/env bash
# Builds the lab realm "maple-harbour" in a LOCAL Keycloak dev server. Safe to run twice.
#
#   bash 1h-verified-reset/scripts/keycloak-dev.sh
#
# What it creates: realm role "manager", group "privileged", client "reset-service"
# (the service's own account, used for token introspection and user changes), a public
# client "helpdesk-console" (so a manager can log in and get a token), and four fictional
# users with a phone attribute.
#
# Secrets (TOTP seeds, the client secret, the manager's dev password) are generated at
# run time and written ONLY to 1h-verified-reset/.dev/ (gitignored). They are never
# printed. The only password literal here is the documented throwaway bootstrap admin
# password of a local test server.
set -euo pipefail

KC_URL="${KEYCLOAK_URL:-http://localhost:8080}"
KC_HOME="${KC_HOME:-/opt/keycloak}"
REALM="${KEYCLOAK_REALM:-maple-harbour}"
ADMIN_USER="${KC_BOOTSTRAP_ADMIN_USERNAME:-admin}"
ADMIN_PASS="${KC_BOOTSTRAP_ADMIN_PASSWORD:-dev-only-not-secret}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEV_DIR="$HERE/../.dev"
mkdir -p "$DEV_DIR"
chmod 700 "$DEV_DIR"
umask 077

say() { echo "keycloak-dev: $*"; }

# ---- 1. make sure Keycloak is answering -------------------------------------
up() { [ "$(curl -s -o /dev/null -w '%{http_code}' "$KC_URL/realms/master" || true)" = "200" ]; }

if ! up; then
  say "Keycloak not answering on $KC_URL, starting it (about 45 seconds)"
  nohup env KC_BOOTSTRAP_ADMIN_USERNAME="$ADMIN_USER" KC_BOOTSTRAP_ADMIN_PASSWORD="$ADMIN_PASS" \
    "$KC_HOME/bin/kc.sh" start-dev --http-port=8080 > /tmp/keycloak.log 2>&1 &
  for _ in $(seq 1 80); do
    up && break
    sleep 2
  done
  up || { say "Keycloak did not come up; see /tmp/keycloak.log"; exit 1; }
fi

# ---- 2. small helpers around the admin REST API ------------------------------
# The admin token is cached in a temp file because api() runs inside $( ) subshells.
TOKEN_FILE="$(mktemp)"
trap 'rm -f "$TOKEN_FILE"' EXIT
refresh_token() {
  # Master-realm admin tokens last about a minute, so fetch a new one when the cached one is 30 s old.
  local age=999
  [ -s "$TOKEN_FILE" ] && age=$(( $(date +%s) - $(stat -c %Y "$TOKEN_FILE") ))
  if [ "$age" -gt 30 ]; then
    curl -s "$KC_URL/realms/master/protocol/openid-connect/token" \
      -d grant_type=password -d client_id=admin-cli \
      --data-urlencode "username=$ADMIN_USER" --data-urlencode "password=$ADMIN_PASS" \
      | jq -r '.access_token // empty' > "$TOKEN_FILE"
    [ -s "$TOKEN_FILE" ] || { say "could not get an admin token (check KC_BOOTSTRAP_ADMIN_PASSWORD)"; exit 1; }
  fi
  TOKEN="$(cat "$TOKEN_FILE")"
}

# api METHOD PATH [JSON]  -> prints the response body, fails on HTTP >= 400 (status only, never the body)
api() {
  refresh_token
  local method="$1" path="$2" body="${3:-}" out status
  out="$(mktemp)"
  if [ -n "$body" ]; then
    status="$(curl -s -o "$out" -w '%{http_code}' -X "$method" "$KC_URL$path" \
      -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d "$body")"
  else
    status="$(curl -s -o "$out" -w '%{http_code}' -X "$method" "$KC_URL$path" -H "Authorization: Bearer $TOKEN")"
  fi
  if [ "$status" -ge 400 ]; then
    rm -f "$out"
    say "FAILED $method ${path%%\?*} -> HTTP $status"
    exit 1
  fi
  cat "$out"
  rm -f "$out"
}

A="/admin/realms/$REALM"

rand_b64() { head -c 24 /dev/urandom | base64 | tr -d '/+=\n' | head -c 24; }
rand_b32() { head -c 20 /dev/urandom | base32 | tr -d '=\n'; }

# ---- 3. realm ------------------------------------------------------------------
refresh_token
if [ "$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $TOKEN" "$KC_URL/admin/realms/$REALM")" != "200" ]; then
  api POST /admin/realms "{\"realm\":\"$REALM\",\"enabled\":true}" > /dev/null
  say "created realm $REALM"
else
  say "realm $REALM exists"
fi

# Keycloak 26 drops unknown user attributes unless the user profile declares them.
profile="$(api GET "$A/users/profile")"
if [ "$(echo "$profile" | jq '[.attributes[].name] | index("phone") != null')" != "true" ]; then
  echo "$profile" | jq '.attributes += [{"name":"phone","displayName":"Phone","validations":{},
    "permissions":{"view":["admin"],"edit":["admin"]},"multivalued":false}]' > "$DEV_DIR/.profile.json"
  api PUT "$A/users/profile" "$(cat "$DEV_DIR/.profile.json")" > /dev/null
  rm -f "$DEV_DIR/.profile.json"
  say "declared the phone attribute"
fi

# ---- 4. role and group -----------------------------------------------------------
if [ "$(api GET "$A/roles" | jq '[.[].name] | index("manager") != null')" != "true" ]; then
  api POST "$A/roles" '{"name":"manager","description":"May approve privileged resets"}' > /dev/null
  say "created role manager"
fi
if [ "$(api GET "$A/groups?search=privileged&exact=true" | jq 'length')" = "0" ]; then
  api POST "$A/groups" '{"name":"privileged"}' > /dev/null
  say "created group privileged"
fi
GROUP_ID="$(api GET "$A/groups?search=privileged&exact=true" | jq -r '.[0].id')"
ROLE_JSON="$(api GET "$A/roles/manager")"

# ---- 5. clients --------------------------------------------------------------------
# reset-service: confidential. Secret generated once, kept in .dev/reset-service.secret.
SECRET_FILE="$DEV_DIR/reset-service.secret"
[ -s "$SECRET_FILE" ] || rand_b64 > "$SECRET_FILE"
SERVICE_JSON="$(jq -n --arg secret "$(cat "$SECRET_FILE")" '{clientId:"reset-service",name:"Verified Reset Service",
  enabled:true,publicClient:false,serviceAccountsEnabled:true,standardFlowEnabled:false,
  directAccessGrantsEnabled:false,secret:$secret}')"
CLIENT_ID="$(api GET "$A/clients?clientId=reset-service" | jq -r '.[0].id // empty')"
if [ -z "$CLIENT_ID" ]; then
  api POST "$A/clients" "$SERVICE_JSON" > /dev/null
  CLIENT_ID="$(api GET "$A/clients?clientId=reset-service" | jq -r '.[0].id')"
  say "created client reset-service"
else
  api PUT "$A/clients/$CLIENT_ID" "$SERVICE_JSON" > /dev/null   # re-applies the secret from the file
  say "client reset-service exists"
fi

# The service's own account may look up and change users, and nothing else.
SA_ID="$(api GET "$A/clients/$CLIENT_ID/service-account-user" | jq -r '.id')"
RM_ID="$(api GET "$A/clients?clientId=realm-management" | jq -r '.[0].id')"
ROLES="$(api GET "$A/clients/$RM_ID/roles" | jq '[.[] | select(.name=="manage-users" or .name=="view-users" or .name=="query-users" or .name=="query-groups")]')"
api POST "$A/users/$SA_ID/role-mappings/clients/$RM_ID" "$ROLES" > /dev/null

# helpdesk-console: public client; only used so a manager can log in and get a token.
CONSOLE_ID="$(api GET "$A/clients?clientId=helpdesk-console" | jq -r '.[0].id // empty')"
if [ -z "$CONSOLE_ID" ]; then
  api POST "$A/clients" '{"clientId":"helpdesk-console","name":"Helpdesk console (lab)","enabled":true,
    "publicClient":true,"standardFlowEnabled":false,"directAccessGrantsEnabled":true}' > /dev/null
  CONSOLE_ID="$(api GET "$A/clients?clientId=helpdesk-console" | jq -r '.[0].id')"
  say "created client helpdesk-console"
fi
# Keycloak 26 only introspects tokens that name the asking client as an audience, so manager
# tokens must carry "reset-service" as an audience.
if [ "$(api GET "$A/clients/$CONSOLE_ID/protocol-mappers/models" | jq '[.[].name] | index("audience-reset-service") != null')" != "true" ]; then
  api POST "$A/clients/$CONSOLE_ID/protocol-mappers/models" '{"name":"audience-reset-service",
    "protocol":"openid-connect","protocolMapper":"oidc-audience-mapper",
    "config":{"included.client.audience":"reset-service","id.token.claim":"false","access.token.claim":"true"}}' > /dev/null
  say "added the reset-service audience to console tokens"
fi

# ---- 6. users --------------------------------------------------------------------------
# username | first | last | phone | group | role | has TOTP device   (from the 1E tickets; all fictional)
USERS=(
  "priya.nair|Priya|Nair|555-0101|-|-|yes"
  "marcus.chen|Marcus|Chen|555-0102|-|manager|no"
  "sofia.alvarez|Sofia|Alvarez|555-0103|-|-|no"
  "daniel.okafor|Daniel|Okafor|555-0104|privileged|-|yes"
)
SEEDS="$DEV_DIR/seeds.json"
[ -s "$SEEDS" ] || echo '{}' > "$SEEDS"

for row in "${USERS[@]}"; do
  IFS='|' read -r uname first last phone group role totp <<< "$row"
  body="$(jq -n --arg u "$uname" --arg f "$first" --arg l "$last" --arg p "$phone" \
    '{username:$u,firstName:$f,lastName:$l,email:($u+"@mapleharbour.example"),emailVerified:true,enabled:true,
      attributes:{phone:[$p]}}')"
  uid="$(api GET "$A/users?username=$uname&exact=true" | jq -r '.[0].id // empty')"
  if [ -z "$uid" ]; then
    api POST "$A/users" "$body" > /dev/null
    uid="$(api GET "$A/users?username=$uname&exact=true" | jq -r '.[0].id')"
    say "created user $uname"
  else
    api PUT "$A/users/$uid" "$body" > /dev/null
  fi

  if [ "$group" = "privileged" ]; then
    api PUT "$A/users/$uid/groups/$GROUP_ID" > /dev/null
  fi
  if [ "$role" = "manager" ]; then
    api POST "$A/users/$uid/role-mappings/realm" "[$ROLE_JSON]" > /dev/null
    [ -s "$DEV_DIR/manager.password" ] || rand_b64 > "$DEV_DIR/manager.password"
    api PUT "$A/users/$uid/reset-password" \
      "$(jq -n --arg v "$(cat "$DEV_DIR/manager.password")" '{type:"password",value:$v,temporary:false}')" > /dev/null
  fi
  if [ "$totp" = "yes" ] && [ "$(jq --arg u "$uname" 'has($u)' "$SEEDS")" != "true" ]; then
    # Dev copy of the seed (design decision D1). Never printed.
    jq --arg u "$uname" --arg s "$(rand_b32)" '. + {($u): $s}' "$SEEDS" > "$SEEDS.tmp" && mv "$SEEDS.tmp" "$SEEDS"
  fi
done
chmod 600 "$DEV_DIR"/* 2>/dev/null || true

say "done: realm $REALM has $(api GET "$A/users" | jq 'length') users (secrets are in 1h-verified-reset/.dev/, not shown)"
