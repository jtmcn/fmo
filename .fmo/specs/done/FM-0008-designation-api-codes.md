---
id: FM-0008
title: the Kalshi designation individuals carry no machine-readable API code
type: feature
priority: 3
depends_on: []
touches:
  - src/kalshi.ttl
  - src/core.ttl
  - src/weather.ttl
  - src/fmo.ttl
  - shapes/  # a new vocabulary shapes file, beside the export one
  - scripts/registry.py
  - scripts/validate_shapes.py
  - scripts/test_shapes.py
  - scripts/validate.py
  - scripts/test_validate.py
  - scripts/term_signatures.py
  - Makefile
  - CONTEXT.md
  - README.md
forbidden:
  - shapes/thermaledge-export.ttl
  - shapes/thermaledge-export.pin.json
  - src/imports/**
  - examples/**
risk: low
acceptance:
  - claim: >-
      Every individual of ksh:MarketStatus, ksh:ResolutionOutcome,
      ksh:ContractSide and ksh:OrderAction carries exactly one skos:notation,
      typed by the datatype for its API field, except ksh:Voided, which carries
      none.
    witness: make shapes
  - claim: >-
      A coded individual with its notation removed, or with a second one added,
      is rejected.
    witness: make shapes-negative
  - claim: >-
      No two individuals share a notation. "yes" as a result code and "yes" as
      a side code are different literals and do not collide.
    witness: make shapes-negative
  - claim: >-
      The notations are exactly the API's documented enumeration per field: a
      code outside it is rejected, and a documented code no individual carries
      is rejected, except the empty `result`.
    witness: make shapes-negative
  - claim: >-
      Every vocabulary shape has at least one focus node over the modules; none
      conforms by matching nothing.
    witness: make shapes-negative
  - claim: >-
      Each individual excepted from carrying a code has no notation and has a
      skos:scopeNote stating why.
    witness: make shapes-negative
  - claim: >-
      The ontology is still consistent under HermiT with typed notation
      literals in src/, and the JDK job still skips nothing.
    witness: make reason
  - claim: >-
      Changing one individual's notation moves that term's semantics_sha256 and
      no other term's.
    witness: make signatures
  - claim: >-
      Each new datatype carries rdfs:label and skos:definition, and the
      validator fails when either is missing.
    witness: make validate-negative
  - claim: >-
      CONTEXT.md names the new term and the four datatypes, and each resolves
      to a declaration.
    witness: make validate
  - claim: >-
      The ThermalEdge export contract is untouched: its pin still audits clean
      without a re-pin.
    witness: make shape-signatures
  - claim: >-
      The version is bumped to 0.13.0 in all four modules and the README status
      line: additive annotations, no existing term changed.
    witness: README.md
---

Found while reading *The Ontology Pipeline* (Talisman) against FMO, in its SKOS
chapters. See the book's CBox integration section (mnemo `5a791d`, seq 297–302)
and its SKOS integrity conditions (seq 212).

## Context

FMO has nine controlled vocabularies, the subclasses of `fm:Designation`. Each is
a set of typed `owl:NamedIndividual`s with `skos:definition`, kept apart by
`owl:AllDifferent` within a vocabulary and `owl:AllDisjointClasses` across them.
This is the book's second way of bringing a vocabulary concept into an ontology,
as an individual, done in OWL rather than SKOS. The book's Heuristic 3 supports
the choice: SKOS is for classification where dual membership is legitimate, and
here it is the defect (`ksh:ResolvedYes` doubling as `fm:True`). Nothing in this
spec changes that.

Four of the vocabularies mirror a field in the Kalshi trading API:

| Vocabulary | API field | Documented codes |
|---|---|---|
| `ksh:MarketStatus` | `status` | initialized, active, inactive, closed, determined, disputed, amended, finalized |
| `ksh:ResolutionOutcome` | `result` | yes, no, scalar, and empty |
| `ksh:ContractSide` | `side` | yes, no |
| `ksh:OrderAction` | `action` | buy, sell |

The kalshi module's scope note says these "mirror the Kalshi trading API, checked
against the live API and the published reference on 2026-08-17."

## Problem

The API string an individual stands for is written nowhere in the model. Where
the two agree today, it is because the `rdfs:label` happens to match (`ksh:Finalized`,
"finalized"). Where they don't, nothing records it: `ksh:YesSide` is labelled "yes
side", and its API code is "yes".

What this has already cost, as recorded in the scope notes:

- **Versions through 0.6.0 listed the wrong vocabulary.** `ksh:MarketStatus`
  enumerated the `?status=` filter values instead of the `status` field values,
  so `settled` sat where `finalized` belongs. Nothing checked the individuals
  against the API, so nothing failed.
- **Two individuals rely on prose to say they don't map.** `ksh:Voided` has no
  API `result` value and must say in prose "should not be read as a mapping
  target". `ksh:ResolvedScalar` exists "so that the outcome enumeration matches
  the API's", a claim no check can read.

The README's "checked against the live API" is therefore a dated manual
observation, not a property of the repository. Code ingesting API data into FMO
has no lookup table. It must either match labels, which is wrong for `side`, or
keep its own mapping, which is the second copy that drifts.

## Out of scope

- **`fm:Comparator` and Kalshi's `strike_type`.** The codes were not part of the
  2026-08-17 check recorded in `src/`. `fm:Comparator` is also venue-neutral core,
  so a Kalshi code on it raises where venue codes on core individuals belong.
  That needs its own spec.
- **The `?status=` filter vocabulary.** It could become a second scheme, with
  `skos:broadMatch` from each status to its filter value, stating the
  many-to-one mapping the `ksh:MarketStatus` scope note describes in prose.
  Nothing consumes it yet.
- **Wrapping the vocabularies in `skos:ConceptScheme` or typing individuals
  `skos:Concept`.** `skos:Concept` would be a new external class that has to be
  grounded under `bfo:entity`. It would also duplicate `rdfs:label` as
  `prefLabel`, which moves the ThermalEdge label digests for nothing.
- **SKOS mapping properties to IAO.** SKOS gives `skos:exactMatch` a domain of
  `skos:Concept`, so any RDFS-aware load of SKOS would type FMO's classes as
  concepts. That's the class/individual crossover (punning) the design notes
  avoid on purpose.
- **Pinning the vocabulary shapes for a consumer**, as the export shapes are
  pinned. No consumer reads them.
- **A live-API conformance check in CI.** The shapes pin the documented
  enumeration. Re-reading the API is still a dated human act, now with a
  checked-in answer to compare against.

## Notes for the agent

### Solution

Each coded individual gets a typed `skos:notation` holding its API code, e.g.
`"finalized"^^ksh:StatusCode`. A new vocabulary shapes file states the API
enumeration and the rules over it. `make shapes` checks the modules against it,
and `make shapes-negative` proves each rule fires.

### User stories

1. As an ingest author, I want to look up the FMO individual for an API `status` string, so that I never match on labels.
2. As an ingest author, I want the `side` code "yes" to resolve to `ksh:YesSide` and the `result` code "yes" to `ksh:ResolvedYes`, so that one string in two fields cannot land on the wrong vocabulary.
3. As an ingest author, I want an API code that FMO does not know to be absent from the model, so that my ingest fails loudly instead of guessing.
4. As an ingest author, I want the empty `result` to deliberately have no individual, so that I treat an unresolved market as unresolved.
5. As an ingest author, I want `ksh:Voided` to carry no code, so that I never produce it from API data.
6. As a maintainer, I want the documented API enumeration checked into the repo, so that "checked against the live API" is something a test can compare.
7. As a maintainer, I want a code outside the documented enumeration to fail `make shapes`, so that a typo in a notation is caught.
8. As a maintainer, I want a documented code with no individual to fail `make shapes`, so that a new API status added to the enumeration forces a modelling decision.
9. As a maintainer, I want a new individual in a coded vocabulary to fail until it carries a code or is excepted, so that the 0.6.0 filter-value mistake cannot recur quietly.
10. As a maintainer, I want every exception to name a scope note, so that "no code" is a decision with a reason, not an omission.
11. As a maintainer, I want two individuals sharing a code to fail, so that the codes stay a lookup table.
12. As a maintainer, I want one individual carrying two codes in one field to fail, so that the mapping stays one-to-one.
13. As a maintainer, I want each vocabulary shape proved to match at least one focus node, so that a renamed class does not turn the shapes into a green no-op.
14. As a maintainer, I want HermiT to still load the modules, so that typed notation literals do not break reasoning.
15. As a ThermalEdge maintainer, I want the export contract and its pin untouched, so that this change needs no action on my side unless I opt in.
16. As a consumer pinning `semantics_sha256`, I want a changed code to move that term's digest, so that a remapped code is not invisible to my pins.
17. As a consumer, I want only the changed term's digest to move, so that one edit does not look like the whole vocabulary changed.
18. As a reader of CONTEXT.md, I want "API code" defined, with "label" on its avoid list, so that nobody says "the label" when they mean the code.
19. As a reviewer, I want each new datatype to carry a label and definition, so that it is documented like every other minted term.
20. As a reviewer, I want the vocabulary shapes kept separate from the export shapes, so that FMO's own vocabulary rules and ThermalEdge's contract cannot be confused or pinned together.
21. As a future spec author, I want the pattern to extend to `fm:Comparator`, so that `strike_type` becomes a follow-up rather than a redesign.

### Implementation decisions

- **One datatype per API field**, declared as `rdfs:Datatype` in the kalshi module
  with `rdfs:label` and `skos:definition`: `ksh:StatusCode`, `ksh:ResultCode`,
  `ksh:SideCode`, `ksh:ActionCode`. One shared datatype would make
  `"yes"` ambiguous between `result` and `side`. Per-field datatypes make
  uniqueness a property of the literal itself, with no scoping rule needed.
- **Declare `skos:notation` as an `owl:AnnotationProperty`.** The modules declare
  no annotation property today; OWLAPI infers them. An undeclared predicate with
  a custom-typed literal may instead be parsed as a data property, and HermiT then
  sees a datatype it does not support. Declaring it keeps the literals out of the
  reasoner's view. `make reason` in the JDK job is the witness either way.
- **The vocabulary shapes file is new, separate from the export shapes, and
  named in the registry** beside the existing shapes constant, so no checker
  keeps its own copy of the path. Its data graph is the modules alone: the
  population is the schema, so the examples cannot empty it or add to it.
- **Shapes, all SHACL core** (pyshacl runs with `advanced=True` already):
  - **Per vocabulary, targeting its class:** `skos:notation` has `sh:datatype`
    for that field, `sh:maxCount 1`, and `sh:in` listing the documented codes.
  - **Minimum count, with exceptions:** `sh:minCount 1`, written as an `sh:or`
    with `sh:in` listing the excepted individuals. Today that list is only
    `ksh:Voided`. The exception list lives in the shapes file, beside the
    enumeration it is an exception to.
  - **Uniqueness:** target `sh:targetObjectsOf skos:notation`, with
    `[sh:inversePath skos:notation] sh:maxCount 1`.
  - **Completeness:** each documented code is an `sh:targetNode` literal
    carrying `[sh:inversePath skos:notation] sh:minCount 1`. The empty `result`
    is simply not listed as a target.
- **`validate_shapes.py` gains a vocabulary mode** that loads the modules and no
  data files. `make shapes` runs it as a third step.
- **`term_signatures.py`:** the semantic rendering gains `notation:` lines,
  sorted, with datatype. `rdfs:Datatype` joins the declared kinds, so the four
  datatypes get signatures too. This moves `semantics_sha256` once for the 15
  coded individuals, not `definition_sha256`, so a consumer pinning prose sees
  nothing.
- **`validate.py`:** `rdfs:Datatype` joins `DECLARED_AS`, so CONTEXT.md can name
  the datatypes. `check_documentation` also covers datatypes in FMO's
  namespaces.
- **Version 0.13.0.** Additive annotations only; no existing term's meaning
  changes. The book's versioning chapter would call this a minor bump.

### Testing decisions

- A good test here feeds the vocabulary shapes a broken copy of the modules and
  asserts the specific constraint that should fire. It asserts that constraint,
  not a generic non-conformance, because a mutant rejected for the wrong reason
  hides a dead constraint. That is the rule `make export-check` already applies
  to the CQ2 fixture.
- `scripts/test_shapes.py` is prior art, and in-process for speed: vacuity per
  shape, plus mutants. Add hand-written mutants for the vocabulary shapes:
  - remove one coded individual's notation (`sh:minCount`);
  - add a second notation (`sh:maxCount`);
  - give two individuals the same code (inverse `sh:maxCount`);
  - use the wrong field's datatype (`sh:datatype`);
  - use a code outside the enumeration (`sh:in`);
  - drop the only individual carrying a documented code (targetNode `sh:minCount`);
  - add an individual to a coded vocabulary with neither a code nor an
    exception (`sh:or`).
- **The exception list's own claim**, that each excepted individual has no
  notation and does have a scope note, is a Python assertion in the same file.
  SHACL cannot see that an exception has gone stale. This follows ADR-0001's
  pattern of naming the scope note and confirming it is present.
- **Bump `EXPECTED_ASSERTIONS`** deliberately and say why in the commit.
- **`make signatures`:** add a mutation case. Alter one notation in memory,
  recompute, and assert exactly one term's `semantics_sha256` moved.
- **`scripts/test_validate.py`:** add a case for a datatype missing its
  `skos:definition`, per "new validator check ⇒ new negative test". The change
  to `check_documentation` counts.

### Terms

New `CONTEXT.md` entry, §3 (market side):

- **API code** (`skos:notation`): the string the Kalshi API uses for a designation, typed by its field's datatype.
- _Avoid_: "label" (`rdfs:label` is the English name: "yes side" vs "yes"), "enum value", "the status string".

The entry names the four datatypes in backticks, which is what makes
`check_context_terms` resolve them.

### Watch for

- **pyshacl and literal targets.** Confirm that pyshacl honours an
  `sh:targetNode` that is a literal before relying on it. If it does not, the
  completeness rule falls back to an `sh:sparql` constraint, and the mutant for
  it is what proves the fallback fires.
- **Codes stated twice.** The `ksh:MarketStatus` scope note's list of filter
  values and the shapes' enumeration of field values will sit a few files apart.
  Don't let the shapes file enumerate the filter values.

## Comments

**2026-09-22 — done.** `make test` passes with a JDK and no skips. The claims'
witnesses, each seen to fail when its subject was removed:

- `make shapes-negative`: 15 vocabulary assertions. That's 6 vacuity checks, the
  `sh:in`/`sh:targetNode` agreement check, the exception check, and 7 mutants,
  each credited only to the constraint it targets. Deleting
  `sh:datatype ksh:ActionCode` fails it.
- `make signatures`: remapping `ksh:Active`'s code moves only its
  `semantics_sha256`. Dropping `notation:` from the digest fails it.
- `make validate`: with `rdfs:Datatype` taken out of `DECLARED_AS`, CONTEXT.md's
  four datatype names are reported as undeclared.

Two findings differ from what the spec expected:

- **Literal `sh:targetNode` works in pyshacl.** The SPARQL fallback wasn't needed.
- **HermiT was never at risk.** It is consistent with the `skos:notation`
  declaration removed too, because OWLAPI already infers annotation properties.
  The declaration stays, matching how `bfo-core.ttl` declares the SKOS
  annotations it uses, and its comment says so rather than claiming it prevents
  a failure.
