# 1E — Front Desk Casebook

**Status: In progress (T1-S01)**

## What it does

A casebook is a practice file for a helpdesk technician. This one holds:

- a written caller-verification procedure (an SOP, a standard operating procedure: the step-by-step checks a technician does before changing anyone's login), built on public guidance;
- a ticket template;
- ten realistic tickets for the fictional Maple Harbour Credit Union (Toronto, 50 staff): six ordinary break-fix tickets (hardware, operating system, software) and four phone requests to reset a password or MFA (multi-factor authentication, the second check such as a code on a phone) that show social-engineering pressure;
- knowledge-base article templates in English and Korean.

The scaffold is built; the solving and writing is Eojin's. All people, phone numbers (`555-01xx`) and emails (`@mapleharbour.example`) are fictional.

## Folder map

| Path | What it is |
|---|---|
| `SOP-caller-verification.md` | The caller-verification procedure: purpose, scope, five steps in order, what to do when a step fails, red flags, what to log, sources. An outline with decision markers for Eojin |
| `ticket-template.md` | The fields every ticket uses |
| `tickets/T01.md` – `T06.md` | Break-fix tickets (hardware, operating system, software, mobile) with symptoms and a short troubleshooting history |
| `tickets/T07.md` – `T10.md` | Phone reset requests. Each shows one pressure from public reporting: urgency, a claimed new phone, asking to skip the callback, impersonating a manager or the IT vendor. The caller transcripts are left for Eojin |
| `kb/en/TEMPLATE.md` | Knowledge-base article template, English |
| `kb/ko/TEMPLATE.md` | Knowledge-base article template, Korean |

## How to run it

There is nothing to run: it is a set of documents. Read the SOP first, then open a ticket, work through it, and write the Decision and the Reply to user in your own words. To start a new article, copy `kb/en/TEMPLATE.md` or `kb/ko/TEMPLATE.md`.

## Eojin's part

- Solve each ticket: write the **Decision** and the **Reply to user** in T01–T10 in your own words.
- Write the caller transcripts (caller lines and agent lines) in T07–T10. Claude does not write attack scripts; keep them at the level of public reporting.
- Write three knowledge-base articles, each in English and Korean, in `kb/en/` and `kb/ko/`.
- Finish the SOP: answer each `<!-- Eojin: -->` question and re-check the quoted sources.
- Record a 3-minute video walking through the SOP on one of the T07–T10 calls and link it here: <!-- Eojin: add the video link here -->.
- Review the Korean template wording; the template was written by Claude and Eojin is the bilingual one.

## What Eojin did vs what Claude did

| | Eojin | Claude |
|---|---|---|
| SOP | Decisions at each marker, final wording, source re-check | Outline built from the public sources quoted in it |
| Tickets T01–T06 | Decision and reply | Symptoms and troubleshooting history |
| Tickets T07–T10 | Caller transcripts, decision and reply | Ticket header, fictional record on file and a neutral description of the pressure |
| Knowledge base | Three articles in English and Korean, review of the Korean template | The two empty templates |
| Video | Recording and link | Nothing |

Nothing is solved yet, so the Eojin column is still to do.

## Results

None yet. This section is filled in after Eojin solves the tickets and the verify report is written (`docs/verify/T1-S01.md`).

## Limits

- The SOP is an outline built from public guidance, not a finished procedure. It has not been tested on real calls.
- The tickets are invented for practice. They are not real incidents.
- T07–T10 contain no caller dialogue until Eojin writes it.
- The Korean template has not yet been reviewed by Eojin.
