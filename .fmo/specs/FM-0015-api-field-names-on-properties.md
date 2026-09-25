---
id: FM-0015
title: properties do not record the Kalshi API field they mirror, and comparators have no strike_type code
type: feature
priority: 2
depends_on: []
touches:
  - src/core.ttl
  - src/kalshi.ttl
  - src/weather.ttl
  - src/fmo.ttl
  - shapes/vocabulary.ttl
  - scripts/term_signatures.py
  - scripts/test_shapes.py
  - CONTEXT.md
  - README.md
forbidden:
  - src/imports/**
  - shapes/thermaledge-export.ttl
  - shapes/thermaledge-export.pin.json
risk: low
acceptance:
  - claim: >-
      Each datatype property that mirrors a Kalshi API field carries that field
      name as a typed skos:notation, and each notation is in the documented
      field list.
    witness: make shapes, over shapes/vocabulary.ttl
  - claim: >-
      Each fm:Comparator individual used for Kalshi strikes carries its
      strike_type code, checked against the documented enumeration.
    witness: make shapes, over shapes/vocabulary.ttl
  - claim: >-
      A property whose field notation is removed or misspelt fails the shapes.
    witness: a mutant in scripts/test_shapes.py
  - claim: >-
      Remapping a field notation moves the property's semantics signature.
    witness: scripts/term_signatures.py --check
---

## Context

FM-0008 gave each Kalshi designation its API code as a typed `skos:notation`,
checked against the documented enumeration by `shapes/vocabulary.ttl`, so
ingest looks designations up by code rather than by label. FM-0009 did the
same for CF standard names on `wx:` terms. `kalshi.ttl:24` says field names
"mirror the Kalshi trading API".

## Problem

The properties are where that promise is not kept. Nothing in the graph ties
`yes_bid` to `ksh:yesBidCents`, `last_price` to `ksh:lastPriceCents`,
`close_time` to `ksh:closeTime`, `event_ticker` to `ksh:eventTicker`, or
`floor_strike`/`cap_strike` to `fm:floorValue`/`fm:capValue`. A handful of
field names appear inside scope notes, which nothing checks.

`strike_type` is the field `docs/design-notes.md` credits with making ingest
"close to mechanical", and the `fm:Comparator` individuals (`core.ttl:149-155`)
carry no code for it. Ingest therefore maps `strike_type: greater` by label,
which FM-0008 exists to stop. FM-0008 deferred this rather than rejecting it.

The next API drift will land on a property, and today it would be found by a
dated human re-read with nothing checked in to compare against.

## Out of scope

- A live-API check in CI. FM-0008 rejected it.
- NWS product field names. Lower value; a later spec if ingest needs it.
- `skos:altLabel` for field names. A notation is the lookup key; an altLabel is
  a synonym for humans.

## Notes for the agent

- Follow FM-0008's shape: a datatype per field family (e.g.
  `ksh:MarketFieldName`) so a notation says what kind of code it is.
- The notation for an `fm:` property that only Kalshi fills (`fm:floorValue`)
  belongs in `kalshi.ttl`, not `core.ttl`. The core stays venue-neutral; FM-0008
  left that question open and this should not close it by accident.
- Record the date the field list was checked, as `shapes/vocabulary.ttl:11`
  does for the enumerations.
- `term_signatures.py` already folds notations into `semantics_sha256`. Adding
  them moves every affected property's digest once; say so in the PR.
- New vocabulary: **field notation**. Add a `CONTEXT.md` entry.

## Comments
