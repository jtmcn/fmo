---
id: FM-0012
title: the Listing tiers and the two probability classes are not declared disjoint
type: bug
priority: 1
depends_on: []
touches:
  - src/core.ttl
  - src/kalshi.ttl
  - src/weather.ttl
  - src/fmo.ttl
  - queries/axiom-expectations.json
  - scripts/test_reason.py
  - README.md
  - docs/design-notes.md
forbidden:
  - src/imports/**
  - shapes/thermaledge-export.ttl
  - shapes/thermaledge-export.pin.json
risk: low
acceptance:
  - claim: >-
      An individual typed both ksh:Series and ksh:Market (and each other pair of
      Listing tiers) is inconsistent under HermiT.
    witness: a reasoner case in scripts/test_reason.py, run by make reason-negative
  - claim: >-
      An individual typed both fm:ForecastProbability and
      fm:MarketImpliedProbability is inconsistent under HermiT.
    witness: a reasoner case in scripts/test_reason.py, run by make reason-negative
  - claim: >-
      Each new disjointness axiom is pinned by a case or exempt with a reason.
    witness: make axioms
  - claim: >-
      Every other sibling set under a minted class was decided, disjoint or
      deliberately not, and the "not" cases say why.
    witness: src/*.ttl scope notes, reviewed
---

## Context

The ontology has five disjointness axioms in total: the designation block
(`core.ttl:270`, `kalshi.ttl:327`), the three depths (`weather.ttl:170`), and
the yes/no contract sides (`kalshi.ttl:139`). FM-0010 showed the pattern of
deciding a sibling set explicitly: snow cover and portion of precipitate were
left overlapping on purpose, and the scope note says so.

## Problem

- README decision 1 is that a series, an event grouping and a market are
  different things, and conflating them is what would make the ontology wrong.
  `ksh:Series`, `ksh:EventGrouping` and `ksh:Market` are all `ksh:Listing` and
  nothing makes them disjoint. An individual typed as two of them is consistent.
- CQ2 subtracts a `fm:MarketImpliedProbability` from a
  `fm:ForecastProbability` on the same proposition. An assignment typed as both
  is consistent, and would make the gap zero for a reason nobody asserted.

Larger sibling sets are undecided too: the 16 children of
`fm:InformationContentEntity`, the 10 of `fm:MeasurementDatum`, the 15 of
`wx:AtmosphericQuality`. Some of those overlap on purpose. None says which.

## Out of scope

Disjointness across the continuant/occurrent line; BFO already provides it.

## Notes for the agent

- Start with the two sets named in the claims; they carry the ontology's
  central claims. The larger sets can be a pass of scope notes rather than
  axioms where overlap is intended.
- Run `make reason` before and after: an existing example that silently typed
  something into two tiers would surface as an inconsistency, which is the point.
- `owl:AllDisjointClasses` over the three tiers, not three pairwise axioms, so
  `make axioms` has one axiom to pin.
- This is a minor version bump across all four modules.

## Comments
