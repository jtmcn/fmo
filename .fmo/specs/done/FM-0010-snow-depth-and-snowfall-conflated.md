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
  # Added at resolution: the version bump, the axiom ledger and reasoner cases for
  # the new disjointness, re-anchored negative cases, and the prose that described
  # the snow terms as unmapped.
  - src/core.ttl
  - src/kalshi.ttl
  - src/fmo.ttl
  - queries/axiom-expectations.json
  - scripts/test_reason.py
  - scripts/test_validate.py
  - README.md
  - docs/design-notes.md
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

**2026-09-25 — reworked after review.** Review found that the first resolution
fixed the confusion for settled depth and brought it back for water
equivalent. With `wx:SnowCover` under `wx:PortionOfPrecipitate`, the bearer of
`wx:PrecipitationDepth` (the water equivalent of what fell) included snow on
the ground as well, which CF names separately
(`lwe_thickness_of_surface_snow_amount`). The fault was in the bearer, so the
rework fixes it there:

- `wx:SnowCover` is now a sibling of `wx:PortionOfPrecipitate` under material
  entity. A cover persists while gaining and losing matter, including drifted
  snow that never fell at the site. A portion is individuated by the process
  that output it.
- `wx:PortionOfPrecipitate`'s definition is narrowed to "output at a surface by
  a precipitation process", which is how the rain example already used it.
- The three depths are one `owl:AllDisjointClasses` block. A third reasoner
  case (new snow depth filed under snow depth) pins it, and it was seen
  accepted before the block went in. My earlier argument that snow on bare
  ground "is both" was about the bearer, and it fails once cover and portion
  are distinct.
- Cover and portion are not declared disjoint. `inheres in` is not functional
  in BFO 2020, so disjoint bearers would not make their qualities disjoint,
  and the qualities are disjoint directly.
- The "usually less" claim is gone from `wx:TotalSnowfall`, and the spec id is
  gone from `wx:SnowDepth`'s scope note.
- Version 0.14.0, across the four modules and README. The first resolution
  claimed FM-0008 as precedent for not bumping; FM-0008 did bump.

