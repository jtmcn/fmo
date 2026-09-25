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
acceptance:
  - claim: >-
      No skos:scopeNote names a file under scripts/, examples/ or queries/, a
      check_ function, a make target, or a CQ number; those references live in
      skos:editorialNote.
    witness: a new registered check in scripts/validate.py, with a negative test in scripts/test_validate.py
  - claim: >-
      Editing a skos:editorialNote does not move semantics_sha256; editing a
      skos:scopeNote still does.
    witness: scripts/term_signatures.py --check, with a mutant for each
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
