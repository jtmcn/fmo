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
  - README.md
  - CONTEXT.md
forbidden:
  - src/**
  - shapes/**
  - examples/**
  - queries/**
risk: low
acceptance:
  - claim: >-
      Every rdfs:subClassOf between named classes asserted in src/core.ttl,
      src/weather.ttl or src/kalshi.ttl is drawn, and its subject is a node,
      whether or not the subject is minted. Today five of the six bridges are
      missing: prov:Entity, prov:Agent, prov:Activity, qudt:QuantityKind and
      qudt:QuantityKindDimensionVector.
    witness: make diagram-check, whose bridge comparison fails against today's generator on the five missing bridges; a mutant in scripts/test_diagram.py dropping one bridge edge
  - claim: >-
      Every subClassOf or subPropertyOf target asserted in a minted file has a
      prefix the map can name. An IRI curie() cannot name fails the check
      instead of dropping out of both the page data and the comparison.
    witness: make diagram-check, comparing raw IRIs; a mutant in scripts/test_diagram.py removing prov from NS
  - claim: >-
      The node set is exactly the minted classes, the ends of the bridges, the
      classes the map already reaches as a domain or range, and the ancestors
      of all of those up to bfo:entity. An imported class that nothing in a
      minted file mentions is not a node.
    witness: make diagram-check; a mutant in scripts/test_diagram.py adding prov:SoftwareAgent and its import-asserted edge
  - claim: >-
      Every borrowed prefix on the map has a display name carried in the page
      data. PROV classes show as "PROV-O", and none falls back to its bare
      prefix.
    witness: make diagram-check; a mutant in scripts/test_diagram.py deleting the prov entry from the page's external names
  - claim: >-
      A minted property's panel lists its super-properties outside FMO's
      namespaces, read off the graph: fm:hasInput shows prov:used, the other
      four PROV-aligned properties show theirs, and fm:hasAgent also shows
      bfo:BFO_0000057.
    witness: make diagram-check, which compares each property's supers against rdfs:subPropertyOf in the minted files and fails on an empty set; a mutant in scripts/test_diagram.py dropping one
  - claim: >-
      MAX_CROSSINGS is re-pinned to the count the new map measures, with PROV
      ordered after every other family.
    witness: make diagram-check (MAX_CROSSINGS)
---

## Context

FM-0022 imported a PROV-O subset, grounded it in BFO, and made five FMO
properties sub-properties of PROV ones. None of it shows up in `make diagram`.
There are two reasons:

- `NS` in `scripts/generate_diagram.py` has no `prov:` entry, so `curie()`
  returns nothing for a PROV IRI. `parents()` drops any edge with an end it
  cannot name, so even `fm:Agent ⊑ prov:Agent`, which starts at a minted class,
  is lost. Nothing fails: the missing IRI drops out of everything that would
  have compared it.
- A class becomes a node only when it is minted, or when the map reaches it as
  a domain or range, or as an ancestor of either. Edges come from the minted
  subjects plus the outline's rows (`build()`, the loop over `tree`). A bridge
  whose subject nothing else reaches never becomes a node. `qudt:Unit ⊑
  fm:MeasurementUnit` is drawn, but only because `qudt:Unit` is
  `fm:hasUnit`'s range. `qudt:QuantityKind` and
  `qudt:QuantityKindDimensionVector` under `fm:Designation` have never been
  drawn, and neither have the three PROV groundings in `src/core.ttl`.

`outline()`'s docstring still says the BFO skeleton is "not on the map".
FM-0021 put it there (`r["on"] = True`), and the docstring was never updated.

Property panels show domain and range. They don't show super-properties, so
`fm:hasInput ⊑ prov:used` has nowhere to appear.

## Problem

Someone looking at the map can't see where FMO's vocabulary meets the
vocabularies it borrows. That meeting point is where the grounding decisions in
`docs/design-notes.md` live: QUDT units as information content entities, PROV
entities as continuants, `fm:Agent` beneath `prov:Agent` rather than above it.

### Decisions already made

- **Bridges are added to the ancestor rule, not substituted for it.** A
  subClassOf between named classes asserted in `src/core.ttl`,
  `src/weather.ttl` or `src/kalshi.ttl` is drawn whatever its subject, and the
  subject becomes a node. The outline still climbs from every node to
  `bfo:entity` through the imports, so BFO's skeleton stays drawn and the is-a
  tree keeps its single root (`README.md`, "BFO's own classes between a
  borrowed class and entity"). What stays off the map is an imported class that
  nothing in a minted file mentions, such as `prov:SoftwareAgent`.
- **`prov:` joins `NS`, and the external names move into the page data.**
  `viz/src/ui.js`'s `EXTERNAL_NAME` falls back to the bare prefix when a name
  is missing, which is the `curie()` failure again, one layer up. The generator
  emits the names next to `NS`, and the check fails on a borrowed prefix
  without one. PROV classes are borrowed ground, like QUDT and BFO: nodes with
  no stanza.
- **PROV is ordered last explicitly.** `SIDE_ORDER` gives every borrowed prefix
  the same rank, 3, and breaks ties by label, so "agent" sorts ahead of
  `fm:Agent`'s siblings and pulls the tree across. A probe that added only
  `prov:` to `NS` measured 72 crossings, and `fm:Agent` moved from depth 4 to
  3. Giving `prov` its own `SIDE_ORDER` entry after every other family brought
  it to 12. Five is not reachable without changing `place()`, which is out of
  scope, so the pin moves and the PR body names each new crossing.
- **Super-properties outside FMO go on the property panel, not the map.** Each
  minted property gets a `supers` list: its `rdfs:subPropertyOf` targets in a
  borrowed namespace. The panel shows them as a "Sub-property of" row. The map
  draws no property-to-property edges, which keeps FM-0021's rule that
  relations are drawn on demand and the is-a tree is the picture at rest.
- **Derived independently, never listed.** `diagram-check` parses the three
  minted files itself and compares raw IRIs. It does not reuse `curie()`,
  `parents()` or the generator's per-module parse, because a derivation shared
  with the generator only checks the generator against itself. It also fails
  when the bridge set or the super-property set is empty, since two empty sets
  agree. Naming the five aligned properties in the checker would pass the day a
  sixth is added and not drawn.

## Out of scope

- Drawing PROV properties, or any property-to-property edge.
- `prov:SoftwareAgent` and other imported classes that no minted file mentions.
- Changing `place()` to reduce crossings beyond what ordering PROV last gives.

## Notes for the agent

- The generator builds one merged graph. To tell where an axiom was asserted,
  parse the three minted files on their own as well; `src_text` already reads
  them per file.
- `prov:Entity` and `prov:Activity` land as leaves with nothing under them.
  `fm:hasInput` and `fm:hasOutput` range over `bfo:entity`, not over PROV
  classes. That is the honest picture, not a layout defect.
- The check's "every node on its depth's row" assertion covers the new nodes,
  as long as depth is computed over the same edges that are drawn.
- Fix `outline()`'s docstring in the same change.
- The mutants in `test_diagram.py` run under `make diagram-negative`. Each one
  mutates the built data and requires `check()` to fail.
- Look at the result, don't just count it: render `build/ontology.html`
  headless (the Playwright cache has chrome-headless-shell) and inspect where
  the PROV nodes land.
- Vocabulary: add two entries to `CONTEXT.md` §4 alongside "the is-a tree".
  **Borrowed ground** is a class on the map from a namespace FMO does not mint.
  **Bridge** is a subClassOf asserted in a minted file whose subject is
  borrowed ground. Avoid "stub" and "bridged class", and use them in neither
  code nor prose.

## Comments

**2026-09-28 — resolved.** All six bridges drawn. The previous generator's `build()`, checked by
the new `diagram-check`, fails its bridge comparison naming the five that were
missing (four if only `prov:` is added to its `NS`, since `prov:Agent ⊑
continuant` is then reached through `fm:Agent`). The node set is
now 134 (27 borrowed). `fm:Agent` stays at depth 4, and `prov:Agent` and
`prov:Entity` sit at depth 2 under continuant, with `prov:Activity` at depth 3
under process. `MAX_CROSSINGS` moved from 5 to 12. All seven new crossings are the
one edge `fm:Agent ⊑ prov:Agent`, which climbs two rows and crosses
`fm:InformationBearingEntity ⊑ material entity`, fiat object part, object aggregate
and object under material entity, site under immaterial entity, and quality and
realizable entity under specifically dependent continuant. Five mutants were added
to `make diagram-negative`, which now passes 46 of 46.
