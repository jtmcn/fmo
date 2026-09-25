---
id: FM-0014
title: time properties accept a timestamp with no timezone offset
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
  - README.md
forbidden:
  - src/imports/**
  - shapes/thermaledge-export.ttl
  - shapes/thermaledge-export.pin.json
risk: low
acceptance:
  - claim: >-
      Every time-valued datatype property has range xsd:dateTimeStamp.
    witness: src/*.ttl; make reason stays consistent over schema plus examples
  - claim: >-
      A dateTime literal without an offset on any of those properties fails
      validation.
    witness: a new registered check in scripts/validate.py, with a negative test in scripts/test_validate.py that strips the offset from one literal
---

## Context

Eight properties are ranged `xsd:dateTime`: `fm:instantDateTime`,
`fm:referenceTime`, `wx:issuanceTime`, `wx:cycleTime`, `ksh:openTime`,
`ksh:closeTime`, `ksh:expectedExpirationTime` and `ksh:latestExpirationTime`. In `xsd:dateTime` the offset is optional.

## Problem

Decision 3 hangs on climatological-day boundaries in local standard time. A
timestamp without an offset silently moves that boundary, and XSD orders
offset-less values only partially against offset-bearing ones, so comparisons
can come out indeterminate rather than wrong-and-visible.

The rule exists as prose: `fm:instantDateTime`'s scope note says "Always record
the offset". `check_lead_times` fails only when one side has an offset and the
other does not; two offset-less values pass. Every literal in `examples/` has
an offset today, which is the pattern of a rule held by care rather than by a
check.

## Out of scope

The export shapes. They constrain no time property today, so this needs no
re-pin. Adding `sh:datatype xsd:dateTimeStamp` to them is a separate decision
about the export contract.

## Notes for the agent

- `xsd:dateTimeStamp` is in the OWL 2 datatype map, so HermiT accepts it. Check
  that rdflib parses `^^xsd:dateTime` values under a `dateTimeStamp` range
  without complaint; the literals themselves can stay typed `xsd:dateTime`.
- Changing a range moves `semantics_sha256` for eight properties. Say so in the
  PR so ThermalEdge's re-pin is expected.
- The new check is population `data` and needs `coverage()`.

## Comments
