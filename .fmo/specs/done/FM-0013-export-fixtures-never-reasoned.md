---
id: FM-0013
title: the export fixtures are never reasoned over, and domain inference can mistype export data
type: bug
priority: 2
depends_on: []
touches:
  - Makefile
  - scripts/validate.py
  - scripts/test_validate.py
  - scripts/test_meta.py
  - README.md
forbidden:
  - src/**
  - shapes/thermaledge-export.ttl
  - shapes/thermaledge-export.pin.json
risk: low
claimed_by: claude
acceptance:
  - claim: >-
      make reason runs HermiT over the modules plus each file in
      examples/export/, and fails if any is inconsistent.
    witness: make reason, and the reason-negative case "an exported market also typed as an event grouping" in scripts/test_reason.py
  - claim: >-
      No individual in the examples or the export fixture acquires, through
      rdfs:domain or rdfs:range, a type on the other side of the
      continuant/occurrent split from one of its asserted types.
    witness: a new registered check in scripts/validate.py with a negative test in scripts/test_validate.py
---

## Context

`EXAMPLES := $(wildcard examples/*.ttl)` (`Makefile:13`) is not recursive, so
`$(BUILD)/full.owl` merges the modules with the top-level examples only.
`examples/export/thermaledge-kxhighaus-2026-08-22.ttl`, the one stand-in for
what ThermalEdge actually produces, never reaches HermiT.

The export shapes run with `inference="rdfs"` (`scripts/validate_shapes.py:105`),
so `rdfs:domain` and `rdfs:range` add types before any `sh:targetClass` matches.

## Problem

- A new disjointness axiom (FM-0012 adds some) that made ThermalEdge exports
  inconsistent would pass `make test`.
- A domain or range assigns a type; it never rejects a triple. A misused
  property in production data — `fm:issuedBy` on a process, say — silently
  types that process as an information content entity. SHACL then validates
  it under the wrong shape or none, and nothing reports it. A probe over the
  current examples found no such case across 4,453 domain-bearing uses, so
  this is a guard, not a fix.

## Out of scope

Running the competency queries over the inferred graph. They run over the
asserted graph with `a/rdfs:subClassOf*` on purpose (`docs/design-notes.md`).

## Notes for the agent

- Prefer a separate `$(BUILD)/export.owl` per fixture over folding the export
  into `full.owl`: the export is a different population from the worked
  examples, and one failing should name which.
- The Java-free check can use rdflib's RDFS closure or a hand-rolled one over
  `rdfs:domain`/`rdfs:range` only. It is population `data`; it needs
  `coverage()` and must pass `make meta`.
- Whether the check also runs over the export fixture decides whether it is
  useful in production mode (`make export-check`). It should.

## Comments

**2026-09-25 — resolved.** `make reason` now merges the modules with each
file in `examples/export/` separately and runs HermiT on each, and fails
if the glob matches nothing. The export fixture is consistent. The negative
case lives in `scripts/test_reason.py`, not `test_validate.py`, which moves
the first claim's witness: that file is where the HermiT cases live, and a
case there can name its own inputs (modules plus the export alone). It
cross-types the exported market into `ksh:EventGrouping` using FM-0012's
new axiom.

The Java-free half is `domain_range_crossings`, in `validate.py`:
- `check_domain_range_typing` runs it over the examples. It counts only
  triples absent from the schema; the vocabulary's own individuals once
  counted 41 uses on a graph with no example data and kept the guard lit.
- `validate_shapes.py` calls it over each export before SHACL runs, since
  that is where RDFS inference types export nodes and `validate.py` never
  reads an export.

Three negative tests cover a domain crossing, a range crossing, and a
crossing in the export fixture through `--exports`. The current data has
no crossing across 7,714 uses.
