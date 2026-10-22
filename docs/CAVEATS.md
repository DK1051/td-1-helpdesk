# Caveats found during execution

One line per caveat, newest last, in this exact format (from CLAUDE.md):

`- YYYY-MM-DD <ID> | what happened | impact: this session / <later IDs> / plan | what I did | needs Eojin: yes/no`

- 2026-10-22 T1-S01 | Ran in one cloud session with the hub and the other tracks (Eojin's D0 launch, no plan-approval stop); this session can push only to `claude/friendly-heisenberg-seafff`, not `t1-s01-1e-scaffold` | impact: this session | used that branch; one PR | needs Eojin: no
- 2026-10-22 T1-S01 | Eojin's rule: attack and social-engineering scripts are his to write, so T07–T10 have the ticket fields and a neutral description but the caller transcript is a TODO placeholder | impact: this session (AC3 partly open) / T1-S03 (replay tests need the transcripts) | left `<!-- TODO(Eojin) -->` in each | needs Eojin: yes
- 2026-10-22 T1-S01 | Probe: Keycloak 26.8.1 installed (no Keycloak caveat needed); Maven Central answered HTTP 429, so the setup's fallback source may fail in a fresh environment; docker not available | impact: T1-S02 | re-check the `keycloak:` line at T1-S02 | needs Eojin: no
- 2026-10-22 T1-S01 | The NCSC and Okta quotes were copied from the brief, not re-checked against the live pages | impact: this session | `TODO(verify)` in the SOP | needs Eojin: yes
- 2026-10-22 T1-S01 | Credit balances not available during the unattended run | impact: this session | placeholders in `COSTS.md` | needs Eojin: yes
