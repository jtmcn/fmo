# Pin the export contract in FMO, and fail on any verdict

`scripts/shape_signatures.py` classifies a change to `shapes/thermaledge-export.ttl`
as WEAKENED or CHANGED against a pinned baseline, over 18 named rules, exercised by
22 mutants in `scripts/test_shape_drift.py`. Until now nothing pointed it at the
file. `--compare` requires a baseline path, no baseline lived here, and no target
passed one. We decided FMO holds its own pin in `shapes/thermaledge-export.pin.json`,
audited by `make shape-signatures`, and that the audit fails on **any** verdict.

The classifier was not untested; it was undeployed. Its only caller was its own
suite. Widening `fm:probabilityValue` from `0..1` to `-99..99` — the range guarding
the 7.41 bug that is the reason `teh:MarketShape`'s target narrowing is a named rule
— passed `validate`, `shapes`, `shapes-negative`, `shape-signatures`, `export-check`
and `cq`. Six green targets over a weakened export contract.

Any verdict rather than only a weakening, because that widening classifies as
`value-changed` → CHANGED. Full SHACL subsumption is undecidable, so the rules name
the weakenings that actually happen and report everything else as CHANGED, meaning
"a human decides". A loosened numeric range and a widened `sh:in` are genuine
weakenings living in that bucket. README already argued a consumer's policy should
be to fail on any verdict; FMO adopting it for its own pin is the same argument, not
a new one. The cost is that adding a shape (`shape-added`, also CHANGED) fails the
build until someone re-pins, which is the `cq-update` discipline: a reviewed diff.

## Considered options

**Leave ownership with the consumer.** README's position, and it is right about
*policy* — what a verdict is worth is the caller's decision, which is why
`--compare` still exits 0 whenever it produced a report and is left untouched by
this change. But it silently assumed someone runs `--compare`. Nobody in this repo
did, and FMO is the party that edits the shapes file. Rejected: it makes FMO's own
`make test` structurally unable to see FMO's own regression, and defers detection to
a downstream nightly run that may never be pointed at the right revision.

**Catch it structurally instead, with no baseline** — extend `test_shapes.py`'s
mutant sweep so a dropped `sh:minCount` or a `sh:deactivated` fails without a pin.
Rejected: a mutant sweep proves a constraint bites, never that it bites as hard as
it did yesterday. It cannot see a *widened* range at all, which is the motivating
case. That is precisely the gap `compare()` was written to fill.

**Change `--compare` to exit non-zero.** Smallest diff. Rejected: `--compare`'s
exit-0 is a published contract (README), written for external callers. Breaking a
published interface to serve an internal need is the wrong trade when `--audit`
costs one CLI branch.

**Build a `ShapeContract` code module** (`sign` / `pin` / `audit`). Rejected for
now: one adapter is a hypothetical seam. When a second consumer's pin needs auditing
here, promote it.

**Give `scripts/term_signatures.py` the same treatment.** It has the same shape one
level over — digests, `--check`, no pin in-repo — but no classifier at all, so this
would be a build rather than a wiring. It must wait on a prior fix:
`semantics_sha256` derives a term's subject by splitting the axiom key on `": "` and
then on `" "`, which yields `AllDisjointClasses(fm:TruthValue,` for the listing
forms. Ten of 68 axiom sites land in buckets no curie can match, including both
`owl:AllDisjointClasses` blocks and the `owl:AllDifferent` block over units that
makes `wx:conventionalUnit`-as-subproperty a HermiT inconsistency. A classifier
built on that fact set would sign an incomplete one and report a guarantee it is not
holding — the failure `term_signatures.py`'s own docstring exists to name.

## Consequences

The pin is generated. `make shape-signatures-update` writes it and refuses when the
signatures are not reproducible, because pinning a signature that churns pins noise
and the next run then fails for a reason nobody can act on. It carries a `_comment`
header, the JSON-comment idiom `queries/production-expectations.json` and
`queries/class-coverage-expectations.json` already use; `load_pin` strips
underscore keys the way `run_competency.py` does, so the classifier's input stays a
map of shape name to facts.

The pin is not a **ledger**. A ledger records why something is *not* proved the
usual way; this proves something directly, and `CONTEXT.md` §4 now carries the word
and the distinction between FMO's pin and a consumer's.

`subclass_map()` gained the zero-guard every traversal in `validate.py` has. It was
the only one without. An empty hierarchy does not fail on its own — membership
doubles as "is this class declared", so every `target-changed` silently becomes
`target-undeclared` WEAKENED. Harmless while only tests called it; a wrong reason on
a real failure now that an audit runs in `make test`.

`EXPECTED_ASSERTIONS = 14` in `scripts/test_shapes.py` is deliberately untouched.
The audit subsumes one of its three populations (the minCount mutants) and not the
other two (vacuity checks, dead `sh:class` checks), so deleting it would lose
coverage. Its real defect is separate: it pins one integer over three cartesian
products and its failure message reads as an instruction to bump it, which is the
argument ADR-0001 makes against pinning an uncharacterised figure.
