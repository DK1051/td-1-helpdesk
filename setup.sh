#!/usr/bin/env bash
# Cloud environment setup: Keycloak 26.8.1 (Java 21 is preinstalled)
KC=26.8.1
if [ ! -x /opt/keycloak/bin/kc.sh ]; then
  mkdir -p /opt/keycloak
  curl -fsSL --max-time 120 -o /tmp/kc.tgz "https://github.com/keycloak/keycloak/releases/download/${KC}/keycloak-${KC}.tar.gz" \
    || curl -fsSL --max-time 120 -o /tmp/kc.tgz "https://repo1.maven.org/maven2/org/keycloak/keycloak-quarkus-dist/${KC}/keycloak-quarkus-dist-${KC}.tar.gz" \
    || echo "WARN keycloak download failed"
  [ -s /tmp/kc.tgz ] && tar -xzf /tmp/kc.tgz -C /opt/keycloak --strip-components=1 && rm -f /tmp/kc.tgz
fi
exit 0
