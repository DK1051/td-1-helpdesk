#!/usr/bin/env bash
# Environment probe: records what this cloud machine can and can't do.
set -u
echo "## Probe $(date -u +%Y-%m-%dT%H:%MZ)"
echo "- arch: $(uname -m)"
echo "- cpus: $(nproc)  memory: $(free -g | awk '/Mem:/{print $2" GB"}')"
echo "- avx2 flags: $(grep -c avx2 /proc/cpuinfo 2>/dev/null || echo 0)"
echo "- python: $(python3 --version 2>&1)"
echo "- java: $(java -version 2>&1 | head -n1)"
echo "- docker: $(docker info --format '{{.ServerVersion}} {{.Architecture}}' 2>/dev/null || echo 'not available')"
echo "- pwsh: $(pwsh -NoLogo -Command '$PSVersionTable.PSVersion.ToString()' 2>/dev/null || echo 'not installed')"
echo "- keycloak: $(ls -d /opt/keycloak 2>/dev/null && /opt/keycloak/bin/kc.sh --version 2>/dev/null | head -n1 || echo 'not installed')"
check() { code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$1"); echo "- reach $1 -> HTTP $code"; }
check https://repo1.maven.org/maven2/
check https://mcr.microsoft.com/v2/
check https://packages.microsoft.com/
check https://pypi.org/simple/
check https://www.powershellgallery.com/
check https://graph.microsoft.com/v1.0/
check https://management.azure.com/
