---
id: FM-0016
title: a label names two terms, some definitions break CONTEXT.md, and individuals escape the documentation check
type: bug
priority: 2
depends_on: []
touches:
  - src/core.ttl
  - src/weather.ttl
  - src/kalshi.ttl
  - src/fmo.ttl
  - scripts/validate.py
  - scripts/test_validate.py
  - scripts/test_meta.py
  - CONTEXT.md
  - README.md
forbidden:
  - src/imports/**
  - shapes/thermaledge-export.ttl
  - shapes/thermaledge-export.pin.json
risk: low
claimed_by: claude
acceptance:
  - claim: >-
      No two minted terms share an rdfs:label, compared case-insensitively, and
      no skos:altLabel equals another term's rdfs:label.
    witness: a new registered check in scripts/validate.py, with a negative test in scripts/test_validate.py
  - claim: >-
      No minted class is its own ancestor through rdfs:subClassOf.
    witness: the same check or a sibling, with a negative test that injects a cycle
  - claim: >-
      Every minted named individual has rdfs:label and skos:definition.
    witness: check_documentation, extended, with a negative test that strips one individual's definition
  - claim: >-
      No definition uses "record" bare or "station" where CONTEXT.md requires
      "site", and no definition carries usage advice that belongs in a scope note.
    witness: src/*.ttl, reviewed; no automated witness can read a definition
---

## Context

`check_documentation` (`scripts/validate.py:1717`) requires a label and a
definition on every minted class and property. It does not look at
individuals, and nothing compares labels across terms. CONTEXT.md says the
definition in `src/` wins on meaning, so a definition that uses a word CONTEXT
forbids makes the forbidden word authoritative.

## Problem

- **One label, two terms.** `ksh:SettlementSource` (`kalshi.ttl:109`) and
  `ksh:settlementSource` (`kalshi.ttl:408`) are both labelled "settlement
  source". CONTEXT §3 explains the difference in prose. The map's search, and
  any label lookup, cannot. The property should read "has settlement source",
  like "has rules" and "has side".
- **No cycle check.** A subclass cycle is not an inconsistency to HermiT; it
  silently makes the classes equivalent.
- **Undocumented individuals.** `fm:True`, `fm:False` (`core.ttl:122-123`) and
  `ksh:Kalshi` have no definition. The other 33 individuals have one by habit.
- **Definitions against CONTEXT.md.**
  - "record" bare: `fm:Indeterminate` (`core.ttl:125`), `fm:TruthAssessment`
    (`core.ttl:130`), `fm:EvaluationProcess` (`core.ttl:368`).
  - "station" for "site": `wx:ClimatologicalDay` (`weather.ttl:227`); "observation
    station" near `weather.ttl:505`; the `ksh:SettlementSource` example.
- **Usage advice inside definitions**, which belongs in `skos:scopeNote`:
  `fm:isAbout` ("NOT used for propositions about the future"), `fm:Between`,
  `fm:BrierScore` and `fm:LogarithmicScore` ("Lower is better"),
  `ksh:expressesProposition`, `wx:stationOfRecord`, `fm:statedAs` ("Not
  authoritative"), `fm:overTemporalInterval`.

## Out of scope

- `@en` language tags. Monolingual, and tagging every label moves every digest.
- `skos:altLabel` for acronyms (DCM, CLI, NWP model). Worth doing, but it needs
  the collision check here first.

## Notes for the agent

- The label and cycle checks are population `schema`: `coverage(always=True)`.
- Rewording definitions moves `definition_sha256` for each touched term.
  Batch them in one change so ThermalEdge re-pins once, and list the terms in
  the PR.
- Relabelling `ksh:settlementSource` moves its label digest; update CONTEXT §3.
- Moving text from definition to scope note must not lose it — the scope note
  gets the sentence verbatim unless it duplicates one already there.

## Comments

**2026-09-25 — resolved in 0.16.0.** Two new registered checks,
`check_label_uniqueness` (case-insensitive, and altLabels against other terms'
labels) and `check_subclass_cycles`, and `check_documentation` now covers named
individuals: 190 terms checked became 226. Five negative tests, one per defect;
`make meta` sweeps all three checks.

`ksh:settlementSource` is labelled "has settlement source". `fm:True`,
`fm:False` and `ksh:Kalshi` have definitions. "record" became "document" in the
three definitions CONTEXT.md §1 names, following `fm:basedOnRecord`'s range;
"station" became "observing site" in `wx:ClimatologicalDay` and the
`ksh:SettlementSource` example, and "weather station" in `wx:stationIdentifier`.
Usage advice moved verbatim from eight definitions into scope notes, merged into
the existing note where there was one.

Digest churn for ThermalEdge: `label_sha256` on `ksh:settlementSource`;
`definition_sha256` on the thirteen reworded terms and the three newly defined
individuals; `semantics_sha256` wherever a scope note gained a sentence.
