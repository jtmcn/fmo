---
id: FM-0024
title: Draw the bridges to borrowed vocabularies on the map, and show a property's PROV super-properties
type: feature
priority: 2
depends_on:
  - FM-0022
touches:
  - scripts/generate_diagram.py
  - scripts/test_diagram.py
  - viz/src/ui.js
  - viz/src/graph.js
  - viz/src/data.js
  - README.md
forbidden:
  - src/**
  - shapes/**
  - examples/**
  - queries/**
risk: low
acceptance:
  - claim: >-
      Every rdfs:subClassOf between named classes asserted in a minted module
      is drawn, whether or not its subject is minted: the QUDT bridges
      (qudt:Unit under fm:MeasurementUnit, and the rest) and the PROV bridges
      (prov:Entity, prov:Agent under continuant, prov:Activity under process,
      fm:Agent under prov:Agent) all appear.
    witness: make diagram-check, which derives the bridge set from the minted modules; a mutant in scripts/test_diagram.py dropping one bridge edge
  - claim: >-
      Edges asserted only inside src/imports/ are not drawn, so the map does
      not grow a copy of BFO's, QUDT's or PROV's own hierarchy.
    witness: make diagram-check (prov:SoftwareAgent is absent: its one parent is asserted in prov-subset.ttl); a mutant in scripts/test_diagram.py adding it
  - claim: >-
      PROV classes are borrowed-ground nodes that the panel names "PROV-O", on
      their BFO parent's depth row like every other node.
    witness: make diagram-check (the depth-row assertion already covers every node); the EXTERNAL_NAME entry in viz/src/ui.js, reviewed
  - claim: >-
      A minted property's panel lists its super-properties outside FMO's
      namespaces, read off the graph: fm:hasInput shows prov:used, and the
      other four aligned properties show theirs.
    witness: make diagram-check, which compares each property's supers against rdfs:subPropertyOf in the schema; a mutant in scripts/test_diagram.py dropping one
  - claim: >-
      The subClassOf crossing ceiling is not raised past 5, or the spec's
      Comments name each new crossing and why no ordering removes it.
    witness: make diagram-check (MAX_CROSSINGS); this file's Comments
---

## Context

FM-0022 imported a PROV-O subset, grounded it in BFO, and made five FMO
properties sub-properties of PROV ones. None of it shows up in `make diagram`.
There are two reasons:

- `NS` in `scripts/generate_diagram.py` has no `prov:` entry, so `curie()`
  returns nothing for a PROV IRI. Even `fm:Agent ⊑ prov:Agent`, which starts at
  a minted class, is dropped.
- The map draws only subClassOf edges whose subject is minted. A bridge axiom
  points the other way (`prov:Entity ⊑ bfo:continuant`,
  `qudt:Unit ⊑ fm:MeasurementUnit`), so no bridge has ever been drawn. QUDT's
  have been missing since the first map. PROV's made it visible, because the
  grounding is the point of that import.

Property panels show domain and range. They don't show super-properties, so
`fm:hasInput ⊑ prov:used` has nowhere to appear.

## Problem

Someone looking at the map can't see where FMO's vocabulary meets the
vocabularies it borrows. That meeting point is where the grounding decisions in
`docs/design-notes.md` live: QUDT units as information content entities, PROV
entities as continuants, `fm:Agent` beneath `prov:Agent` rather than above it.

### Decisions already made

- **The rule: draw what FMO asserts.** A subClassOf between named classes is
  drawn when it is asserted in a minted module (`core.ttl`, `weather.ttl`,
  `kalshi.ttl`), whatever its subject. Being minted is a fact about the
  subject; being asserted here is a fact about the axiom, and a bridge is an
  axiom FMO makes about someone else's class. The vendored and generated files
  under `src/imports/` stay undrawn, so the map doesn't grow a copy of BFO's,
  QUDT's or PROV's hierarchy.
- **`prov:` joins `NS`** and gets an `EXTERNAL_NAME` entry, "PROV-O", in
  `viz/src/ui.js`. PROV classes are borrowed ground, like QUDT and BFO: stub
  nodes with no stanza, placed last in their family order.
- **Super-properties outside FMO go on the property panel, not the map.** Each
  minted object or datatype property gets a `supers` list: its
  `rdfs:subPropertyOf` targets in a borrowed namespace, as curies. The panel
  shows them as a "Sub-property of" row. The map draws no property-to-property
  edges, which keeps FM-0021's rule that relations are drawn on demand and the
  tree is the picture at rest. `bfo:BFO_0000057` on `fm:hasAgent` is a
  super-property too and appears the same way.
- **Derived, never listed.** `diagram-check` computes the bridge set and each
  property's `supers` from the parsed modules, and compares the page data
  against them. Naming the five aligned properties in the checker would pass
  the day a sixth is added and not drawn.

## Out of scope

- Drawing PROV properties, or any property-to-property edge.
- `prov:SoftwareAgent` and other imported classes that no minted module
  places.
- Changing `place()` to reduce crossings beyond what ordering borrowed ground
  last already gives.

## Notes for the agent

- The generator builds one merged graph. To tell where an axiom was asserted,
  parse the three minted modules on their own as well; `src_text` already reads
  them per module.
- The check's "every node on its depth's row" assertion covers the new stubs,
  as long as depth is computed over the same edges that are drawn.
- `test_diagram.py` mutates the built data and requires `check()` to fail.
  Add one mutant per new claim: a dropped bridge edge, a drawn import-only
  edge, and a dropped super-property.
- Look at the result, don't just count it: render `build/ontology.html`
  headless (the Playwright cache has chrome-headless-shell) and inspect where
  the PROV stubs land.
- No new vocabulary. "Borrowed ground" and "bridge" are the map's existing
  words; if `CONTEXT.md` needs "bridge axiom", add it there in the same PR.

## Comments
