# Classify unexercised classes rather than counting them

36 of 98 minted classes have no instance in `examples/` even through their subclass
closure, and `validate.py` reports that as an advisory figure nothing enforces. We
decided to classify every unexercised class in `queries/class-coverage-expectations.json`
under one of four reasons and fail the build on a class in none of them, rather than
pinning a floor on the count.

The reason is that the 36 are not one population. Nine have schema individuals and no
example file can ever reach them. Nine more are quality classes that a forecast example
must not instantiate, because "propositions, not aboutness" refuses to assert a quality
instance standing in for a future fact — `wx:AirTemperature`'s scope note says so
outright. Only a residue is a genuine gap. A single number over those four situations
cannot move for reasons that have nothing to do with whether the ontology is improving.

## Considered options

**Floor the count** — pin 43 (direct) or 62 (closure) and fail on regression. Rejected:
the direct-versus-closure choice is undecidable without knowing what the number is made
of, and `queries/axiom-expectations.json` exists because a ledger asserting an unverified
relationship is the original bug wearing the ledger's clothes. Pinning an
uncharacterised figure repeats that.

**Delete what is unexercised** — prune the classes that do not earn their place.
Rejected: it would delete `wx:AirTemperature`, `wx:DewPoint` and their siblings, whose
absence from the examples is the ontology's central design decision working correctly,
not neglect.

**Leave the advisory counts alone.** Rejected: nothing stops a newly minted class
joining the unexercised set silently, which is the only failure mode worth catching.

## Consequences

No number is pinned anywhere. Regression protection falls out as a side effect: a new
class that no example reaches fails the build until someone files it with a reason.

The ledger is required to shrink. A classified class that later becomes exercised fails
as a stale entry, so writing example data forces the file down rather than leaving
entries to rot — the same guard `check_axioms.py` runs against its own ledger.

The four reasons are not equally verifiable, and the asymmetry is deliberate.
`schema-instantiated` is derived at runtime and never written by hand. `unassertable`
is pinned to the `skos:scopeNote` that states the prohibition, which catches a reword
silently evaporating the justification. `unlisted` rests on an external fact about what
Kalshi lists and can only carry a check date. `unwritten` rests on the stale guard alone,
which is the right amount for a claim that says only "nobody has done this yet".

The cost is 27 hand-written reasons, and they are the work — the check itself is set
arithmetic over two graphs.
