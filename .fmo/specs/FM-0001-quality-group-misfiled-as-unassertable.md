---
id: FM-0001
title: the quality group is misfiled as unassertable, and the rain example instantiates a quality
type: bug
priority: 2
depends_on: []
touches:
  - queries/class-coverage-expectations.json
forbidden:
  - src/**
  - scripts/**
  - README.md
risk: low
acceptance:
  - claim: >-
      The six quality-group classes no longer sit under `unassertable`. Each
      names, in its reason, the example that would instantiate it -- for
      temperature, a portion of air at the site bearing the quality with a
      datum reporting the maximum it attained, mirroring `rex:Datum-Precip`.
    witness: queries/class-coverage-expectations.json
  - claim: >-
      Nothing left under `unassertable` cites a sibling for its reason. Both
      survivors, `fm:Designation` and `fm:MeasurementUnit`, cite themselves.
    witness: check_class_coverage
  - claim: >-
      The ledger `_comment` no longer says one argument covers the whole
      quality group, which stops being true once the group moves.
    witness: queries/class-coverage-expectations.json
  - claim: >-
      `make validate` passes unchanged, and no `src/` file moved, so no version
      bump and no README status line.
    witness: make validate
---

Migrated from GitHub issue #21 (labelled `bug`). Supersedes the premise of #20.

## Context

That issue asks how best to record the argument that instantiating the
atmospheric qualities is a modelling error. The argument does not hold, so
neither of its options should be spent.

Six of the nine `unassertable` entries in
`queries/class-coverage-expectations.json` are the quality group:
`wx:AtmosphericQuality`, `wx:AirTemperature`, `wx:AtmosphericPressure`,
`wx:DewPoint`, `wx:RelativeHumidity`, `wx:WindSpeed` — plus `wx:WindDirection`,
which is the same case with a different external fact attached.

`unassertable` means, per the ledger's own `_comment`, that instantiating the
class "would assert something the ontology deliberately refuses." The ontology
refuses none of them.

## Problem

**The counterexample is already in the repo.**
`examples/kxrainnyc-2026-07-15.ttl:210` mints a quality instance and points the
settlement datum at it:

```turtle
rex:Depth-2026-07-15 a wx:PrecipitationDepth ;
    rdfs:label "the depth that portion of precipitate occupied" ;
    bfo:BFO_0000197 rex:Precipitate .           # inheres in
```

```turtle
rex:Datum-Precip a wx:WeatherObservationDatum ;
    # fm:isAbout commits to the relatum existing, which is why a proposition never
    # carries it -- Prop-Rain points at the target, not this. The rain already fell,
    # so the datum can point at the quality it reports. First instance anywhere.
    fm:isAbout rex:Depth-2026-07-15 .
```

`wx:PrecipitationDepth` (`src/weather.ttl:125`) and `wx:AtmosphericQuality`
(`src/weather.ttl:90`) are structurally identical: `rdfs:subClassOf
bfo:BFO_0000019` plus an `inheres in` restriction, one onto
`wx:PortionOfPrecipitate`, the other onto `wx:PortionOfAir`. One is instantiated
by a worked example. The other is filed as refused.

**Where the reasoning went wrong.** `wx:AtmosphericQuality`'s ledger reason says
a forecast concerns a future fact, so the quality instance it would be about
does not exist when the forecast is issued. That is modelling decision 2, and
decision 2 is scoped to **propositions** — `README.md:157`, `src/core.ttl:379`,
`docs/design-notes.md:46` all argue the forecast side only. It constrains what a
forecast may point at. It says nothing about what an example may instantiate.
Settlement is past-tense, and that is the door the rain example walked through.

The ledger already half-notices this. `wx:PortionOfAir` sits under `unwritten`,
its reason observing that "wx:PortionOfPrecipitate shows the analogous class is
assertable once a process is recorded." The bearer is assertable-but-unwritten
while every quality that inheres in it is refused. Both cannot be right.

**`wx:AirTemperature`'s scope note argues against the entry that cites it.**
`src/weather.ttl:102` says "Yesterday's high" is not an instance of this class;
it is a measurement datum reporting the maximum magnitude *this quality*
attained over an interval. The note presupposes the quality instance exists and
is referable — it is what the maximum is a maximum *of*. It denies one
identification, not the instantiation. Nobody has written that example. That is
`unwritten`, not `unassertable`. Same for `wx:WindSpeed`, whose note explains why
the quality is *retained* when the underlying phenomenon is a process — an
argument for the class existing, not against instantiating it.

**Not a stale-ordering accident.** The ledger (`8bb5f97`) landed 45 commits
after the rain example (`6f451c9`). The counterexample was in the repo when the
classification was written.

## Out of scope

**Tightening the justifier check.** `scripts/validate.py:1259` verifies only that
the justifier *has* a `skos:scopeNote`, never that the note argues the
prohibition. That is how six entries came to rest on a note arguing the
opposite. Tightening it is likely not worth the machinery — but it is why
writing five more notes, as #20 proposed, would have made the pin feel stronger
while changing nothing.

## Notes for the agent

Ledger-only: no `src/` change, so no version bump and no README status line.
`semantics_sha256` does not move, and `definition_sha256` — the digest
`README.md:385` says ThermalEdge actually pins — was never in play: it digests
`skos:definition` alone (`scripts/term_signatures.py:103`), and nothing here
touches a definition.

**Worth deciding as part of this**: whether the two wind qualities go to
`unwritten` or to `unlisted` alongside `wx:AirMotion`. `unlisted` fits the
external fact (no wind market is listed) and requires a `checked` date;
`unwritten` fits the fact that no example has been written. They are not the
same claim and the entries should not straddle them.

Once this lands, #20 dissolves without a scope note being written or moved.

## Comments
