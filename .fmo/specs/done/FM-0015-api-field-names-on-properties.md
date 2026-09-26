---
id: FM-0015
title: properties do not record the Kalshi API field they mirror, and comparators have no strike_type code
type: feature
priority: 2
depends_on:
  - FM-0011
touches:
  - src/core.ttl
  - src/kalshi.ttl
  - src/weather.ttl
  - src/fmo.ttl
  - shapes/vocabulary.ttl
  - scripts/term_signatures.py
  - scripts/test_shapes.py
  - examples/**
  - queries/cq05-bracket-coherence.rq
  - queries/cq05-bracket-coherence.expected
  - queries/cq08-order-flow-payout.rq
  - queries/cq08-order-flow-payout.expected
  - queries/axiom-expectations.json
  - scripts/validate.py
  - scripts/test_validate.py
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
    witness: scripts/term_signatures.py --check, field_name_mutant
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

**2026-09-25 — scoped against the live API before starting; decisions made.**
Checked against Kalshi Trade API 3.31.0 (`https://docs.kalshi.com/openapi.yaml`).
Four findings change the spec:

- **No price field is in cents any more.** `Market` has no `yes_bid`,
  `yes_ask`, `last_price`, `volume` or `open_interest`. Prices are
  `*_dollars` fixed-point strings (`yes_bid_dollars`, `yes_price_dollars`),
  and counts are `*_fp` fixed-point strings (`volume_fp`, `count_fp`).
  - Five FMO properties have no cents field to mirror: `ksh:yesBidCents`,
    `ksh:yesAskCents`, `ksh:lastPriceCents`, `ksh:limitPriceCents`,
    `ksh:executionPriceCents`.
  - `ksh:payoutAmountCents` does have one: `Settlement.revenue` is still
    an integer in cents.
- **Two name traps.** `ksh:settlementValue`, the observed value applied to
  the condition, is `Market.expiration_value`. It is not
  `settlement_value_dollars` or `Settlement.value`: both are payouts.
- **`strike_type` has eight codes:** `greater`, `greater_or_equal`,
  `less`, `less_or_equal`, `between`, `functional`, `custom`,
  `structured`.
  - `fm:EqualTo` has no code.
  - `functional` and `structured` have no FMO comparator.
  - Neither is defined beyond the schema:
    - `functional_strike` is a "mapping from expiration values to
      settlement values".
    - `structured` ties to the `/structured_targets` catalogue of named
      entities.
  - The prose docs add nothing.
- **The README's "field names checked against the live API on
  2026-08-17" is stale** for every price and count field.

Decisions (maintainer):
- **Rename the five dollar-priced properties to `*Dollars`,** retiring the
  `*Cents` ones to tombstones under ADR 0003. This is a breaking change, so
  it bumps the version and sets `owl:incompatibleWith` on the prior version,
  and hence the new dependency on FM-0011. `ksh:payoutAmountCents` stays.
- **Mint comparators for `functional` and `structured`** so every
  documented code is carried. Their definitions rest on the schema lines
  quoted above, and each should cite that source and say how thin it is.
  `fm:EqualTo` carries no code; its scope note says so, as `ksh:Voided`'s
  does.

**2026-09-25 — resolved in 0.19.0**, which is `owl:incompatibleWith` 0.18.0
on `kalshi` and the top module.

**Renames and tombstones.** `ksh:yesBidDollars`, `ksh:yesAskDollars`,
`ksh:lastPriceDollars`, `ksh:limitPriceDollars` and
`ksh:executionPriceDollars` replace the `*Cents` five, which are now
tombstones whose history notes say to divide by one hundred.
- Every example value was converted ÷100, along with the prose that stated
  prices in cents.
- cq05 and cq08 report dollars, and their `.expected` diffs are exactly
  ÷100 in the renamed columns.
- `ksh:payoutAmountCents` stays, and its new scope note says why no field
  is it.

**Field names.** Six `*FieldName` datatypes, one per API schema, because
`ticker` and `yes_price_dollars` each recur across schemas. 29 properties
carry their field name, including `fm:floorValue`, `fm:capValue` and
`fm:hasComparator`, whose notations live in `kalshi.ttl` so the core stays
venue-neutral.
- `shapes/vocabulary.ttl` gives each family a shape whose `sh:in` is that
  schema's full 3.31.0 field list, generated from the OpenAPI file rather
  than retyped.
- The enumeration-agreement check in `test_shapes.py` now covers codes
  only, because a field list is closed but need not be carried.
- Three field-name mutants.
- `term_signatures.py --check` gains `field_name_mutant`. The generic
  notation mutant remaps the first notation in IRI order, which is now a
  comparator's code, so it no longer exercised a property.

**Strike types.** The six matching comparators carry their codes, and the
new `ksh:FunctionalStrike` and `ksh:StructuredStrike` are minted.
- Both definitions rest on the schema's one-line descriptions, and their
  scope notes say so. `functional` strains `fm:Comparator`'s definition,
  which is about truth, not a settlement mapping.
- `fm:EqualTo` is excepted, with a scope note.
- An `owl:AllDifferent` over all nine comparators is exempt in the axiom
  ledger for the same reason as the core's.
- Three mutants.

**Left unmapped on purpose:**
- `ksh:limitPriceDollars`: which price field holds it depends on
  direction.
- `ksh:restingQuantity`: order book levels are unnamed arrays.
- `ksh:payoutAmountCents`: `revenue` sums every lot in the market.

**Filed.** FM-0019: the API has moved order direction to one
`outcome_side` bit, and `side`/`action`, which `ksh:hasSide` and
`ksh:hasAction` map to for now, are deprecated past their promised date.
