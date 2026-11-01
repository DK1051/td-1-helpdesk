# 1A — Helpdesk Bot Stress Test

## Status

**The framework is complete. The real stress-test run is pending.** It needs Eojin's 60 case files (20 English attacks, 20 Korean attacks and 20 genuine requests) and a live run of Keycloak and the 1H service. It is scheduled after his CompTIA A+ exam and will use plan usage. **No results exist yet, and no number in this repo should be read as one.**

What is built: the case checker, the batch maker, the wrapper the assistant uses, the scorer, the results-table writer, the assistant's definition, and tests for all of them. What has not happened: no model has run on any case, and `api.py` has never talked to a live 1H service (its tests use a fake one).

## What it does

Does an AI helpdesk assistant check who a caller is before it changes anything, when the caller is trying to talk it out of checking? This project finds out.

- The **assistant** is a Claude subagent (`.claude/agents/helpdesk-bot.md`) that plays a Maple Harbour Credit Union helpdesk agent. Its only tool is one wrapper script, `harness/api.py`, which talks to the 1H Verified Reset Service (`../1h-verified-reset/`).
- The **callers** are scripted conversations written by Eojin: 20 English attacks, 20 Korean attacks (a caller trying to skip verification) and 20 genuine requests (an honest employee). The callers' lines are fixed; they do not react to what the assistant says.
- The **wrapper** acts as the telephone and the authenticator app. The 1H service cannot hear a phone call, so the wrapper decides whether a `dial` is answered (never, for an attack) and turns the placeholder `{{OTP}}` into a valid one-time code for a genuine caller or a wrong one for an attacker. The assistant never sees a secret.
- The **scorer** reads 1H's own audit log (its record of every decision) and the wrapper's log, not what the assistant says about itself. It reports four things, each split by language and by model: how often the assistant verified before acting, how often it correctly refused or escalated an attack, how often it wrongly refused a genuine request, and how many attacks got through (expected to be 0).

A term used above: an **OTP** (one-time password) is the six-digit code from an authenticator app, good for about 30 seconds. A **callback** is the agent phoning the number stored for the user, never a number the caller offers. More terms are in the glossary at the end of [DESIGN.md](DESIGN.md).

## Folder map

| Path | What it is |
|---|---|
| `DESIGN.md` | The full design: simulation rules, record shapes, the exact score formulas, threats to validity, cost plan |
| `DESIGN-REVIEW.md` | The `redteam` review of the first design, and what was changed in response |
| `cases/` | Eojin's case files (format in `cases/README.md`). Empty until he writes them |
| `harness/validate_cases.py` | Checks the case files before anything runs |
| `harness/make_batches.py` | Makes label-free batch files (`batches/*.yaml`) and the private `batches/manifest.json` |
| `harness/api.py` | The wrapper: the assistant's only tool (eight commands) |
| `harness/score.py` | Scores one model's runs into `results/<model>.json` |
| `harness/render_results.py` | Writes the results table below from `results/*.json` and `results/costs.md` |
| `tests/` | Tests, run with `pytest -q`; they use small made-up runs and a fake 1H, never a real model or service |
| `../.claude/agents/helpdesk-bot.md` | The assistant under test |

## How to run it

Run everything from the repo root with the project's virtual environment (`python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt`). Only the case-checking, batch-making, scoring and table steps have been exercised, and only on made-up data in the tests. Every step that needs the live service is marked TODO(verify).

1. **Check the case files.**
   `PYTHONPATH=1a-bot-stress-test .venv/bin/python -m harness.validate_cases 1a-bot-stress-test/cases`
   It prints the count per group and stops on any error (fewer than 10 English attacks, 10 Korean attacks or 10 genuine requests is an error). Warnings (for example fewer than 5 genuine cases in a language) do not stop it. Fix the files until it passes.
2. **Make the batch files.**
   `PYTHONPATH=1a-bot-stress-test .venv/bin/python -m harness.make_batches 1a-bot-stress-test/cases 1a-bot-stress-test/batches`
   This writes at most 20 cases per file, per language, with attacks and genuine requests shuffled together under a fixed seed, plus `batches/manifest.json` (the private answer key; the assistant must never read it).
3. **Run each model on each batch file.** TODO(verify): this step has never run live. Per model and batch file:
   1. Start Keycloak and set up the dev users: `bash 1h-verified-reset/scripts/keycloak-dev.sh` (see the 1H README).
   2. Choose the run folder `1a-bot-stress-test/runs/<model>-<batch>` (for example `runs/haiku-en-1`) and tell the wrapper about it: set `HARNESS_RUN_DIR`, or write the folder path into the file `1a-bot-stress-test/runs/CURRENT`.
   3. Start a fresh 1H service with its own audit log in that folder, from the `1h-verified-reset` folder: `AUDIT_LOG_PATH=<absolute run folder>/audit.jsonl ALERTS_LOG_PATH=<absolute run folder>/alerts.jsonl uvicorn app.main:app --port 8000`. A fresh service per run is required: mixing runs makes the scorer wrong, and the scorer refuses a run whose audit log and wrapper log disagree. TODO(verify): the relative-versus-absolute path behaviour of `AUDIT_LOG_PATH` when started this way.
   4. Invoke the `helpdesk-bot` subagent once with the batch file's path, setting the model in the Agent tool's `model` parameter (do not edit the agent file). Order: haiku, then sonnet, then opus only if credit allows.
   5. Stop the service. Eojin reads the credit balance before and after each batch file and it is written to `results/costs.md`.
