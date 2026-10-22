## Probe 2026-10-22T09:51Z
- arch: x86_64
- cpus: 4  memory: 15 GB
- avx2 flags: 4
- python: Python 3.13.16
- java: Picked up JAVA_TOOL_OPTIONS: [proxy settings removed before commit — they list internal proxy hosts]
- docker:   not available
- pwsh: 7.6.7
- keycloak: /opt/keycloak Keycloak 26.8.1
- reach https://repo1.maven.org/maven2/ -> HTTP 429
- reach https://mcr.microsoft.com/v2/ -> HTTP 200
- reach https://packages.microsoft.com/ -> HTTP 200
- reach https://pypi.org/simple/ -> HTTP 200
- reach https://www.powershellgallery.com/ -> HTTP 000
- reach https://graph.microsoft.com/v1.0/ -> HTTP 000
- reach https://management.azure.com/ -> HTTP 000

Notes on this run (added by the director, not by `probe.sh`):
- The `java:` line's proxy host list was removed before commit (it names internal hosts). Java 21 (`openjdk version "21.0.12.1"`) was checked separately.
- `docker:` and `keycloak:` each printed over two lines; they are joined here.
- This probe ran in the same cloud session as the hub's H00 and the other track sessions (Eojin's D0 launch), after `environment/setup.sh` for Track 1 and Track 3 ran on this machine. So `pwsh: 7.6.7` comes from Track 3's setup, not Track 1's.

### What the `keycloak:` line means for Track 1
- `keycloak: /opt/keycloak Keycloak 26.8.1` — the environment setup installed Keycloak 26.8.1, the version T1-S02 expects, so no Keycloak caveat is needed. 1E itself does not use Keycloak.
- If T1-S02 runs in a fresh `td-1-helpdesk` environment, re-check this line there: Maven Central answered `HTTP 429` (too many requests) today, so the setup's fallback source may not work.
