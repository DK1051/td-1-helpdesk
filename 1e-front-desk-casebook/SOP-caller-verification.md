# SOP — Caller verification for account requests

> **Draft outline (T1-S01).** This is a skeleton built from public guidance. The decisions marked `<!-- Eojin: -->` are Eojin's to make; the wording is his to finish. An SOP (standard operating procedure) is a written, step-by-step procedure that every technician follows the same way.

## Purpose

Stop an attacker from taking over a staff account by phoning the helpdesk and asking for a reset. The helpdesk is the front door: if a technician resets a password or multi-factor authentication (MFA, the second check such as a code on a phone) for the wrong person, the attacker is inside.

<!-- Eojin: write the purpose in your own words, in two or three sentences. -->

## Scope

This procedure applies to any request that changes how a person proves who they are:

- Password reset
- MFA reset
- New device enrolment (adding a phone or token to an account)
- Phone number or email address change on the account

<!-- Eojin: decide whether walk-up and email requests follow the same steps as phone requests, and say so here. -->

## Verification steps (in this order)

Do not skip a step, and do not reorder them. If the caller pushes to skip one, that is itself a red flag (see below).

1. **Call back the phone number already on file.** End the call, then dial the number stored in the staff record. Never use a number the caller gives you, and never call back a number shown on caller ID.
   <!-- Eojin: what do you do if the number on file is the lost phone itself? -->
2. **Send a one-time code to the registered device.** The caller must read the code back. A one-time code is a short number that works once and expires quickly.
   <!-- Eojin: what if the registered device is the one that was lost? Decide the fallback. -->
3. **Get manager approval for privileged accounts.** A privileged account is one that can change other accounts or systems (for example IT administrators). The manager is reached through the number on file, not through the caller.
   <!-- Eojin: list which roles count as privileged at Maple Harbour. -->
4. **Issue a temporary password that expires in 60 minutes.** The caller must set a new password at first sign-in.
5. **Watch for MFA changes in the 24 hours after a reset.** Any new device or MFA change in that window is reviewed by a second person.
   <!-- Eojin: who reviews, and how do they get notified? -->

## What to do when a step fails

- **Block:** make no change to the account.
- **Escalate:** hand the request to the security contact and the caller's manager, using details on file.
- **Log:** record which step failed and what the caller said, in the ticket.

<!-- Eojin: write the exact wording the technician says to the caller when refusing politely. -->

## Red flags seen in public reporting

These behaviours are described in public reporting on helpdesk social engineering (see Sources). None of them proves an attack; each means "slow down and follow the steps".

- **Urgency:** "I have to present in ten minutes", "the whole team is waiting".
- **A "new phone":** the old phone is lost, broken or "being replaced", so the code cannot go to the registered device.
- **Asking to skip the callback:** "just call me on this number instead".
- **Name-dropping a manager:** "my manager said you should do this", or claiming to be the manager.

<!-- Eojin: add any red flag you think is missing, and say how a technician should respond to each. -->

## What to log

For every request, record: ticket ID, date and time, the staff record the request claims to be for, which steps were completed, which step failed (if any), the final decision, and the technician's name.

<!-- Eojin: confirm the list, and add the retention period you would propose. -->

## Sources

Quoted exactly. Retrieved for this draft; Eojin to re-check each passage against the live page.

- Canadian Centre for Cyber Security, alert AL26-010 (May 1, 2026): https://www.cyber.gc.ca/en/alerts-advisories/al26-010-cyber-criminals-social-engineering-enabled-compromise-enterprise-saas-environments
  - Attackers "convince support staff to reset MFA or enroll attacker-controlled devices".
  - Recommends "out-of-band verification procedures for identity-related requests".
  - Recommends to "restrict and closely monitor MFA reset, recovery, and device re-enrolment processes" with "enhanced verification and approval".
- UK National Cyber Security Centre, "Incidents impacting retailers" (4 May 2025): https://www.ncsc.gov.uk/blog-post/incidents-impacting-retailers
  - "review helpdesk password reset processes, including how the helpdesk authenticates staff members credentials"
- Okta, "Cross-Tenant Impersonation: Prevention and Detection" (31 Aug 2023): https://sec.okta.com/articles/2023/08/cross-tenant-impersonation-prevention-and-detection
  - "Strengthen help desk identity verification processes using visual verification."

<!-- TODO(verify): Eojin to re-read each source page and confirm the quoted passages and dates before the SOP is marked Built. -->
