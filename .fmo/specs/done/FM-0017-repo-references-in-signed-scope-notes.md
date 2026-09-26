---
id: FM-0017
title: scope notes cite repo scripts and CQs, and the semantics signature digests them
type: bug
priority: 3
depends_on:
  - FM-0016
touches:
  - src/core.ttl
  - src/weather.ttl
  - src/kalshi.ttl
  - src/fmo.ttl
  - scripts/term_signatures.py
  - scripts/validate.py
  - scripts/test_validate.py
  - CLAUDE.md
  - CONTEXT.md
forbidden:
  - src/imports/**
  - shapes/thermaledge-export.ttl
  - shapes/thermaledge-export.pin.json
risk: low
claimed_by: claude
acceptance:
  - claim: >-
      No skos:scopeNote names a file under scripts/, examples/ or queries/, a
      check_ function, a make target, or a CQ number; those references live in
      skos:editorialNote.
    witness: check_note_kinds in scripts/validate.py, with four negative tests in scripts/test_validate.py
  - claim: >-
      Editing a skos:editorialNote does not move semantics_sha256; editing a
      skos:scopeNote still does.
    witness: scripts/term_signatures.py --check, scope_note_mutant and editorial_note_mutant
---

## Context

`scripts/term_signatures.py:89` folds every `skos:scopeNote` into
`semantics_sha256`, which is what ThermalEdge pins to learn that a term's
commitments moved. CLAUDE.md says a scope note carries "why here, not there".

## Problem

Eight scope notes point at repo machinery rather than the domain:

| Term | Cites |
|---|---|
| `fm:TruthAssessment` | CQ7 |
| `fm:hasUnit` | `scripts/validate.py` |
| `wx:PrecipitationProcess` | `examples/kxrainnyc-2026-07-15.ttl` |
| `wx:leadTimeHours` | `scripts/validate.py` |
| `ksh:YesContract` | `scripts/validate.py`, CQ8 |
| `ksh:Payout` | `scripts/validate.py` |
| `ksh:sourceProtocol` | `scripts/validate.py` |
| `ksh:payoutAmountCents` | `scripts/validate.py`, `check_payouts` |

Renaming a check or an example file therefore tells a consumer that the term's
meaning changed when nothing semantic did. That trains the consumer to ignore
the signal.

## Out of scope

Rewriting the domain content of those notes. Only the repo references move.

## Notes for the agent

- Split each note: the domain sentence stays in `skos:scopeNote`; the "and
  `check_payouts` enforces this" sentence moves to `skos:editorialNote`.
- The detector needs a pattern list; keep it narrow (paths, `check_\w+`,
  `\bCQ\d`, `make \w+`) and let the negative test prove each pattern bites.
  `fm:SkillScore` matches "make it" as prose, which the pattern must not flag.
- One-time digest churn for eight terms. Depends on FM-0016 so the two
  definition/scope-note passes land as one re-pin, not two.
- Add a line to CLAUDE.md "Working in the ontology": scope notes for the
  domain, editorial notes for the repo.

## Comments

**2026-09-25 — resolved in 0.20.0.** Nine terms, not the eight listed above.
`wx:TropicalCyclone` cited `docs/design-notes.md`, which the pattern list here
did not cover.

**What moved.** Each note was split: the domain sentences stayed in
`skos:scopeNote`, reworded where they had leaned on the reference ("the stored
value is checked against…"), and the pointer moved to a `skos:editorialNote`
naming the specific check, such as `check_lead_times` or `check_protocols`.

**`check_note_kinds`.** It refuses a scope note that cites:
- a path under `src/`, `scripts/`, `queries/`, `shapes/`, `docs/` or
  `examples/`;
- a `check_` name;
- a CQ number;
- a make target, counted only when the Makefile defines it, so
  `fm:SkillScore`'s "make it" passes, as the baseline proves.

It also goes one step past the spec: every path and check name an editorial
note gives must exist. Editorial notes are outside the digest, so nothing else
would notice one rot. There are six negative tests, one per scope-note pattern
and one per resolution failure.

**`term_signatures.py --check`** gains `scope_note_mutant` (that term's
semantics moves, and nothing else) and `editorial_note_mutant` (no digest
moves).

**Digest churn for ThermalEdge.** `semantics_sha256` moves on the nine terms
whose scope notes were reworded. That is the last time a repo rename can move
one.