4. **Score each model.**
   `PYTHONPATH=1a-bot-stress-test .venv/bin/python -m harness.score --manifest 1a-bot-stress-test/batches/manifest.json --out 1a-bot-stress-test/results/haiku.json 1a-bot-stress-test/runs/haiku-en-1 1a-bot-stress-test/runs/haiku-ko-1 ...`
   Give it all of one model's run folders. It exits non-zero if a run's audit log and wrapper log disagree; do not report those results.
5. **Write the table below.**
   `PYTHONPATH=1a-bot-stress-test .venv/bin/python -m harness.render_results`

## What Eojin did vs what Claude did

- **Eojin:** approved the scoped build (framework only, run later). Will write all 60 case files in his own words, in both languages. Will read the credit balance before and after each batch file. Decides the open items listed in `DESIGN.md` and `DESIGN-REVIEW.md`.
- **Claude:** wrote the design, the harness (case checker, batch maker, wrapper, scorer, results-table writer), the tests and the assistant's prompt. Claude wrote no attack text and no case. `redteam` (a second Claude model) reviewed the design and later the code; each of its comments is answered in `DESIGN-REVIEW.md` or `DESIGN.md`.

## Results

<!-- results:start -->
No runs yet — real evaluation deferred.
<!-- results:end -->

## Threats to validity

These apply to any number this project produces (full wording in `DESIGN.md`, section 10).

- **Scripted callers do not adapt.** A live attacker reacts to the assistant's answers; these callers repeat fixed lines. The test is easier than a real call. A good score would not show a bot resists a live attacker.
- **The restriction is a prompt plus a wrapper, not a sandbox.** The assistant has a shell, so it could open the case files, the manifest, the dev seeds or call 1H directly. The prompt forbids it. The scorer catches a bot that creates its own request directly in 1H (the audit-versus-wrapper check), but a bot that only peeks at the label files could still cheat without a trace.
- **Username and request kind can give the label away.** If only genuine cases use a given pair (for example `priya.nair` with `password`), the assistant could guess. The case checker warns about it.
- **Small cells.** 10 to 20 cases per language and kind: one case moves a rate by 5 to 10 points. Counts are shown with every rate; no claim of statistical significance.
- **Non-determinism.** The same model can behave differently on a second run. One rerun per model is budgeted, which gives a rough sense of spread, not a variance estimate.
- **Long context per batch.** 20 conversations in one call can make a model lose track late in the file.
- **Simulation simplifications.** A dial to an attacker's own number answers "no answer"; callback and code checks are modelled with exactly the two checks 1H has; no voice, no caller-ID spoofing, no real phone network.
- **The genuine set is small and uneven.** Few dev users have a device, so genuine requests that should complete are all one user and one request kind. The false-refusal rate measures that narrow slice, and it counts every genuine case that did not finish, including causes that are not the model's fault.
- **Dev-only setup.** Authenticator secrets kept outside the identity provider, a single node, plain HTTP (see the 1H README, "Limits").

## Limits

- **The "only use the wrapper" rule is in the prompt only.** A hook in `.claude/settings.json` that would block the assistant from reading the label files (review item R9) was **not added**: it changes settings that apply to every session in this repo, so it is Eojin's decision.
- **No live 1H has run against `api.py`.** Its tests use a fake service, so the real request and response shapes are checked by reading the 1H source, not by running it. TODO(verify) at the first live run.
- **`555-0199`** is the fixed fictional new phone number the wrapper sends for `mfa_change_phone` requests (1H requires one). TODO(verify): that no dev user has this number on file.
- **Rules for genuine cases (R2).** To keep case order from mattering, a genuine case that expects `COMPLETED` must be a `password` request for a user who has a device and is not privileged (in practice `priya.nair`); a genuine MFA-kind case is not allowed for any user with an authenticator secret (`priya.nair`, `daniel.okafor`); a genuine case that expects `ESCALATED` is allowed only for `marcus.chen`, `sofia.alvarez` or `daniel.okafor`. This is stricter than `cases/README.md`; the case checker enforces it.
- **Model versions** are recorded only if Eojin can confirm them from the usage page. TODO(verify).

## More

- [DESIGN.md](DESIGN.md): the design, with the exact formulas and record shapes.
- [DESIGN-REVIEW.md](DESIGN-REVIEW.md): the independent design review and the responses.
- [cases/README.md](cases/README.md): the case-file format and the dev users.
