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
make typecheck          # static types over scripts/, via ty (pinned exactly)
make typecheck-negative # negative tests: prove ty fails, and refuses to check nothing
make validate           # structure, BFO grounding, disjointness, units, docs (no Java)
make validate-negative  # negative tests: prove the validator fails when it should
make shapes             # SHACL conformance: examples union, then each export fixture
make shapes-negative    # tests about the shapes: vacuity, mutants, dead constraints
make export-check       # production CQ mode: exports pass, the mismatch fixture fails on CQ2
make shape-signatures   # sign the export shapes, audit them against FMO's pin
make shape-signatures-update  # re-pin after an intended shapes change; review the diff
make cq                 # SPARQL competency questions vs checked-in .expected
make cq-update          # regenerate .expected — review the diff before committing
make reason             # HermiT consistency (needs a working JDK; fails, not skips, without one)
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
- **Editing `shapes/thermaledge-export.ttl` means re-pinning.** `make shape-signatures`
  audits it against `shapes/thermaledge-export.pin.json` and fails on *any* verdict,
  weakened or merely changed — a widened numeric range is the second kind and is the
  hole the pin was added for. Run `make shape-signatures-update` and review the diff;
  the pin is generated, never hand-edited — the audit enforces that, refusing a
  body whose stored digest disagrees with its own facts and a `_comment` that has
  drifted from `PIN_COMMENT`. See `docs/adr/0002-pin-the-export-contract.md`.
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
  traversed nothing proved nothing, so `coverage()` fails on a zero count — when
  there is example data to traverse. A check whose population is the schema passes
  `always=True`, because no example file can empty it and gating its guard on
  `EXAMPLES` makes it depend on something the check never reads.
  One call per *check* is not enough: an aggregate counter over several traversals
  stays non-zero when one of them empties, which is the original lead-time bug
  wearing a guard. `scripts/test_meta.py` (`make meta`) enforces both by running
  every *registered* check against something that empties its traversal: the schema
  with no example data for a `data` check, an empty graph and no `EXAMPLES` for a
  `schema` one — which is what proves its `always=True` — and an example file
  holding nothing for an `example-files` check that re-reads `examples/` off disk.
  Which of the three a check needs is `population=` on its `@check` decorator, and
  the schema-reading claim is then run rather than read: a data-dependent check
  misfiled there empties trivially and would otherwise pass vacuously.
  There is a fourth value, `unsweepable`, and it is an opt-out from this rule
  rather than a fourth way of applying it: the sweep prints `exempt` and never
  calls the check. Only `check_context_terms` uses it, because it reads neither
  graph it is handed. Nothing verifies an `unsweepable` reason, so a new one is
  the thing to argue about in review — it is the one way to register a check that
  `make meta` will not run.
- **Every check registers itself with `@check(takes=…, population=…)`.** `takes`
  names the graphs `main()` hands it; `population` names what has to go away for its
  traversal to empty. The two correlate and do not coincide, so both are declared.
  Dispatch is derived from the registry, never retyped: `main()` once held two
  hand-written tuples and four loose `run_check` calls while `make meta` swept
  `dir(V)`, and a well-formed check that `main()` never called passed both.
  `test_meta.py` now runs `validate.CHECKS` and fails on a `check_*` that is not
  registered.
  `coverage(always=)` is *not* derived from `population`, though today it could
  be: `always=True` holds for exactly the `schema` and `unsweepable` checks, and
  is uniform within every one of them. The reason is that the two facts are not
  the same shape. `population` is one fact per check; `always=` is an argument to
  a *call*, and a check's `coverage()` calls are not in correspondence with its
  traversals — `check_class_coverage` has five loops and six comprehensions
  behind a single guarded `coverage()`, deliberately leaving the rest unguarded
  because an empty ledger is its goal state. A registration carries no per-call
  fact to derive from, so deriving `always=` would mean inventing one — and a
  check taking both graphs could want `always=True` on its schema traversal and
  `always=False` on its data one, which a derived value makes unrepresentable.
  Restating the fact is safe here because `make meta` enforces the correlation by
  *running* it, not by reading it: a `population="schema"` check is swept against
  an empty graph with `EXAMPLES` cleared, so an `always=False` on one of its calls
  gates the guard on example data that is not there — the check passes, and the
  sweep fails it by name. Flipping `check_bfo_grounding` confirms it. The reverse
  direction is a stricter guard, not a weaker one, so nothing hides there. Same
  "run rather than trusted" mechanism the schema claim itself rests on: this
  duplication is checked, not merely correlated.
  Only a registered function is dispatched or swept, so `main()` parses and
  dispatches and holds no check of its own — six once did, and none of the six
  guarded a zero count. What is left inline is advisory and can never fail: the
  minted-class count. The instantiation figures moved into `check_class_coverage`,
  which already traverses what they report — two computations of one fact drift,
  and the check is where the traversal is guarded.
- **Every unexercised class is classified.** A minted class no example instantiates,
  directly or through a subclass, must appear in
  `queries/class-coverage-expectations.json` under `unassertable`, `unlisted` or
  `unwritten`, with a reason. The fourth case, a class whose own individuals are
  declared in `src/`, is derived at run time and never written in the file. No count
  is pinned: the four situations are different populations, and a floor over the lot
  cannot move for reasons that have nothing to do with the model improving. See
  `docs/adr/0001-classify-unexercised-classes.md`.
- **Every checked-in ledger goes through `scripts/ledger.py`.** A ledger records,
  per item, why something is not proved the usual way; three exist, and each grew
  its own copy of the same set arithmetic. The copies drifted —
  `production-expectations.json` checked that every query had an entry and never
  that every entry had a query, so a stale exemption read as a decision about
  today's query set. `CONTEXT.md` §4 had stated the rule for all three, and the
  third checker was written without it, which is the argument for a module over a
  paragraph. A new ledger calls `ledger.audit()`, names in `handles=` every
  finding kind it has decided about — rendering one is a decision, and so is
  deliberately ignoring it — and passes its category keys to `ledger.load()` so a
  key nothing reads is refused. Both refusals raise rather than pass quietly,
  because the failure they replace was a finding computed and dropped. What the
  kernel does *not* own is the file's shape, its wording, or its per-entry
  verification; see `scripts/ledger.py`'s docstring for why each stays at the call
  site.
- **Units: identical where values are compared, dimension-equal where a unit is merely
  chosen.** Dimension equality is never sufficient — °F vs °C shares a dimension vector.
  `wx:conventionalUnit` is deliberately *not* a sub-property of the functional
  `fm:hasUnit`; the `owl:AllDifferent` block in `core.ttl` makes that mistake a HermiT
  inconsistency rather than a wrong answer.

## Agent skills

### Issue tracker

Issues live in GitHub Issues on `jtmcn/fmo`, via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical triage roles, using their default label strings. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.
