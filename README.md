# td-1-helpdesk — Track 1 · Helpdesk (CompTIA A+): stop the reset at the front door

This is the first of four repos in my [Takeover Defense](https://github.com/DK1051/takeover-defense) portfolio. It covers the moment the attack starts: someone phones the IT helpdesk, says they lost their phone and cannot log in, and asks for a password and MFA reset (MFA, multi-factor authentication, is the second check — such as a code on your phone — that protects a login). A helpdesk technician who verifies the caller properly stops the whole attack before it begins. The three projects here show what a technician should do (a casebook and a written verification procedure), what the tooling should make impossible to skip (a small reset service that enforces the checks in order), and what happens when the technician is an AI assistant (a stress test against scripted social-engineering calls). The company, people and phone numbers are all fictional: Maple Harbour Credit Union, Toronto, 50 staff, `mapleharbour.example`.

Why this attack matters, with the sources, is in the hub: [docs/STORY.md](https://github.com/DK1051/takeover-defense/blob/main/docs/STORY.md). The lead source is the Canadian Centre for Cyber Security alert AL26-010 (May 1, 2026), which warns that attackers "convince support staff to reset MFA or enroll attacker-controlled devices" and recommends "out-of-band verification procedures for identity-related requests".

## Status

**In progress.** 1E is being built (T1-S01) and 1H has its core service and tests (T1-S02); 1A is still planned. The schedule is in [docs/RUN-SHEET.md](docs/RUN-SHEET.md). Status words (same in every repo of the portfolio): `Planned` → `In progress (session IDs)` → `Built` → `Verified` (verify report linked) → `Cut` (moved to after Nov 5, 2026).

## Projects

| Project | Level | Folder | What it shows | Status |
|---|---|---|---|---|
| 1E Front Desk Casebook | Easy | `1e-front-desk-casebook/` | A caller-verification procedure (SOP) built on AL26-010, a ticket template, ten realistic helpdesk tickets (six break-fix, four phone reset requests that are social engineering) that I solve myself, and knowledge-base articles in English and Korean | In progress (T1-S01) |
| 1H Verified Reset Service | Hard | `1h-verified-reset/` | A small web service (FastAPI) a helpdesk agent uses to run a reset. It enforces the steps in order — callback to the phone number on file, one-time code to the registered device, manager approval for privileged accounts, a temporary password that expires in 60 minutes — and alerts on any MFA change within 24 hours of a reset. Tested against the four social-engineering tickets and the alleged Clorox sequence | In progress (T1-S02) |
| 1A Helpdesk Bot Stress Test | Hard + AI | `1a-bot-stress-test/` | An AI helpdesk assistant whose only actions are calls to the 1H service, run against 40 attack scripts (20 English, 20 Korean) and 20 genuine requests that I write. Scored on whether it verified before acting, escalated correctly, and refused genuine users — by language and by model, with cost per run | Planned |

## What I do and what Claude does

- **I (Eojin)** solve every ticket, write the knowledge-base articles in both languages, record a short video walking through the SOP, write every attack script and genuine request used in the stress test, and sit two "class" sessions where I explain the code back and answer ten "why" questions per project — graded honestly, transcript published.
- **Claude** scaffolds the casebook, writes the service and its tests, builds the test harness and scorer, and verifies each session's work against written acceptance criteria. The roles and rules are in [CLAUDE.md](CLAUDE.md). Per project, [AI-USE.md](AI-USE.md) lists what Claude did (and which model) and what I did.

## How to verify my work

- `docs/verify/<session>.md` — one line per acceptance criterion with PASS / FAIL / NEEDS-EOJIN and evidence.
- `docs/learning/<session>.md` — my graded answers from the class sessions.
- One branch and one pull request per session (`t1-s01-…`, `t1-s02-…`); `COSTS.md` logs the AI credit spent; `docs/CAVEATS.md` logs what went wrong and what changed.

## Running the code (once it exists)

```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
ruff check .
pytest -q          # integration tests marked `keycloak` skip themselves when no Keycloak is running
```

The 1H service talks to a local Keycloak server (an open-source identity server that plays the role of the company's login system) at `http://localhost:8080`. The cloud environment installs Keycloak 26.8.1 with `environment/setup.sh`; the start command and the dev-realm setup script are described in `docs/briefs/T1-S02.md`. The dev server's bootstrap password is a throwaway for a local test server and is never reused anywhere.

## Sources

- Canadian Centre for Cyber Security, alert AL26-010 (May 1, 2026): https://www.cyber.gc.ca/en/alerts-advisories/al26-010-cyber-criminals-social-engineering-enabled-compromise-enterprise-saas-environments
- UK National Cyber Security Centre, "Incidents impacting retailers – recommendations from the NCSC" (4 May 2025), quoted in the SOP ("review helpdesk password reset processes, including how the helpdesk authenticates staff members credentials"): https://www.ncsc.gov.uk/blog-post/incidents-impacting-retailers
- Okta, "Cross-Tenant Impersonation: Prevention and Detection" (31 Aug 2023), quoted in the SOP ("Strengthen help desk identity verification processes using visual verification."): https://sec.okta.com/articles/2023/08/cross-tenant-impersonation-prevention-and-detection

## Licence

MIT — see [LICENSE](LICENSE).
