---
id: FM-0018
title: FM-0008 rejects SKOS mappings for a domain that FM-0009's closeMatch carries too
type: decision
priority: 3
depends_on: []
touches:
  - docs/design-notes.md
  - .fmo/specs/done/FM-0008-designation-api-codes.md
forbidden:
  - src/**
  - shapes/**
  - scripts/**
risk: low
acceptance:
  - claim: >-
      docs/design-notes.md states one reason for or against SKOS mapping
      properties on FMO classes, and that reason is true of both skos:closeMatch
      and skos:exactMatch as FMO declares them.
    witness: docs/design-notes.md, reviewed
  - claim: >-
      If the reason FM-0008 gave does not hold, FM-0008 carries a comment saying
      so and naming the reason that does.
    witness: .fmo/specs/done/FM-0008-designation-api-codes.md, under ## Comments
---

## Context

FM-0008 (Out of scope) rejected SKOS mapping properties to IAO:

> SKOS gives `skos:exactMatch` a domain of `skos:Concept`, so any RDFS-aware
> load of SKOS would type FMO's classes as concepts. That's the
> class/individual crossover (punning) the design notes avoid on purpose.

FM-0009 then put `skos:closeMatch` on nine `wx:` classes and seven
individuals, pointing at CF standard names. `docs/design-notes.md` ("CF
standard names, and not SOSA") explains choosing `closeMatch` over `exactMatch`
by strength: `exactMatch` is transitive and too strong between a BFO quality
and a variable name. It says nothing about the domain.

## Problem

In the SKOS RDF schema, `skos:semanticRelation` has domain and range
`skos:Concept`; `skos:mappingRelation` is a sub-property of it, and
`skos:closeMatch` of that. So `closeMatch` has the same `skos:Concept` domain
FM-0008 objected to. The two records cannot both be right as written:

- **Either FM-0008's reason holds**, and FM-0009 took on the exposure FM-0008
  refused. Then the CF mappings need another predicate, or the exposure needs
  accepting in writing.
- **Or it does not.** `src/weather.ttl:541` declares `skos:closeMatch a
  owl:AnnotationProperty`, and SKOS is not imported. In OWL 2 DL an annotation
  property carries no domain semantics, so nothing types an FMO class as a
  concept unless someone loads SKOS's RDFS alongside. The same declaration
  would defuse `exactMatch` equally. Then IAO mappings were rejected on a
  reason that does not hold, and the reason left is the one the IAO section
  already gives: no consumer needs standard IRIs.

## Out of scope

- Adding IAO or SOSA mappings. Whichever way this goes, those stay deferred
  until the ontology is published for reuse.
- Changing the CF mappings unless the decision is the first branch.

## Notes for the agent

- This is a decision for the maintainer; do not implement either branch
  unattended.
- Check the claim about SKOS's schema against the W3C `skos.rdf` rather than
  restating it from here.
- If the second branch wins, the design-notes paragraph belongs beside
  "Annotation, not import." in the CF section: the annotation declaration is
  what keeps the SKOS domain out of the model, and nothing checks that SKOS
  stays unimported. Consider whether that deserves a validator check.

## Comments
