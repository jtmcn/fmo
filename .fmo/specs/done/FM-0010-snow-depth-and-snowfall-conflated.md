---
id: FM-0010
title: wx:SnowDepth and wx:TotalSnowfall do not say whether they mean new snow or snow on the ground
type: bug
priority: 3
depends_on: []
touches:
  - src/weather.ttl
  - queries/cf-mapping-expectations.json
  - queries/class-coverage-expectations.json
  - CONTEXT.md
forbidden:
  - src/imports/**
  - shapes/thermaledge-export.ttl
  - shapes/thermaledge-export.pin.json
risk: low
claimed_by: claude
acceptance:
  - claim: >-
      wx:SnowDepth and wx:TotalSnowfall each carry one CF standard name
      mapping, and neither is left in the ambiguous category of the CF ledger.
    witness: check_cf_mappings, under make validate
  - claim: >-
      Each term's definition and its parent class agree on whether it is new
      snow over an interval or snow lying on the ground at an instant.
    witness: src/weather.ttl, reviewed; no automated witness can read a definition
---

## Context

Found while mapping the `wx:` terms to CF standard names (FM-0009). CF
separates the two quantities that FMO's snow terms blur:
`thickness_of_snowfall_amount` (new snow over an interval) and
`surface_snow_thickness` (snow lying on the ground). NWS climate reports
separate them the same way: daily snowfall and snow depth are two values.

## Problem

- `wx:SnowDepth` is defined as "the settled depth of accumulated snow". That
  reads as snow on the ground. But its parent is `wx:PrecipitationDepth`,
  whose members inhere in a *portion of precipitate*: what fell, not what
  lies there.
- `wx:TotalSnowfall` is "the accumulated settled depth of snow at an observing
  site over a temporal interval", which could be the sum of new snowfall or
  the depth on the ground at the end.

A market settling on "snowfall" and a forecast of snow depth would currently
map to the same terms without anything noticing. This is the same kind of
confusion as the precipitation-versus-snowfall note on `wx:TotalSnowfall`, but
between two quantities that also share a dimension *and* a name.

## Out of scope

Any change to the other CF mappings.

## Notes for the agent

Decide whether snow on the ground is a quality of a portion of precipitate at
all, or of something else (a snowpack as a material entity). That is the BFO
question, and the answer decides where `wx:SnowDepth` goes. `wx:TotalSnowfall`
most plausibly means the NWS daily snowfall (new snow, `time: sum`), and
should say so in its definition. If a new class is needed for snow on the
ground, it needs a `CONTEXT.md` entry and a place in the class-coverage ledger.

When both are mapped, drop them from the `ambiguous` category of
`queries/cf-mapping-expectations.json`. The check fails on an entry for a
mapped term, so leaving one behind is not possible.

## Comments

**2026-09-25 — resolved.** The cause was the parent: `wx:SnowDepth` sat under
`wx:PrecipitationDepth`, a liquid-water-equivalent depth, while its own
definition was a settled depth. Snow on the ground *is* a portion of
precipitate (fallen and accumulated at a surface), so the BFO answer was a
subclass of the bearer, not a new material entity outside it:

- `wx:SnowCover`, a new subclass of `wx:PortionOfPrecipitate`: the snow lying on
  the ground.
- `wx:SnowDepth` now inheres in a snow cover and maps to
  `surface_snow_thickness`. It is no longer a precipitation depth.
- `wx:NewSnowDepth`, new: the settled depth of a snowfall's output, mapped to
  `thickness_of_snowfall_amount`. It follows the rain example's pattern.
- `wx:TotalSnowfall` is defined as the sum of new snow depths (NWS daily
  snowfall) and maps to `thickness_of_snowfall_amount` with `time: sum`.

Both settled depths are `owl:disjointWith wx:PrecipitationDepth`, and each
disjointness is pinned by a new `test_reason.py` case that files the class back
under it (unsatisfiable). I watched both cases report "accepted" before the
axioms went in. They are deliberately not disjoint from each other: snow
falling on bare ground is both.

The CF ledger's `ambiguous` category is now empty. The two negative cases that
anchored on the snow entries now inject their own entry, and a third case
proves that citing this spec, now in `done/`, fails as "tracks no open spec".
The two new classes are `unwritten` in the class-coverage ledger. No variable
for snow depth on the ground was added, since no market needs one yet.

