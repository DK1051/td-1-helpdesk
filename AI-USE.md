# What Claude did vs what Eojin did

One section per project. Each is filled in at `wrap` from what actually happened in the session, not from the plan. "Models used" names the subagent and model (director Opus 5.5, builder Sonnet 5.5, chores Haiku 5.5, verifier Opus 5.5, redteam Fable 5.1) that did each piece.

## Starter kit (CLAUDE.md, agents, briefs, run sheet, README skeleton)
Claude (models used)
- Drafted every kit file from Eojin's written plan (director: Opus 5.5; kit writer: Fable 5.1). Confirm at T1-S01.
Eojin
- Wrote the plan the kit was generated from; reviewed and uploaded the kit. Confirm at T1-S01.

## 1E Front Desk Casebook
Claude (models used)
- T1-S01 director (Opus 5.5): kit check (24 files, all found), probe, caveats, run sheet, PR.
- T1-S01 `builder` (Sonnet 5.5): wrote the SOP outline with the quoted sources, the ticket template, break-fix tickets T01–T06 in full, the ticket shells for T07–T10 (fields and a neutral description only), the KB templates in English and Korean, and the 1E README; ran the fictional-data consistency pass and `ruff` / `pytest`.
- T1-S01 `redteam` (Fable 5.1): mid-review. `verifier` (Opus 5.5): final check, `docs/verify/T1-S01.md`.
Eojin
- To do: write the caller transcripts for T07–T10, the Decision and Reply to user for all ten tickets, three KB articles in English and Korean, review the Korean template, and record the SOP video.

## 1H Verified Reset Service
Claude (models used)
- T1-S02 director (Opus 5.5): checked Needs, explained D1/D2 in plain words and proposed the plan; integrated, logged caveats, opened the PR.
- T1-S02 `builder` (Sonnet 5.5): `scripts/keycloak-dev.sh`, the FastAPI service in `app/`, 46 unit tests with a fake Keycloak and 6 integration tests against a local Keycloak 26.8.1, the draft 1H README; then applied the redteam fixes.
- T1-S02 `redteam` (Fable 5.1): mid-review (17 items, all handled). `verifier` (Opus 5.5): final check, `docs/verify/T1-S02.md`.
Eojin
- Approved the plan and the D1/D2/Rule-5 choices. Still to do: read the README state-machine list before T1-C1 (you will be asked why each step is where it is); record the credit balance.

## 1A Helpdesk Bot Stress Test
Claude (models used)
- (to be filled at wrap)
Eojin
- (to be filled at wrap)
