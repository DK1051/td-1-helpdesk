# Run sheet — td-1-helpdesk (Track 1)

This repo's sessions, in order. Days are relative: D0 = the day the kit is uploaded (planned Oct 22, 2026). The cross-repo schedule, buffer days and the hard stop (Nov 5, 4:00 PM KST) are in the hub: `takeover-defense/docs/MASTER-RUN-SHEET.md`. Status words: `TODO` → `IN PROGRESS` → `DONE (PR #n)`; `BLOCKED (see CAVEATS)` when a later session cannot start; `CUT` when moved past Nov 5 (cut order for this track: T1-S04 first; never T1-S01).

- [x] T1-S01 · D0 · 1E scaffold: SOP outline, ticket template, 10 tickets, KB templates (EN + KO) · needs: kit · cap $5 · status: DONE (PR #1)
- [ ] T1-S02 · D1 · 1H core service: FastAPI verified-reset flow, unit tests, scripts/keycloak-dev.sh · needs: T1-S01 merged · cap $12 · status: TODO
- [ ] T1-S03 · D2 · 1H replay tests (T07–T10 + alleged Clorox sequence), audit log, README with Mermaid diagram, demo script · needs: T1-S02 merged · cap $10 · status: TODO
- [ ] T1-C1 · D3 · class 1E + 1H: code walk-through, 10 "why" questions, one live change · needs: T1-S03 merged, Eojin's 1E done · cap $5 · status: TODO
- [ ] T1-S04 · D5 · 1A harness + eval (redteam design review first) · needs: T1-S03 merged, Eojin's 40 attack scripts + 20 genuine requests (minimum 10 EN + 10 KO + 10 genuine) · cap $20 · status: TODO
- [ ] T1-C2 · D7 · class 1A: harness and scorer walk-through, 10 "why" questions, one live change · needs: T1-S04 merged · cap $4 · status: TODO
