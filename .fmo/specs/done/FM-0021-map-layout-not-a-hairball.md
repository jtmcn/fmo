---
id: FM-0021
title: The map lays out the is-a hierarchy as a tree and shows relations on demand
type: feature
priority: 3
depends_on:
  - FM-0020
touches:
  - viz/src/layout.js
  - viz/src/graph.js
  - viz/src/main.js
  - viz/style.css
  - scripts/generate_diagram.py
  - scripts/test_diagram.py
  - README.md
forbidden:
  - src/**
  - shapes/**
  - viz/src/data.js
risk: normal
acceptance:
  - claim: >-
      At rest the map draws only rdfs:subClassOf, laid out so that no more than a
      pinned number of those edges cross. Relations appear for the selected
      class and the active lens.
    witness: >-
      make diagram-check, computing positions in the generator as it does the
      outline's rows, with a negative test that reverses one family's order
  - claim: >-
      Depth reads off the page: every class sits on the row for its depth from
      BFO's entity, the same depth the outline and the panel give.
    witness: make diagram-check (every node's y equals its outline depth times the row height)
  - claim: >-
      The layout is deterministic, so two builds of one ontology draw the same map.
    witness: make diagram-check (building twice yields identical positions)
---

## Context

The map is a force layout of 113 classes and 147 edges, and it reads as a hairball.
*The Ontology Pipeline* gives no layout algorithm, but four of its principles apply:

- keep the layers apart; don't collapse the taxonomy and the ontology into one picture;
- draw hierarchy as a tree ("consistent depth across branches becomes immediately
  obvious in a tree diagram");
- let competency questions scope what is shown;
- start from top-level categories.

Measured on 0.20.0:
- 102 of the 147 edges (70%) are `rdfs:subClassOf`;
- only 45 are relations, and 11 of those cross modules;
- the biggest hub is `fm:InformationContentEntity`, with 20 edges.

A force layout weighs all 147 edges as equal springs, so the hierarchy pulls
everything into the middle and hides the relations.

## Prototype

The branch is `joel/proto-banded-layout`. Open
`viz/prototype-layouts.html?variant=A|B|C|D` after `make diagram`, and use ← → to switch.
Each variant reports its edge crossings at rest:

| Variant | Layout | Edges at rest | Crossings |
|---|---|---|---|
| A | force (today) | 145 | **593** |
| B | banded: x = side column, y = depth | 102 | **419** |
| C | radial is-a tree | 102 | **16** |
| D | top-down is-a tree, rows = depth, each family ordered wx, fm, ksh | 102 | **20** |

The prototype's finding is that **side and hierarchy don't line up in this
ontology**. `fm:InformationContentEntity` and the BFO qualities and processes each have
subclasses on all three sides. Pinning each side to a column (B) drags every
such family across the map. So side can be a local order within a family, as in C
and D, but it can't be a global axis.

B, C and D hide relations until a class is selected or a lens is on. In D,
`ksh:Market` selected shows 9 relations, and the CQ2 lens shows 2.

## Problem

Choose a layout, and make its quality checkable rather than judged once by eye. D is
the likely pick: its rows are the outline's depths, and families read left to
right as forecast, pivot, market. Its costs are a wide, flat aspect and labels that
need zoom. C is more compact but loses the depth-as-rows reading.

Open for the verdict:
- whether BFO's intermediate classes should become nodes, so the top rows
  aren't nearly empty;
- whether to wrap wide families;
- whether dragging stays.

## Out of scope

- Drawing OWL restrictions.
- Edge bundling for the relations. They only appear on demand, so there are
  few of them at once.

## Notes for the agent

- Compute positions in `generate_diagram.py`, as `outline()` already computes rows.
  The check can then count crossings and pin the ceiling. `layout.js` would read the
  positions instead of simulating them. That keeps the page thin and the picture
  testable.
- Keep the prototype's crossing counter as the metric: segment intersection over
  the edges drawn at rest, where edges sharing an endpoint don't count.
- The prototype files are throwaway. Rewrite the chosen variant properly; don't
  promote `prototype-layouts.js`.

## Comments

- 2026-09-26: Verdict: **D**, the top-down is-a tree. The prototype stays on the
  throwaway branch `joel/proto-banded-layout` (variants A–D, crossing counts 593 /
  419 / 16 / 20). Defaults taken on the open questions:
  - BFO's intermediate classes are now map nodes. The tree has one root, and
    crossings fell to 3.
  - Wide families don't wrap. Deferred.
  - Dragging moves a class along its row only.

  Built on `joel/map-tree-layout`, stacked on FM-0020. `place()` computes positions
  in the generator, and `diagram-check` requires every class on its depth's row,
  crossings ≤ 3, and identical positions from two runs. `test_diagram.py` moves a
  class off its row and reverses a row to prove both fail. Labels are counter-scaled
  so they read at 11px at any zoom, which is why the fitted tree is labelled at all.

  All three acceptance witnesses pass under `make test`. Resolved.
