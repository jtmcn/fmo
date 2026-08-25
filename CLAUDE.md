# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

An OWL ontology (Turtle, hand-authored) relating weather forecasts to Kalshi prediction
markets, grounded in BFO 2020. There is no application code — `scripts/` exists only to
check the ontology. `README.md` has the architecture and the three modelling decisions
that shape everything; `docs/design-notes.md` has the rejected alternatives. Read both
before changing `src/`. `CONTEXT.md` is the controlled vocabulary — which word to use
for what, and which not to; consult it before naming anything in prose or in Turtle.

## Commands

```bash
make setup              # poetry install + fetch robot.jar if missing
make validate           # structure, BFO grounding, disjointness, units, docs (no Java)
make validate-negative  # negative tests: prove the validator fails when it should
make shapes             # SHACL conformance: examples union, then each export fixture
make shapes-negative    # tests about the shapes: vacuity, mutants, dead constraints
make export-check       # production CQ mode: exports pass, the mismatch fixture fails on CQ2
make cq                 # SPARQL competency questions vs checked-in .expected
make cq-update          # regenerate .expected — review the diff before committing
make reason             # HermiT consistency (skips with a notice if ROBOT/Java absent)
make competency         # CQ3: weaken an assertion, confirm the reasoner re-derives it
make meta               # every check must fail when it has nothing to check
make test               # all of the above
```

Everything runs through `poetry run`. No single-test runner: `validate.py` and
`test_validate.py` run all checks; `run_competency.py` runs all queries. To isolate one
competency question, run its `queries/cqNN-*.rq` by hand against the same graph
`run_competency.py` loads.

## Working in the ontology

- **Every minted class and property needs `rdfs:label` and `skos:definition`.** The
  validator fails without them. `skos:scopeNote` carries the "why here, not there"; use
  it for anything a future reader would otherwise re-litigate. Term IRIs are readable
  local names, not opaque IDs.
- **Every minted term must reach `bfo:entity` via `rdfs:subClassOf`.** Bridged external
  classes (QUDT) get grounded in `core.ttl` too — four classes once floated under
  `owl:Thing` and the check exists because of it.
- **Adding a source file means updating the `MODULES` list** in `scripts/registry.py`,
  plus `src/fmo.ttl` and `src/catalog-v001.xml`. Every checker imports `MODULES` from
  there rather than keeping its own copy. A stale copy fails silently — the shapes run
  against a smaller ontology, `sh:class` matches fewer nodes, and fewer matched nodes
  means *conformance*, not an error.
- **Version bumps touch all four modules** — `owl:versionIRI` and `owl:versionInfo` in
  `core.ttl`, `weather.ttl`, `kalshi.ttl`, `fmo.ttl`, plus the status line in
  `README.md`.
- **`src/imports/bfo-core.ttl` is vendored unmodified.** Never edit it.
  `src/imports/qudt-subset.ttl` is generated — edit `scripts/extract_qudt_subset.py` and
  run `make qudt` instead.
- **`examples/verification-synthetic.ttl` is generated** by
  `scripts/generate_verification_data.py` (fixed seed). A diff there means the generator
  changed.

## Checks

- **An empty SPARQL result fails.** A query matching nothing is how a broken competency
  check looks like a passing one. SPARQL here does no subclass reasoning, so queries use
  `a/rdfs:subClassOf*`.
- **New validator check ⇒ new negative test.** `scripts/test_validate.py` injects each
  defect into a throwaway copy and asserts the check fails with the right message. The
  first unit check passed a Celsius/Fahrenheit mismatch silently; only the negative test
  caught it.
- **Every traversal calls `coverage()`, one call per traversal.** A check that
  traversed nothing proved nothing, so `coverage()` fails on a zero count.
  One call per *check* is not enough: an aggregate counter over several traversals
  stays non-zero when one of them empties, which is the original lead-time bug
  wearing a guard. `scripts/test_meta.py` (`make meta`) enforces both by running
  every `check_*` against the schema with no example data. Inline check bodies in
  `main()` are invisible to that sweep — write checks as `check_*` functions.
- **Units: identical where values are compared, dimension-equal where a unit is merely
  chosen.** Dimension equality is never sufficient — °F vs °C shares a dimension vector.
  `wx:conventionalUnit` is deliberately *not* a sub-property of the functional
  `fm:hasUnit`; the `owl:AllDifferent` block in `core.ttl` makes that mistake a HermiT
  inconsistency rather than a wrong answer.
