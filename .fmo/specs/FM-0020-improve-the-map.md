---
id: FM-0020
title: The map reads as it claims to, in colour, by keyboard, and as a check on the ontology
type: feature
priority: 3
depends_on: []
touches:
  - viz/style.css
  - viz/index.html
  - viz/src/graph.js
  - viz/src/ui.js
  - viz/src/layout.js
  - viz/src/main.js
  - scripts/generate_diagram.py
  - Makefile
  - README.md
  - CONTEXT.md
forbidden:
  - src/**
  - shapes/**
  - queries/*.expected
  - viz/src/data.js
risk: normal
acceptance:
  - claim: >-
      Every colour token used as text clears 4.5:1 against the surface it sits
      on, and every token used as a mark clears 3:1, in both themes.
    witness: make diagram-negative (muted text back in the pre-audit grey)
  - claim: >-
      The module palette passes the dataviz validator's all-pairs CVD check at
      the 6 floor in both themes, the pivot's deliberate lack of chroma aside.
    witness: make diagram-negative (dark grey inseparable from red under CVD)
  - claim: >-
      No text is filled with a module colour except the Turtle stanza's
      prefixes; relation labels wear text tokens.
    witness: make diagram-negative (text set in a module colour outside the stanza)
  - claim: >-
      Every node takes the pointer within 12 screen pixels of its centre at
      every zoom, and the nearest node wins where targets overlap.
    witness: make diagram-negative (a hit reach shrunk to the dot)
  - claim: >-
      Every term on the map is reachable and selectable by keyboard alone, through
      an outline view that lists each minted class under its parent with its depth.
    witness: make diagram-negative (a class missing from the outline)
  - claim: >-
      Search finds object and datatype properties, and a retired term resolves
      to the term that replaced it.
    witness: make diagram-negative (a tombstone whose replacement is not on the map)
  - claim: >-
      The panel shows skos:changeNote and skos:historyNote where a term has one.
    witness: make diagram-negative (a change note dropped on the way to the panel)
  - claim: >-
      Every lens (the export profile, competency questions, class coverage) is
      one mechanism, and each fails diagram-check when it lights nothing.
    witness: make diagram-check, with a negative test per lens
---

## Context

Two passes over `viz/` on 2026-09-26. The first read Talisman's *The Ontology
Pipeline* for what a visualization is for. The second audited the map with the
`dataviz` skill and ran its palette validator against the CSS tokens.

The book asks a visualization to do two things the map half does:

- **Communicate.** "The visualization serves as an organizational language and
  communication interface." The pivot colouring and the declared Turtle already
  do this well.
- **Expose structure.** "Visualization helps identify structural problems, such
  as orphaned concepts, unbalanced hierarchies, and missing relationships…
  Consistent depth across branches… becomes immediately obvious in a tree
  diagram." The map doesn't do this. A force layout hides depth.

It also names two things the map doesn't show. Terms trace back to competency
questions ("every term… traces back to at least one competency question"), and
"a disjointness axiom is invisible to most users".

## Problem

### Measured (validator output, 2026-09-26)

| Token pair | Light | Dark | Rule |
|---|---|---|---|
| `--graphite` as text on `--paper` | **2.78:1** | 4.18:1 | text ≥ 4.5 |
| `--graphite` ↔ `--warm`, protan | 16.2 | **5.8** | CVD floor ≥ 6 |
| `--cold`, `--warm` OKLCH L | in band | **0.716, 0.694** | dark band ≤ 0.67 |
| `--ink` (the pivot) chroma | **0.011** | **0.008** | ≥ 0.10 to read as a hue |

- `--graphite` is used as text all over the chrome: field headings, the CURIE,
  legend descriptors, the block note, the placeholder. At 10–12px it fails
  WCAG in light mode.
- The pivot in ink is a deliberate choice (CONTEXT.md §5). It fails the
  chroma floor by design, and it passes separation (ΔE 26.8 against `--cold`).
  Keep it, and say so in `style.css`. What matters is that `fm` and `bfo` are
  told apart by fill (solid vs hollow dashed ring) as well as by lightness, and
  that stays true.

### Encoding

- **Relation labels are filled with their domain's module colour**
  (`graph.js`, `e.lab` gets `fill: color(e.a)`). Text wears text tokens;
  identity comes from the coloured stroke beside it.
- **The export profile marker reuses `--warm`** (`.prof`, `.lits li.in-prof`).
  On a map where warm means `ksh:`, it reads as "market side".
- **The legend keys only the modules.** Nothing says a hairline is
  `rdfs:subClassOf`, a coloured curve is a relation coloured by its domain, or
  a dashed ring is borrowed ground.
- **The legend is `display: none` below 900px**, so on a phone colour is the
  only identity channel.

### Interaction

- Node hit targets are only the painted circle: r 4.6 at the smallest, about
  9px across. The minimum is 24px.
- The SVG is `role="img"`, so the only keyboard path is search, which finds
  classes only. There is no table view. The book's tree view and the dataviz
  table-view rule ask for the same thing: an **outline** listing each minted
  class under its parent, with its depth. The outline is the keyboard path
  *and* the view that shows depth.

### Content the book points at

- The panel drops `skos:changeNote` and `skos:historyNote`. `build()` reads
  only the definition, the scope note and the example. ADR 0003 requires the
  change note, so the one field that says why a term moved is written and
  never shown.
- Search can't find a property, so it can't find a tombstone either. All six
  in `src/kalshi.ttl` are properties (`ksh:yesBidCents` and others). The book's
  hidden-label pattern: a retired name still resolves, to its
  `dcterms:isReplacedBy`.
- Disjointness (7 declaring lines across core, weather and kalshi) appears nowhere on
  the map.
- No view answers "which competency question needs this term", or "which
  classes does no example instantiate".

## Plan

Build in this order. Each step lands on its own, and 1–2 are small.

1. **Legibility.** Move every text use of `--graphite` to `--ink-soft`
   (6.1:1), keeping graphite for `bfo` marks only. Re-step dark `--cold` and
   `--warm` into the band, and re-step dark `--graphite` until protan ΔE
   against `--warm` is ≥ 6. Relation labels → `--ink-soft`. Give the profile
   marker a non-module encoding (an ink rule plus the word, not a hue). Add
   edge and ring rows to the legend. Keep the legend visible on narrow screens,
   collapsed to a toggle.
   Witness: `diagram-check` computes WCAG contrast and OKLab CVD distance off
   the tokens in `style.css`. The maths is about 40 lines of Python (port the
   Machado 2009 matrices from the dataviz `validate_palette.py`), plus a
   negative test that lowers a token.
2. **Panel and search.** Extract the change and history notes. Index object
   properties, datatype properties and tombstones. A tombstone hit selects its
   replacement and shows "retired in … — replaced by …".
3. **Hit targets.** A transparent circle, r ≥ 12, under every dot. It carries
   `data-id`, and the visible dot stops taking pointer events.
4. **Outline view.** A `Map | Outline` toggle in the bar. The outline is an
   indented tree rooted at `bfo:entity`, with columns for module, depth,
   relation count and literal count. Rows are buttons that call the same
   `select()`, so the panel is shared. A class with more than one parent
   appears under each, marked. This is the table twin and the depth view at
   once.
5. **Generalise the profile into lenses.** Today's `profileOnly` flag and
   `profile`/`reached` fields become one mechanism: a lens names classes and
   paths, and the edges it walks light their ends. Do this *before* the second
   lens, not after the third. The same reasoning made `scripts/ledger.py`
   exist.
6. **CQ lens.** `generate_diagram.py` reads the terms each `queries/cq*.rq`
   mentions. Choosing a CQ lights them, and the panel lists "used by CQ2,
   CQ5". Minted terms no CQ touches are listed in the legend note. They are
   not errors (`class-coverage-expectations.json` classifies classes, not
   CQs), just visible.
7. **Coverage lens.** Lights the classes an `examples/` file instantiates.
   Unexercised classes show their ledger category and reason from
   `queries/class-coverage-expectations.json`.
8. **Structure.** Show depth in the panel, and add a "Disjoint with" field. A
   legend note counts classes joined to the rest only by `rdfs:subClassOf`,
   which are this map's orphans.

## Out of scope

- Changing the three-way colour split, or giving the pivot a hue. The split
  is the ontology's claim (CONTEXT.md §5), and the audit found it separable.
- Drawing OWL restrictions as edges. The generator's argument still holds for
  restrictions; disjointness goes in the panel, not on the canvas.
- Instance data on the canvas. The coverage lens colours classes; it doesn't
  draw individuals.
- A layout engine other than the current force layout. The outline carries
  the hierarchy, so the map doesn't have to become a tree.

## Notes for the agent

- New vocabulary: **lens** (a named subset of the map that lights, while
  everything else dims), and **outline** (the tree view of the map). Both need
  `CONTEXT.md` entries next to **The map**, with "filter" on the lens's
  _Avoid_ list: a module chip hides, a lens dims, and the difference matters.
- Every lens and the outline are traversals. Each gets a `diagram-check`
  assertion that fails when it is empty, and a negative test. That is the
  repo's `coverage()` rule, applied to the map.
- The built file must stay self-contained. No palette library at runtime; the
  CVD maths lives in the checker, not the page.
- Render both themes and look at them before claiming step 1 is done. The
  validator checks colour, not label collisions.
- A reader who only has the built file (emailed, double-clicked) should get
  all of this. Nothing may depend on `viz/index.html`'s dev-only webfonts.

## Comments

- 2026-09-26: Step 1 (legibility) landed on `joel/map-legibility`. `scripts/palette.py`
  audits the tokens inside `diagram-check`, and `make diagram-negative` has 12 cases.
  The audit also found the two dark blocks already disagreeing on `--shadow`
  (whitespace only). Steps 2–8 are still open.

- 2026-09-26: Step 2 (panel and search) on `joel/map-panel-search`, stacked on step 1.
  Properties get their own panel. The notes claim covers the terms the map shows,
  meaning classes and properties: `wx:TotalSnowfall`'s change note is on an
  individual, and individuals are not drawn. Found while doing it: `stanzas()` kept only
  a term's last Turtle block, so every property FM-0015 gave a field name showed just
  its `skos:notation` line. Blocks are joined now, and `diagram-check` requires every
  stanza to contain its declaration.

- 2026-09-26: Step 3 (hit targets) on `joel/map-hit-targets`, stacked on step 2. Hit
  testing is nearest-node in screen space rather than a larger transparent circle:
  circles big enough at low zoom overlap in the core, where the one drawn last would
  win. Checked headless at zoom 1.39 and 0.4: 10px from a dot's centre selects it,
  and 16px from an isolated dot selects nothing. `diagram-check` pins HIT_PX ≥ 12.

- 2026-09-26: Step 4 (outline) on `joel/map-outline`, stacked on step 3. The rows
  are computed in `generate_diagram.outline()`, not in the page, so `diagram-check`
  can test them. It walks BFO's own hierarchy too: the map draws only edges starting
  at a minted class, which left 12 BFO roots and no depth to speak of. Depth ranges
  today are fm 3–5, wx 3–6, ksh 3–7. A data key named `outline` was silently
  overwritten by the module of the same name on `window.FMO`, so `diagram-check`
  now refuses a data key named like a viz module.

- 2026-09-26: Step 5 (lenses) on `joel/map-lenses`, stacked on step 4. The export
  profile is now `data.lenses[0]`, built by `lens()`, and the per-node and per-edge
  `profile`/`reached` flags are gone. The chip became a picker. Checked headless: the
  same 7 classes light, with the same legend and panel wording as before. One change
  in behaviour: the marker on a class's literal list now follows the active lens.
  Before, it always showed the export profile.

- 2026-09-26: Step 6 (question lenses) on `joel/map-cq-lens`, stacked on step 5. There
  is one lens per `queries/cq*.rq`, with terms read from the parsed algebra, plus a
  **No question** lens. 68 of 100 minted classes are untouched by any question. That
  is a finding for whoever owns the CQ set, not something this spec should fix.
  `diagram-check` refuses a query matching on a retired or undeclared term. The lens
  picker and the view toggle made the bar overflow below 1336px, so the bar now sheds
  its subtitle, then search width and the "Lens" label. It fits from 1440 down to 901.

- 2026-09-26: Step 7 (coverage lens) on `joel/map-coverage-lens`, stacked on step 6.
  `check_class_coverage`'s exercised/reached computation moved into
  `validate.exercise()`, which the map now shares. Today: 43 classes direct, 19 via a
  subclass, 9 enumerated in src/, and 29 in the ledger (2 unassertable, 6 unlisted,
  21 unwritten). A lens's prose field is now `about` rather than `question`, since
  not every lens asks one.
