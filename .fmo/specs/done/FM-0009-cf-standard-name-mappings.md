---
id: FM-0009
title: the wx qualities and weather variables carry no mapping to CF standard names
type: feature
priority: 3
depends_on: []
touches:
  - src/weather.ttl
  - scripts/validate.py
  - scripts/test_validate.py
  - scripts/term_signatures.py  # only if the mapping is judged semantic; see notes
  - CONTEXT.md
  - README.md
  - docs/design-notes.md
  - queries/cf-mapping-expectations.json  # the unmapped ledger, added at resolution
  - scripts/ledger.py  # docstring: four ledgers, added at resolution
  - CLAUDE.md  # the ledger count, added at resolution
  - .fmo/specs/FM-0010-snow-depth-and-snowfall-conflated.md  # filed per the notes
forbidden:
  - src/imports/**
  - shapes/thermaledge-export.ttl
  - shapes/thermaledge-export.pin.json
  - examples/**
  - src/kalshi.ttl
risk: low
claimed_by: claude
acceptance:
  - claim: >-
      Every subclass of wx:AtmosphericQuality and wx:PrecipitationDepth, and
      every wx:WeatherVariable individual, either carries exactly one CF
      standard name mapping or is listed as unmapped with a reason.
    witness: check_cf_mappings, under make validate
  - claim: >-
      The check fails on a term with neither a mapping nor an unmapped entry,
      on an unmapped entry naming a term that has since gained a mapping, and on
      a mapping object outside the CF standard name namespace.
    witness: scripts/test_validate.py, one negative test per defect
  - claim: >-
      The check fails when it traversed nothing, and is registered with the
      population that empties it.
    witness: make meta
  - claim: >-
      No CF IRI is declared an owl:Class, and none is linked by
      owl:equivalentClass or rdfs:subClassOf. The mapping is annotation, not
      import.
    witness: check_cf_mappings (asserts it), plus make reason staying consistent
  - claim: >-
      The mapping predicate is declared an owl:AnnotationProperty, so the
      modules stay OWL DL, as skos:notation already is in kalshi.ttl.
    witness: make reason
  - claim: >-
      The choice of CF over SOSA, and of annotation over import, is written down
      with the argument rather than left implicit.
    witness: docs/design-notes.md
---

## Context

FMO imports two external ontologies: BFO 2020 and a generated QUDT subset.
Nothing in `weather.ttl` points at a third-party weather vocabulary. The two
candidates were SOSA/SSN and CF standard names.

They answer different questions. SOSA is an observation *pattern*: Observation,
Sensor, FeatureOfInterest, ObservableProperty, Procedure, Result. `weather.ttl`
already models that pattern, grounded in BFO (`wx:WeatherObservation`,
`wx:WeatherObservationDatum`, `wx:MeasurementProtocol`, `wx:WeatherStation`).
SOSA makes no BFO commitment. Importing it would need grounding in `core.ttl`
as QUDT did, and `sosa:Observation` is an act, while FMO's observation record
is an information content entity. The result would be a second observation
model and a modelling argument, for interoperability that
`docs/design-notes.md` defers until the ontology is published for reuse.

CF standard names are a controlled list of *variable* names, each with a
canonical unit. They correspond to the `wx:` qualities, and CF's
`cell_methods` correspond to the statistics that the `wx:WeatherVariable`
individuals encode.

## Problem

Forecast model output (NetCDF, and GRIB once read through CF-aware tools)
names its variables in CF. The settlement side of FMO is described in NWS
terms, and nothing connects the two. A consumer bringing a forecast in has to
work out by hand that `wx:MaximumAirTemperature` is `air_temperature` with
`time: maximum`, and that `wx:TotalPrecipitation` is
`lwe_thickness_of_precipitation_amount`, not `precipitation_amount`, which is a
mass per area. The second mistake is a dimension error that would not show
until values were compared.

## Out of scope

- **SOSA/SSN.** Not imported and not mapped here. Revisit if FMO data has to be
  read by SOSA-speaking tools; `skos:closeMatch` from the observation classes
  would be the first step, not an import.
- **Vendoring the CF standard name table.** A generated subset, like
  `qudt-subset.ttl`, would let a check prove each mapped name exists and
  compare its canonical unit against `wx:conventionalUnit`. That is a follow-up
  spec. This one checks the form of the IRI, not whether the name exists.
- **WMO/GRIB parameter codes.** Different vocabulary, different spec.
- **Changing any `wx:` definition** to fit CF. If a mapping cannot be chosen
  without a definition changing, record that as a finding (see the notes);
  don't resolve it here.

## Notes for the agent

**Predicate.** For the quality classes, use `skos:closeMatch`, not
`skos:exactMatch`. A BFO quality and a variable name are different kinds of
thing, and `exactMatch` is transitive, which is too strong across that gap.
Never use `owl:equivalentClass`. For the `wx:WeatherVariable` individuals, the
standard name alone leaves out the statistic, so the mapping has to carry the
cell method too. A minted annotation property (working name `wx:cfCellMethods`,
a plain string such as `"time: maximum"`) is the likely shape. Minting it needs
a `CONTEXT.md` entry in the same change, and `rdfs:label` and `skos:definition`
like every minted term.

**IRI form.** The CF standard names are published as SKOS by the NERC
Vocabulary Server. Confirm the current IRI pattern before committing to it
(believed to be `http://vocab.nerc.ac.uk/standard_name/<name>/`, with a P07
collection form as an alternative). Record the table version you checked
against in `docs/design-notes.md`.

**Expected mappings, to verify rather than trust:**

| term | CF standard name | cell methods |
|---|---|---|
| `wx:AirTemperature` | `air_temperature` | |
| `wx:DewPoint` | `dew_point_temperature` | |
| `wx:RelativeHumidity` | `relative_humidity` | |
| `wx:AtmosphericPressure` | `air_pressure` (not `air_pressure_at_mean_sea_level`: the definition is ambient pressure) | |
| `wx:WindSpeed` | `wind_speed` | |
| `wx:WindDirection` | `wind_from_direction` (the definition says "from which") | |
| `wx:PrecipitationDepth` | `lwe_thickness_of_precipitation_amount` | |
| `wx:MaximumAirTemperature` | `air_temperature` | `time: maximum` |
| `wx:MinimumAirTemperature` | `air_temperature` | `time: minimum` |
| `wx:MeanAirTemperature` | `air_temperature` | `time: mid_range`, **not** `time: mean`. The scopeNote says the NWS daily mean is the midpoint of max and min. Confirm `mid_range` is in CF Appendix E. |
| `wx:TotalPrecipitation` | `lwe_thickness_of_precipitation_amount` | `time: sum` |
| `wx:PeakWindGust` | `wind_speed_of_gust` | `time: maximum` |
| `wx:MaximumSustainedWindSpeed` | `wind_speed` | `time: maximum`. The averaging period lives in the protocol, per the scopeNote, so the cell method does not state it. |

**The snow terms are the likely finding.** `wx:SnowDepth` is defined as the
settled depth of accumulated snow, which reads like CF
`surface_snow_thickness` (snow on the ground). Yet it sits under
`wx:PrecipitationDepth`, whose members inhere in a portion of precipitate.
`wx:TotalSnowfall` is "accumulated settled depth of snow" over an interval,
which could be `thickness_of_snowfall_amount` (new snow) or the change in
snow on the ground. NWS reports snowfall and snow depth as separate values.
If the CF mapping cannot be picked uniquely, that ambiguity is in FMO, not in
CF. List the term as unmapped, put the reason in the ledger, and file it as
its own spec rather than fixing the definition here.

**Unmapped terms need a ledger.** The "unmapped with a reason" claim means a
checked-in ledger, and per `CLAUDE.md` it goes through `scripts/ledger.py`:
`ledger.audit()` with `handles=`, and category keys passed to `ledger.load()`.
Don't write the set arithmetic a fourth time.

**Check registration.** The population is the schema (the `wx:` terms), so
`@check(takes=("schema",), population="schema", reason=…)` and
`coverage(always=True)`. `make meta` proves it by sweeping against an empty
graph.

**Signatures.** Decide whether the mapping belongs in `semantics_sha256`. It
does if ingest might look a term up by its CF name, as it does for Kalshi API
codes by `skos:notation`, and otherwise it is documentation. Write down the
reasoning either way. If it goes in, add the matching mutant alongside
`notation_mutant`.

**Version.** Additive annotations only, so no bump, following FM-0008.

## Comments

**2026-09-25 — resolved.** Every claim's witness passes under `make test`,
with HermiT reporting the modules and examples consistent.

- 13 of 16 terms are mapped: seven qualities with `skos:closeMatch`, six weather
  variables with the name plus `wx:cfCellMethods`. Verified against CF
  standard name table v95 (2026-09-16) and CF 1.12 Appendix E. All 10 names
  resolve at `http://vocab.nerc.ac.uk/standard_name/<name>/`, and a bogus one
  404s. `mid_range` is in Appendix E ("Average of maximum and minimum"), so
  `wx:MeanAirTemperature` uses it.
- 3 are in `queries/cf-mapping-expectations.json`: `wx:AtmosphericQuality`
  under `no-counterpart`, and both snow terms under `ambiguous`, tracked by
  **FM-0010**. The snow finding held up: `wx:SnowDepth`'s definition reads as
  snow on the ground while its parent is precipitate.
- The check refuses the P07 collection form. It names the same concept, but
  ingest would have to resolve a second spelling.
- `check_documentation` now covers minted annotation properties.
  `wx:cfCellMethods` is the first one, and would otherwise have been skipped.
- Signatures: the mapping and the cell method are both in `semantics_sha256`,
  since ingest resolves by them as it does by API code. Each has a mutant in
  `term_signatures.py --check`, and each was seen to fail with its line
  removed from the rendering.
- No version bump here. The stated precedent was wrong: FM-0008 did bump
  (0.12.0 to 0.13.0) for an additive change. The bump is made once, to
  0.14.0, by FM-0010, which lands with this in one stack.

