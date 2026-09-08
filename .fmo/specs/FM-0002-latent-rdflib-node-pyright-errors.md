---
id: FM-0002
title: 36 latent rdflib-Node pyright errors revealed by pyright venv resolution
type: chore
priority: 3
depends_on: []
touches:
  - scripts/validate.py
  - scripts/test_shapes.py
  - scripts/shape_signatures.py
  - scripts/axioms.py
  - scripts/extract_qudt_subset.py
forbidden:
  - src/**
  - examples/**
  - queries/**
risk: low
acceptance:
  - claim: >-
      `npx pyright scripts/` reports 0 errors. The 36 reportArgumentType errors
      (plus one reportAssignmentType) are gone, not suppressed wholesale.
    witness: npx --no-install pyright scripts/
  - claim: >-
      No blanket suppression. Any `# type: ignore` is line-scoped and carries a
      justification comment referencing this spec.
    witness: scripts/validate.py
  - claim: >-
      The suite is unaffected: validate.py still ends OK, and test_shapes,
      test_validate, test_shape_drift, test_meta and test_reason all still pass.
    witness: make test
---

Migrated from GitHub issue #22 (labelled `enhancement`).

## Context

The branch for the LSP-diagnostics remediation plan (`lsp-diagnostics`, plan
`docs/superpowers/plans/2026-08-26-lsp-diagnostics.md`) addressed all **95**
pyright/ast-grep/typos findings it enumerated. But enabling `pyrightconfig.json`
— which makes pyright resolve the poetry venv — **revealed 36 pre-existing
latent pyright type errors** that were previously invisible: rdflib's types only
failed type-check once rdflib actually resolved.

These 36 are pre-existing. None was introduced by the remediation branch; every
flagged line is outside every task's diff, and they were classified out of that
plan's literal scope.

## Problem

rdflib's `Graph.objects()` / `subjects()` / `items()` / `value()` return generic
node types (`_ObjectType` / `_SubjectType` / `Node`). Pyright will not accept
those where the calling code annotates a narrower type (`URIRef`, `BNode`,
`Node`, `int`, `float`). The result is ~36 `reportArgumentType` errors plus one
`reportAssignmentType`.

This is a type-annotation gap, not a runtime bug: the RDF graphs are well-formed
and the validator suite passes. It is latent type-unsafety.

| File | Count |
|------|-------|
| `scripts/validate.py` | 20 |
| `scripts/test_shapes.py` | 12 |
| `scripts/shape_signatures.py` | 2 |
| `scripts/axioms.py` | 1 |
| `scripts/extract_qudt_subset.py` | 1 |

Reproduce with `npx --no-install pyright scripts/` (venv present or symlinked).
Representative triggers:

- `validate.py:492,580,581,729,730,909,910,964` — `int(node)` / `float(node)`
  where `node` is `_ObjectType`, not assignable to a `ConvertibleToFloat` param.
- `validate.py:189,617,1212,1340` — `ancestors(g, node)` where `node:
  _ObjectType` but the param is annotated `URIRef`.
- `validate.py:642` — `sources = {s for h in holders for s in g.objects(h, ...)}`
  returns `set[_ObjectType]`, not assignable to the declared `set[URIRef]`.
- `shape_signatures.py:121` — `int(value)` / `curie(value)` where `value:
  _ObjectType`; `:243` — `prop` is not `BNode`.
- `test_shapes.py:127,195,198` — shacl `str_conforms` returns
  `ValidationFailure` etc.; `.value` / `.subjects` attribute access.

## Out of scope

Anything under `src/`, `examples/` or `queries/`. This is a typing change to
`scripts/` and must not move the graph.

## Notes for the agent

Three approaches; pick one and document the choice:

1. **Narrow helper signatures + runtime assertions**: widen `ancestors`,
   `_constraints`, `curie`, `ranges_of`, `subclasses_of` params to accept `Node`
   and re-annotate call sites, or add `assert isinstance(x, URIRef)` at the seams
   so pyright narrows.
2. **Line-scoped type ignores**: `# type: ignore[reportArgumentType]` narrowly
   where the annotation is known-correct for this ontology (all RDF terms here
   are named IRIs; the `_ObjectType` reality is a stub limitation).
3. **Central narrowing util**: a small `as_uriref(node) -> URIRef` used at
   boundary points.

Constraint carried from the original plan: no broad `# type: ignore` files, no
`typing.cast` everywhere. Prefer honest narrowing at the seam.

Note that `make typecheck` runs `ty`, not pyright, and is pinned exactly. This
spec is about pyright's view; keep both green.

## Comments
