---
id: FM-0019
title: Kalshi now states order direction as one outcome side, and FMO models side plus action
type: feature
priority: 2
depends_on:
  - FM-0015
touches:
  - src/kalshi.ttl
  - src/core.ttl
  - src/weather.ttl
  - src/fmo.ttl
  - shapes/vocabulary.ttl
  - scripts/test_shapes.py
  - examples/kxhighny-2026-08-15-trading.ttl
  - queries/cq08-order-flow-payout.rq
  - queries/cq08-order-flow-payout.expected
  - CONTEXT.md
  - README.md
  - docs/design-notes.md
forbidden:
  - src/imports/**
  - shapes/thermaledge-export.ttl
  - shapes/thermaledge-export.pin.json
risk: elevated
acceptance:
  - claim: >-
      An order's direction is modelled so that buy-yes and sell-no are the
      same direction, as the API's outcome_side states it, or the design notes
      say why FMO keeps the two apart.
    witness: docs/design-notes.md, reviewed; CQ8 still answers
  - claim: >-
      The properties recording an order's direction and price carry the
      current, non-deprecated API field names, checked by make shapes.
    witness: make shapes, over shapes/vocabulary.ttl
  - claim: >-
      Any term the migration retires is a tombstone under ADR 0003.
    witness: make lineage
---

## Context

Found while doing FM-0015 against Kalshi Trade API 3.31.0. The Order schema
marks `side` (yes/no) and `action` (buy/sell) deprecated. It says "Use
`outcome_side` (or `book_side`) instead", and promises the old fields only
until May 14, 2026, which has passed.

`outcome_side` is a single directional bit. Buy-yes and sell-no both produce
`yes`; buy-no and sell-yes both produce `no`. `book_side` carries the same bit
as `bid`/`ask`. Both parties to a match trade at the same price `p`.

## Problem

FMO's trading layer is built on the pair the API is retiring:

- `ksh:hasSide` and `ksh:hasAction` relate an order to FM-0008's
  `ksh:ContractSide` and `ksh:OrderAction` designations, with codes typed
  `ksh:SideCode` and `ksh:ActionCode`.
- FM-0015 mapped both properties to the deprecated `side` and `action`
  fields, because they are still documented. The next API release may drop
  them.
- `ksh:limitPriceDollars` is deliberately unmapped. The Order schema has
  `yes_price_dollars` and `no_price_dollars`, and which one holds an order's
  limit depends on the direction model this spec decides.

The semantics question matters more than the field names. Under the API's
model, "sell yes" and "buy no" are one direction. In FMO they are different
(action, side) pairs that happen to be economically equivalent. Whether FMO
should identify them is a modelling decision, not a rename.

## Out of scope

- Fills (`Fill`) and the `book_side` vocabulary beyond what the Order needs.
- Removing `ksh:SideCode`/`ksh:ActionCode` while the API still documents the
  deprecated fields. Retire them when the fields go.

## Notes for the agent

- Read the API's "Order direction" guide (`/getting_started/order_direction`
  on docs.kalshi.com) before modelling. The schema descriptions alone were
  enough to find this, not to settle it.
- The contract side of a lot (`ksh:YesContract`/`ksh:NoContract`) is a
  different fact from an order's direction and should not move with it.
- New vocabulary likely: **outcome side**. It needs a `CONTEXT.md` entry,
  with "side" alone on its _Avoid_ list.

## Comments
