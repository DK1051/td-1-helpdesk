# CLAUDE.md — td-1-helpdesk (Track 1 · Helpdesk (CompTIA A+))

This is a PUBLIC portfolio repo owned by Eojin Kim (GitHub: DK1051), a career-changer preparing for IT helpdesk → SOC → IAM roles in Canada. Hiring managers will read it. Write plainly, explain a technical term the first time you use it, and never invent facts, numbers, versions or sources — write `TODO(verify): …` instead.

## Short prompts (do exactly this)
- `go <ID>` → open `docs/briefs/<ID>.md`, read all of it, and check its **Needs** list against the repo and `docs/RUN-SHEET.md`. If anything is missing, STOP and say exactly what is missing. Otherwise propose your plan (Plan mode), wait for approval, then follow the brief.
- `status` → summarise `docs/RUN-SHEET.md` (done / next / blocked) and the last 5 entries of `docs/CAVEATS.md`.
- `probe` → run `bash scripts/probe.sh` and save its output to `docs/PROBES.md` (append, with the date).
- `class <ID>` → open `docs/briefs/<ID>.md` and run it as a lesson: explain the project's code to Eojin step by step, then the "why" interview (one question at a time, wait for his answer, grade honestly, no hints before he answers). Change no code except the brief's live-change exercise (Eojin makes the change; you guide and check it) or a bug he finds. Save the transcript summary to `docs/learning/<ID>.md`. Run the interview before any demo that starts servers; if spend passes 70% of the brief's cap, skip the demo and say so in the transcript.
- `wrap` → run the `verifier` subagent; update `docs/RUN-SHEET.md`, `COSTS.md`, `AI-USE.md`, `docs/CAVEATS.md`; push the branch; print a PR title and description for Eojin to paste.

## Roles (subagents in .claude/agents)
- You (main session, Opus 5.5) are the director: plan, split the work, integrate, decide.
- `builder` (Sonnet 5.5) writes code, tests, CI and docs.
- `chores` (Haiku 5.5) does mechanical work: fixtures, formatting, filling templates, link checks.
- `redteam` (Fable 5.1) does the mid-review: when the builder has finished about half of the brief's steps, send it the brief plus the output of `git diff main`; it looks for wrong assumptions, hidden failure cases and code Eojin couldn't explain in an interview. It also reviews designs before AI builds and gives a project's final gate. Never send it attack scripts, injection payloads or detection rules (Fable redirects offensive-security requests and has high fallback rates on security tasks); for those files the `verifier` does the mid-review instead.
- `verifier` (Opus 5.5) does the extra review and the final check: it reviews the whole diff, confirms nothing that worked on `main` is broken, and checks the brief's acceptance criteria. It reports; it never edits.
- To run a subagent on a different model (for example in an evaluation), pass the Agent tool's `model` parameter in that call; never edit a file in `.claude/agents/` during a session.

## Verification (every session, before `wrap` ends)
1. Mid-review: about halfway, `redteam` reviews the diff so far (the `verifier` does it instead for attack, injection or detection files). Address each comment or record why not.
2. Nothing broken: the `verifier` runs the full test suite and linters on this branch and on a clean checkout of `main`. Anything that passed on `main` and fails now is a FAIL, whatever the brief says.
3. Acceptance: the `verifier` checks each criterion in this order: code checks (tests, linters, scripts) → Eojin's answer key, if the brief names one → AI judgement (say so) → left for Eojin.
It writes `docs/verify/<ID>.md` with the mid-review comments and how each was handled, the regression result, and PASS / FAIL / NEEDS-EOJIN per criterion with evidence. A FAIL inside the brief's scope gets fixed if it is cheap; otherwise it becomes a caveat.

## Live adaptation
When anything differs from the plan (missing tool, limit, wrong assumption, cheaper path), append one line to `docs/CAVEATS.md`:
`- YYYY-MM-DD <ID> | what happened | impact: this session / <later IDs> / plan | what I did | needs Eojin: yes/no`
If it blocks a later session, mark that session `BLOCKED (see CAVEATS)` in `docs/RUN-SHEET.md`. Ask Eojin before changing scope, adding any paid service, or touching anything outside this repo.

## Cost discipline
- Use `builder` for code; keep the main session for planning and integration.
- Don't re-read large files; summarise them once.
- Each brief has a credit cap. If the session will clearly exceed it, stop and ask.
- At `wrap`, remind Eojin to record the credit balance (usage menu) before and after in `COSTS.md`.

## Safety rules (never break)
- Never ask for, print, store or commit passwords, tokens, keys, tenant or subscription IDs, or personal data. Secrets live only in GitHub Actions secrets or the cloud environment's network secrets, set by Eojin.
- Never connect to Eojin's Microsoft 365 / Entra tenant or Azure subscription from a cloud session. Code that talks to them is tested here against mocks; Eojin runs it, or GitHub Actions does through OIDC.
- All companies, people, phones and emails in data are fictional (Maple Harbour Credit Union, `mapleharbour.example`). Real incidents are cited only as public reporting; Clorox's claims are "alleged".
- Defensive purpose only: no malware, no exploit code, no tools for attacking real systems. Attack scripts and injection test strings are written by Eojin; you build the harness that runs them against our own test systems.
- Pin versions. Prefer mcr.microsoft.com, Maven Central, PyPI and GitHub over Docker Hub (anonymous pull limits).
- These repos are public, so CI logs are public: print error codes only, never full Azure or Microsoft Graph error bodies (they can contain object IDs).

## Conventions
- Python 3.12+, `pytest`, `ruff`; virtual env `.venv` (`python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt`). Never `pip install` system-wide.
- GitHub Actions: Node 20 was removed from GitHub-hosted runners in September 2026, so only use Node 24 action versions: `actions/checkout@v6`, `actions/setup-python@v6`, `actions/upload-artifact@v6`, `gitleaks/gitleaks-action@v3`, `azure/login@v3`. Never copy an older `@v` tag from memory; if you need another action, check its latest major version on GitHub first.
- Long commands (starting Keycloak or the Kusto emulator, setup scripts, big downloads): start them in the background with `nohup … > /tmp/<name>.log 2>&1 &` and poll in separate short commands of at most 100 seconds each, or raise the Bash tool timeout (up to 600000 ms). A timeout is not evidence that a tool is broken: read its log first.
- Branch per session `<id-lowercase>-<slug>`; one PR per session; Eojin squash-merges in the GitHub web UI.
- Each project folder has a README: what it does (plain English), how to run it, what Eojin did vs what Claude did, results, limits.
- Keycloak runs locally at http://localhost:8080 (start command in docs/briefs). Folders: 1e-front-desk-casebook/, 1h-verified-reset/, 1a-bot-stress-test/.
