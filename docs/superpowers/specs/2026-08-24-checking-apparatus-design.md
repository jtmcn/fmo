# Hardening the checking apparatus

Design for a three-PR stack. Written 2026-08-24, against `main` at `bbd56bc`.

## Why

Two rounds of code review on PR #10 produced about twenty findings. **None was in
the ontology. Every one was in the apparatus that checks it.** Sorted by root
cause:

| Class | Count | Instances |
|---|---|---|
| Checks that cannot fail | 6 | `\|\| true` in `export-check`; two `sh:targetClass` on a subclass; two dead `sh:class` under rdfs range entailment; `check_lead_times` zero-coverage |
| Metrics that lie | 3 | coverage conflating an abstract parent with an unusable class; `total_mentioned` reporting 150 where 93 exist; cq06's all-null row counted as data |
| Registration drift | 4 | `rex:` added to one prefix map and not the other; `MODULES` copied; the prose guard reading one file; `examples/negative/` globbed nowhere |
| Crash instead of fail | 3 | `KeyError` mid-run; two `IndexError`s on a flag with no value |
| Stale prose | 4 | "eighteen classes", "three negative tests", two comments citing each other |

The apparatus is 3,518 lines checking a 2,557-triple ontology. It is larger than
the thing it checks and is now the part most likely to be wrong.

The first class is the one that matters. A check that cannot fail is worse than no
check, because it reports success. Six of them shipped, and each was caught by a
human building an adversarial fixture — never by the suite.

**The through-line: the discipline exists as prose in `CLAUDE.md` and as
hand-written cases, so it is applied wherever someone remembered.** `validate.py`
has six hand-written "traverses nothing" guards; the seventh, for lead times, is
missing, and nothing noticed. This work converts that discipline into mechanism.

---

## PR 1 — `joel/checks-foundation`

Mechanical. No new checks. No behaviour change except where a crash becomes a
failure.

### A registry

New `scripts/registry.py`: `ROOT`, `SRC`, `MODULES`, the namespace map, the
example-prefix map, `PROSE_FILES`, and the example/export/negative globs.
Everything imports from it, `validate.py` included — inverting today's
arrangement, where `generate_diagram.py` and `validate_shapes.py` import a
1,328-line module to borrow a list, and `run_competency.py:36` keeps its own copy
of `MODULES` anyway.

The `rex:` bug is the shape of this class. `validate.py` holds prefix→IRI and
`run_competency.py` holds IRI→prefix: two maps over the same namespaces, updated
independently, and one was missed. The registry holds **one source and derives
both views**, so they cannot disagree again.

Glob resolution also leaves the `Makefile`. `EXPORT_FIXTURES` and
`NEGATIVE_FIXTURES` are wildcards there and conceptually in Python too; the
scripts resolve them from the registry and the `Makefile` calls the scripts.

### Prose stops stating apparatus counts

Not "remove the numbers" — the line matters:

- **Numbers describing the ontology's state stay.** 30 weather classes with no
  direct instance, `43 direct / 62 via subclass / 98`. These are the point, they
  change rarely, and a reader cannot reconstruct them.
- **Numbers counting apparatus artifacts go.** "Seven negative tests", "6 file(s)".
  These change every PR, caused four findings, and are already printed by the run.

### Crashes become failures

Each check call in `validate.py`'s main, and each query in `run_competency.py`,
wrapped so an exception yields `FAIL [<name>]: raised KeyError: 'min_rows'` and the
run continues. Today one malformed expectation aborts everything after it, which is
worse than a failure: it hides every remaining result behind a traceback.

---

## PR 2 — `joel/checks-enforcement`

### `coverage()`

A helper in the registry, called by each check in place of its `notes.append`:

```python
coverage("lead times", checked, "checked against issuance and interval start")
```

It records `(name, count)`, prints the note in today's format, and **fails when the
count is zero while examples exist**. Nine one-line edits, at
`validate.py:389, 460, 493, 562, 600, 657, 778, 910, 963` and the traversal note at
`1295`.

This closes `check_lead_times`, the one data-dependent check that today passes
silently reporting `0 checked`.

### The meta-test

**Changed from the original proposal.** Asserting "every `check_*` has a negative
case" requires annotating all 56 case tuples with the check they target — invasive,
and the annotation rots like any other hand-maintained pairing.

The mechanical form is stronger and nearly free: **call every `check_*` with an
empty graph and assert it fails.** No annotation, nothing to maintain, and it is
exactly the property wanted — a check with nothing to check must not pass. Run as a
probe while writing this spec, it identified `check_lead_times` immediately, and
confirmed the other eight already fail.

A second, weaker lint: every `check_*` name must appear somewhere in
`scripts/test_validate.py`, catching a new check with no test at all. Its docstring
must say plainly that this is a smoke alarm, not a proof — a mention is not a test,
and `check_lead_times` would have passed it.

---

## PR 3 — `joel/shape-mutants`

New `scripts/test_shapes.py`: in-process, building mutant graphs with rdflib and
calling pyshacl directly. No tree copy, no subprocess. Own make target, in
`make test`.

The existing harness in `test_validate.py` copies the whole repo per case (~1.2s ×
76 = 93s). Generating a mutant per shape per superclass through it would push the
suite past several minutes; in-process keeps the whole matrix near a second. The
shell-out harness stays for the hand-written cases, where end-to-end fidelity is
the point.

Three checks:

1. **Vacuity.** Every `sh:targetClass` must match at least one focus node on the
   fixtures. A shape matching nothing conforms, so a dead shape is indistinguishable
   from a clean run.
2. **Supertype mutants.** For each targeted class `C` and each superclass `P` in our
   namespaces, retype the focus nodes `C`→`P` and assert the shape still fires.
   This is both `targetClass` bugs, derived from the class hierarchy instead of from
   someone thinking to write the fixture. A class with no superclass in our
   namespaces yields no mutants rather than a false failure.
3. **A static `sh:class` lint.** Flag any `sh:class C` on a path whose `rdfs:range`
   is already `C` or a subclass of it. Under `inference="rdfs"` such a constraint
   can never fire — range entailment types the object before SHACL looks. Pure graph
   inspection, no mutation. This encodes as a check what is currently a comment.

---

## Done means

- `make test` green at every stage of the stack, each PR standing alone.
- `check_lead_times` fails on zero coverage, with the empty-graph meta-test proving
  all nine do.
- `scripts/registry.py` is the only definition of `MODULES` and of the namespace
  maps; `grep -c 'MODULES = \['` over `scripts/` returns 1.
- Supertype mutants are generated for `teh:MarketShape` and `teh:ProbabilityShape`
  and pass. Reverting either shape's `sh:targetClass` to the subclass it used to
  target (`ksh:WeatherMarket`, `fm:ForecastProbability`) makes them fail. Watched
  failing, not assumed.
- The `sh:class` lint fires on a deliberately re-added dead constraint.
- No apparatus counts remain in `README.md` or `CLAUDE.md`; ontology-state figures
  remain.

## Deferred, with reasons

- **The 93s negative suite.** Each case copies the repo. Real, and it caps how many
  cases anyone will write, but it is a cost problem rather than a correctness one.
  PR 3 avoids adding to it rather than fixing it.
- **cq06's all-null row.** Aggregation over an empty inner result yields one null
  row, which a row count reads as data. Harmless while both entries are
  `may_be_empty`; a `min_rows` of 1 on either would be vacuously satisfied. Wants a
  `HAVING` or a null filter, which is a change to query semantics rather than to the
  apparatus.
- **Per-check negative-case coverage.** The strong form needs case annotation; PR 2
  ships the empty-graph test and an honest smoke alarm instead.
