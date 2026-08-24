# FMO 0.10.0 — Findings Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the five findings from the 0.9.0 read — report the coverage metric honestly, exercise the precipitation branch with a real settled rain market, widen the prose guard to README and docs, and record what stays open.

**Architecture:** Four tasks, each independently testable and independently rejectable. Task 1 changes an advisory note. Task 2 widens an existing check and is pure TDD against the repo's own negative-test harness. Task 3 adds one worked example file and is the only task with modelling risk. Task 4 is the release pass. Tasks 1 and 2 are independent of each other and of Task 3; Task 4 must come last.

**Tech Stack:** Turtle (OWL 2 DL, hand-authored), Python 3.12 + rdflib via poetry, ROBOT/HermiT for reasoning, GNU make.

**Spec:** `docs/superpowers/specs/2026-08-23-findings-remediation-design.md`

## Global Constraints

- **Every minted class and property needs `rdfs:label` and `skos:definition`.** The validator fails without them. This plan mints no classes or properties — if you find yourself minting one, stop and re-scope.
- **Every minted term must reach `bfo:entity` via `rdfs:subClassOf`.**
- **New validator check ⇒ new negative test** in `scripts/test_validate.py`. Task 2 widens a check and therefore needs one. Tasks 1, 3, 4 add no check.
- **An empty SPARQL result fails.** Never "fix" a competency question by letting it match nothing.
- **Units: identical where values are compared.** The rain example compares in `unit:IN` throughout.
- **`src/imports/bfo-core.ttl` is vendored — never edit it.** `src/imports/qudt-subset.ttl` is generated — never hand-edit it. Neither needs touching here.
- **Terminology follows `CONTEXT.md`.** Say "event grouping", never bare "event". Say "site", not "station", where settlement is meant. Say "current assessment", not "latest".
- **Version 0.10.0** lands in exactly five places, together, in Task 4 only.
- Everything runs through `poetry run`. `make test` is the gate.

## Two spec corrections found while planning

Both make the work smaller. Fold them in; do not follow the spec where it disagrees.

1. **`wx:TotalPrecipitation` already exists** (`src/weather.ttl:227`) as a `wx:WeatherVariable` individual with `fm:hasQuantityKind quantitykind:Length` and `wx:conventionalUnit unit:IN , unit:MilliM`. No weather variable needs minting for Task 3.
2. **The example lists are globs, not lists.** `scripts/validate.py:129` and `scripts/run_competency.py:72` both read `sorted((ROOT / "examples").glob("*.ttl"))`. Adding an example file requires **no** change to either list. The spec's "mechanical updates: MODULES and example lists" is wrong. The only registration Task 3 needs is the new prefix in `EXAMPLE_PREFIXES`.

---

### Task 1: Coverage metric reports the subclass closure

**Files:**
- Modify: `scripts/validate.py:1156-1170`
- Modify: `README.md` (the Open questions bullet beginning "**The trading layer is thin")

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: nothing later tasks rely on. The note text changes; no function signature changes.

**Why there is no negative test here.** The note is advisory and cannot fail — that is deliberate, and the comment above it says so. The CLAUDE.md rule binds new *checks*. Do not convert this to a check; README's Open questions depends on it staying a visible number rather than a gate.

- [ ] **Step 1: Read the current behaviour and record the baseline number**

Run: `poetry run python3 scripts/validate.py | grep 'minted classes have'`

Expected output, exactly:

```
40/98 minted classes have an instance in the examples
```

Write that line down. If it differs, Task 3 has already landed — stop and re-derive the expected numbers before continuing.

- [ ] **Step 2: Replace the coverage block**

In `scripts/validate.py`, find this block (it ends the documentation-coverage section, around line 1156):

```python
    schema_instantiated = {t for t in g.objects(None, RDF.type) if is_ours(t)}
    instantiated = {t for t in ex.objects(None, RDF.type) if is_ours(t)} - schema_instantiated
    covered = sum(1 for c in our_classes if c in instantiated)
    notes.append(
        f"{covered}/{len(our_classes)} minted classes "
        f"have an instance in the examples"
    )
```

Replace it with:

```python
    schema_instantiated = {t for t in g.objects(None, RDF.type) if is_ours(t)}
    instantiated = {t for t in ex.objects(None, RDF.type) if is_ours(t)} - schema_instantiated
    direct = sum(1 for c in our_classes if c in instantiated)

    # Counting direct rdf:type alone conflates two different things. An abstract
    # parent -- ksh:Market, wx:Forecast, fm:Document -- is exercised through a
    # child and can never gain a direct instance no matter how much data arrives,
    # so it sat in the uncovered count permanently, next to classes nothing can
    # instantiate because the vocabulary does not work. That second group is the
    # one README cites this figure to keep visible, and one number cannot separate
    # them. Report both: direct is the figure that tracks the gap, closure is the
    # figure that says how much of the tree the examples reach.
    descendants: dict[URIRef, set] = {}
    for cls in our_classes:
        seen: set = set()
        stack = [cls]
        while stack:
            node = stack.pop()
            for sub in g.subjects(RDFS.subClassOf, node):
                if sub not in seen:
                    seen.add(sub)
                    stack.append(sub)
        descendants[cls] = seen
    closure = sum(
        1 for c in our_classes if c in instantiated or (descendants[c] & instantiated)
    )
    notes.append(
        f"{direct} direct / {closure} via subclass / {len(our_classes)} "
        f"minted classes have an instance in the examples"
    )
```

- [ ] **Step 3: Run the validator and confirm all three numbers**

Run: `poetry run python3 scripts/validate.py | grep 'minted classes have'`

Expected output, exactly:

```
40 direct / 57 via subclass / 98 minted classes have an instance in the examples
```

If `direct` is not 40 or `closure` is not 57, the closure walk is wrong. `closure` must be strictly greater than `direct` and strictly less than 98.

- [ ] **Step 4: Confirm nothing else moved**

Run: `make validate && make validate-negative`

Expected: validator prints `OK`; negative tests print `67/67 checks passed`.

- [ ] **Step 5: Update the README sentence that cites the figure**

In `README.md`, in the Open questions bullet that begins `**The trading layer is thin, but no longer unexercised.**`, find:

```
`validate.py` reports the instantiated-class count on every run so the gap stays visible.
```

Replace with:

```
`validate.py` reports the instantiated-class count on every run so the gap stays
visible. It prints two figures: the direct count is the one that tracks this gap,
since a class nothing can instantiate stays in it; the subclass-closure count is
higher only because abstract parents are exercised through their children.
```

- [ ] **Step 6: Commit**

```bash
git add scripts/validate.py README.md
git commit -m "Report coverage as direct and subclass-closure counts

One number conflated an abstract parent with a class the vocabulary cannot
express. The first can never gain a direct instance; the second is the gap
README cites this figure to keep visible. Print both."
```

---

### Task 2: Widen the prose guard to README and docs

**Files:**
- Modify: `scripts/validate.py:117-125` (constants), `scripts/validate.py:953-1008` (`check_context_terms`)
- Modify: `scripts/test_validate.py` (add one case to `CASES`)
- Modify: `docs/design-notes.md:29` (strikethrough fix)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `PROSE_FILES: list[Path]` module constant in `validate.py`, and the failure message format `"{filename} names an undeclared term: {prefix}:{local}"`. Task 3 relies on `EXAMPLE_PREFIXES` gaining a key, which is edited in Task 3, not here.

**The ordering trap.** `docs/design-notes.md:29` writes `` `ksh:Event` `` without strikethrough — a name the project rejected, so it is declared nowhere by construction. The moment the check reads that file, `make validate` fails on the clean tree, which makes `test_validate.py`'s baseline fail and every negative result meaningless. The strikethrough fix and the widening must land in the **same commit**. Do not split them.

- [ ] **Step 1: Write the failing test**

In `scripts/test_validate.py`, add this case to the end of the `CASES` list (after the last tuple, before the closing `]`):

```python
    (
        # CONTEXT.md was guarded and README was not, though README backticks 22
        # minted terms and rots from a rename in exactly the same way. The guard
        # was written for one file because that is the file that had just been
        # added, not because the others were safe.
        "README.md naming a term that no longer exists",
        "README.md",
        "`wx:conventionalUnit` is deliberately\n**not** a sub-property of `fm:hasUnit`",
        "`wx:conventionalUnit_renamed` is deliberately\n**not** a sub-property of `fm:hasUnit`",
        "README.md names an undeclared term: wx:conventionalUnit_renamed",
    ),
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `poetry run python3 scripts/test_validate.py 2>&1 | grep -A3 'README.md naming'`

Expected: `FAIL [README.md naming a term that no longer exists]: validate.py passed but should have failed`

That is the correct failure. The mutation lands in README, the check never reads README, and the validator exits 0.

- [ ] **Step 3: Fix the strikethrough in design-notes**

In `docs/design-notes.md`, line 29, find:

```
`ksh:Event` under `bfo:process` gets an ontology that parses, reasons, and is wrong.
```

Replace with:

```
~~`ksh:Event`~~ under `bfo:process` gets an ontology that parses, reasons, and is wrong.
```

- [ ] **Step 4: Add the file list constant**

In `scripts/validate.py`, find:

```python
CONTEXT = ROOT / "CONTEXT.md"
```

Replace with:

```python
CONTEXT = ROOT / "CONTEXT.md"
# Every prose file that names minted terms and would rot from a rename. Not
# docs/superpowers/**: a plan or a spec describes a state the graph does not have
# yet, so checking one against the current graph fails on correct content. The
# path, make-target and check-name assertions stay scoped to CONTEXT.md, whose
# section 4 is repo mechanics and is why those assertions exist at all.
PROSE_FILES = [
    ROOT / "CONTEXT.md",
    ROOT / "README.md",
    ROOT / "docs" / "design-notes.md",
    ROOT / "docs" / "fmo-in-thermaledge.md",
]
```

- [ ] **Step 5: Make the check read every prose file**

In `scripts/validate.py`, in `check_context_terms`, find:

```python
    if not CONTEXT.exists():
        fail("missing CONTEXT.md")
        return
    text = CONTEXT.read_text(encoding="utf-8")

    declared = {s for cls in DECLARED_AS for s in g.subjects(RDF.type, cls) if is_ours(s)}
    deprecated = set(g.subjects(OWL.deprecated, Literal(True)))
    mentioned = set(CONTEXT_TERM.findall(text))
    if not mentioned:
        fail("CONTEXT.md names no terms in backticks, so this check matched nothing")
        return
    for prefix, local in sorted(mentioned):
        term = URIRef(CONTEXT_PREFIXES[prefix] + local)
        if prefix in EXAMPLE_PREFIXES:
            if (term, RDF.type, None) not in ex:
                fail(f"CONTEXT.md names an undefined individual: {prefix}:{local}")
        elif term in deprecated:
            fail(f"CONTEXT.md names a deprecated term: {prefix}:{local}")
        elif term not in declared:
            fail(f"CONTEXT.md names an undeclared term: {prefix}:{local}")

    paths = set(CONTEXT_PATH.findall(text))
```

Replace with:

```python
    for path in PROSE_FILES:
        if not path.exists():
            fail(f"missing prose file: {path.name}")
            return
    if not CONTEXT.exists():
        fail("missing CONTEXT.md")
        return
    text = CONTEXT.read_text(encoding="utf-8")

    declared = {s for cls in DECLARED_AS for s in g.subjects(RDF.type, cls) if is_ours(s)}
    deprecated = set(g.subjects(OWL.deprecated, Literal(True)))

    total_mentioned = 0
    for path in PROSE_FILES:
        prose = path.read_text(encoding="utf-8")
        mentioned = set(CONTEXT_TERM.findall(prose))
        if path == CONTEXT and not mentioned:
            fail("CONTEXT.md names no terms in backticks, so this check matched nothing")
            return
        total_mentioned += len(mentioned)
        for prefix, local in sorted(mentioned):
            term = URIRef(CONTEXT_PREFIXES[prefix] + local)
            if prefix in EXAMPLE_PREFIXES:
                if (term, RDF.type, None) not in ex:
                    fail(f"{path.name} names an undefined individual: {prefix}:{local}")
            elif term in deprecated:
                fail(f"{path.name} names a deprecated term: {prefix}:{local}")
            elif term not in declared:
                fail(f"{path.name} names an undeclared term: {prefix}:{local}")

    paths = set(CONTEXT_PATH.findall(text))
```

- [ ] **Step 6: Update the note line at the end of the check**

In the same function, find:

```python
    notes.append(
        f"CONTEXT.md: {len(mentioned)} term(s), {len(paths)} path(s), "
        f"{len(targets)} make target(s), {len(checks)} check name(s) verified"
    )
```

Replace with:

```python
    notes.append(
        f"prose: {total_mentioned} term(s) across {len(PROSE_FILES)} file(s), "
        f"{len(paths)} path(s), {len(targets)} make target(s), "
        f"{len(checks)} check name(s) verified"
    )
```

- [ ] **Step 7: Update the docstring's first line**

In the same function, find:

```python
    """CONTEXT.md names terms in prose, and no tool but this one reads it.
```

Replace with:

```python
    """The prose files name terms, and no tool but this one reads them.
```

- [ ] **Step 8: Run the validator on the clean tree**

Run: `make validate`

Expected: `OK`, and the note line now reads:

```
prose: 141 term(s) across 4 file(s), 13 path(s), 2 make target(s), 1 check name(s) verified
```

The term count is the sum over the four files and will differ if README changed in Task 1 — any number over 130 is fine. What must be true: exit 0. If it fails naming `ksh:Event`, Step 3 was skipped.

- [ ] **Step 9: Run the negative tests and watch the new case pass**

Run: `poetry run python3 scripts/test_validate.py 2>&1 | tail -5`

Expected: `68/68 checks passed`, and the README case now prints `ok`.

- [ ] **Step 10: Prove the test is real by reverting the check**

Temporarily change `PROSE_FILES` to `[ROOT / "CONTEXT.md"]`, run `poetry run python3 scripts/test_validate.py 2>&1 | grep 'README.md naming'`, confirm it FAILS, then restore the four-file list and confirm it passes again. A check nobody has watched fail is not known to work.

- [ ] **Step 11: Commit**

```bash
git add scripts/validate.py scripts/test_validate.py docs/design-notes.md
git commit -m "Guard the terms README and docs name, not just CONTEXT.md

README backticks 22 minted terms and docs another 73, none of them read by
anything. They rot from a rename the same way CONTEXT.md would; the guard was
scoped to one file because that file had just been added.

docs/superpowers/** stays excluded: a plan describes a state the graph does
not have yet, so checking it against the current graph fails on correct
content. design-notes now strikes through the rejected ksh:Event, which is
the convention CONTEXT.md section 5 already prescribes."
```

---

### Task 3: The rain worked example

**Files:**
- Create: `examples/kxrainnyc-2026-07-15.ttl`
- Modify: `scripts/validate.py:105-110` (`EXAMPLE_PREFIXES`)
- Modify: `src/weather.ttl:157` (the scope note the exchange contradicts)
- Modify: `queries/*.expected` (regenerated, reviewed)

**Interfaces:**
- Consumes: `EXAMPLE_PREFIXES` from `validate.py` — add the key `"rex"`. If Task 2 has landed, `PROSE_FILES` exists but is not touched here.
- Produces: the namespace `https://w3id.org/forecast-market-ontology/examples/kxrainnyc-2026-07-15#` with prefix `rex:`. Individuals later tasks may cite: `rex:Market-Rain-T0`, `rex:Prop-Rain`, `rex:Target-Precip`, `rex:NWSDailyPrecipProtocol`.

**Source data.** Every market value below came from the live Kalshi API on 2026-08-23, endpoint `/trade-api/v2/markets/KXRAINNYC-26JUL15-T0`. `result: yes`, `expiration_value: 0.27`, `strike_type: greater`, `floor_strike: 0`, `status: finalized`. The forecast probability is illustrative — Kalshi publishes no forecast — and the file says so, as the temperature example does.

**Stop conditions.** If the vocabulary cannot express something here without minting a class or property, **stop and report**. That is the finding this task exists to produce, and minting a term quietly to make the example work is how the eighteen dark classes got there. Likewise if HermiT reports an inconsistency: that is a result, not an obstacle to route around.

- [ ] **Step 1: Register the prefix**

In `scripts/validate.py`, find:

```python
EXAMPLE_PREFIXES = {
    "ex": "https://w3id.org/forecast-market-ontology/examples/kxhighny-2026-08-15#",
    "tex": "https://w3id.org/forecast-market-ontology/examples/kxhighny-2026-08-15-trading#",
    "vex": "https://w3id.org/forecast-market-ontology/examples/verification#",
}
```

Replace with:

```python
EXAMPLE_PREFIXES = {
    "ex": "https://w3id.org/forecast-market-ontology/examples/kxhighny-2026-08-15#",
    "tex": "https://w3id.org/forecast-market-ontology/examples/kxhighny-2026-08-15-trading#",
    "vex": "https://w3id.org/forecast-market-ontology/examples/verification#",
    "rex": "https://w3id.org/forecast-market-ontology/examples/kxrainnyc-2026-07-15#",
}
```

- [ ] **Step 2: Write the example file**

Create `examples/kxrainnyc-2026-07-15.ttl` with exactly this content:

```turtle
# Worked example: the daily NYC rain market, settled, followed through to
# assessment. The second worked example, and the first outside temperature.
#
# It exists to answer a question the ontology had never been asked: whether the
# precipitation vocabulary can express a real listed market, or is only minted.
# Through 0.9.0 eighteen classes in weather.ttl had no instance, no query and no
# check -- the condition the trading layer was in through 0.7.1, where unused
# turned out to mean unusable.
#
# The market decides one thing the model had left to prose. Kalshi settles
# "will it rain" as strike_type: greater, floor_strike: 0 -- a threshold on a
# QUALITY, precipitation depth, not the occurrence of a process. So the
# proposition's subject is the depth target, exactly as the exchange settles it,
# and the rainfall process appears where it belongs: in the record of what
# happened, not in the claim about what would.
#
# Market values are from the Kalshi API on 2026-08-23 (result yes, expiration
# value 0.27 inches). The forecast probability is illustrative -- Kalshi
# publishes no forecast -- as in the temperature example.

@prefix rex:  <https://w3id.org/forecast-market-ontology/examples/kxrainnyc-2026-07-15#> .
@prefix ex:   <https://w3id.org/forecast-market-ontology/examples/kxhighny-2026-08-15#> .
@prefix fm:   <https://w3id.org/forecast-market-ontology/core#> .
@prefix wx:   <https://w3id.org/forecast-market-ontology/weather#> .
@prefix ksh:  <https://w3id.org/forecast-market-ontology/kalshi#> .
@prefix bfo:  <http://purl.obolibrary.org/obo/> .
@prefix owl:  <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .
@prefix unit: <http://qudt.org/vocab/unit/> .

<https://w3id.org/forecast-market-ontology/examples/kxrainnyc-2026-07-15>
    a owl:Ontology ;
    owl:imports <https://w3id.org/forecast-market-ontology/fmo> ;
    rdfs:label "Worked example: KXRAINNYC-26JUL15" .

################################################################
# 1. Time
#
# Same climatological day rule as the temperature example: local STANDARD time
# midnight to midnight all year. 15 July 2026 is inside daylight saving time,
# so the interval runs 01:00 EDT on the 15th to 00:59:59 EDT on the 16th.
#
# The site is ex:CentralParkSite, defined in the temperature example. The market
# rules name it directly: "the number of inches of precipitation recorded at
# Central Park, New York". Re-using it rather than minting a second site is the
# point of the site/station split -- one persistent place of record, many
# variables measured there.
################################################################

rex:ClimDay-2026-07-15 a wx:ClimatologicalDay ;
    rdfs:label "climatological day 2026-07-15 at Central Park" ;
    bfo:BFO_0000222 rex:Instant-Start ;     # has first instant
    bfo:BFO_0000224 rex:Instant-End .       # has last instant

rex:Instant-Start a bfo:BFO_0000203 ; fm:instantDateTime "2026-07-15T01:00:00-04:00"^^xsd:dateTime .
rex:Instant-End   a bfo:BFO_0000203 ; fm:instantDateTime "2026-07-16T00:59:59-04:00"^^xsd:dateTime .

################################################################
# 2. What is being measured
#
# A separate protocol from ex:NWSDailyClimateProtocol, though both are the NWS
# CLI product for NYC. The reporting increment differs -- hundredths of an inch
# against whole degrees -- and the increment is a property of the protocol. Two
# targets differing in protocol are different targets; the rule does not bend
# because the publisher happens to be the same.
#
# The trace case is where this protocol earns its keep. The CLI product reports
# "T" for a measurable-but-unquantifiable trace, and Kalshi's rules resolve Yes
# on T when the threshold is 0. T is not a number, so a datum reporting it could
# not carry fm:realizedValue at all. This example settles on 0.27 inches and does
# not exercise that path; it is named here so the next reader does not assume it
# was handled.
################################################################

rex:NWSDailyPrecipProtocol a wx:MeasurementProtocol ;
    rdfs:label "NWS daily precipitation protocol for CLINYC" ;
    fm:statedAs "Total liquid-equivalent precipitation recorded at the New York City station of record over the climatological day, in hundredths of an inch, as published in the NWS CLI product for NYC. A trace is reported as T and is not a numeric value." ;
    fm:issuedBy ex:NWS .

rex:Target-Precip a wx:WeatherObservationTarget ;
    rdfs:label "total precipitation, Central Park, climatological day 2026-07-15" ;
    wx:targetVariable wx:TotalPrecipitation ;
    wx:atSite ex:CentralParkSite ;
    fm:overTemporalInterval rex:ClimDay-2026-07-15 ;
    wx:underProtocol rex:NWSDailyPrecipProtocol ;
    fm:hasUnit unit:IN .

################################################################
# 3. The proposition -- the pivot
#
# fm:GreaterThan, floor 0, no cap. The API returns cap_strike 0 alongside
# floor_strike 0 for a greater-strike market; it is not a cap and is not
# recorded as one. Writing fm:capValue 0 here would make the proposition say
# "exactly 0", which is the opposite of what it settles.
################################################################

rex:Prop-Rain a fm:Proposition ;
    rdfs:label "more than 0 inches of precipitation" ;
    fm:hasSubject rex:Target-Precip ;
    fm:hasComparator fm:GreaterThan ;
    fm:floorValue "0"^^xsd:decimal ;
    fm:hasUnit unit:IN ;
    fm:statedAs "The total precipitation recorded at the Central Park station of record over the climatological day of 15 July 2026, as published in the NWS CLI product for NYC, is strictly greater than 0 inches." .

################################################################
# 4. The market side
#
# No ksh:mutuallyExclusive on the grouping. This event lists one market, and one
# market partitions nothing -- the complement of Yes is the No side of the same
# contract, not a sibling market. Asserting exclusivity would be trivially true
# and would teach the next reader the wrong thing about what the flag means.
################################################################

rex:NWSPrecipSettlementSource a ksh:SettlementSource ;
    rdfs:label "NWS climatological report for NYC, precipitation" ;
    ksh:sourceProtocol rex:NWSDailyPrecipProtocol ;
    fm:issuedBy ex:NWS .

rex:KXRAINNYC a ksh:Series ;
    rdfs:label "Kalshi: rain in NYC, daily" ;
    ksh:seriesTicker "KXRAINNYC" ;
    ksh:settlementSource rex:NWSPrecipSettlementSource ;
    fm:issuedBy ksh:Kalshi .

rex:KXRAINNYC-26JUL15 a ksh:EventGrouping ;
    rdfs:label "Kalshi: rain in NYC on 2026-07-15" ;
    ksh:eventTicker "KXRAINNYC-26JUL15" ;
    ksh:inSeries rex:KXRAINNYC ;
    ksh:coversTarget rex:Target-Precip .

rex:Market-Rain-T0 a ksh:WeatherMarket ;
    rdfs:label "KXRAINNYC-26JUL15-T0" ;
    ksh:marketTicker "KXRAINNYC-26JUL15-T0" ;
    ksh:inEventGrouping rex:KXRAINNYC-26JUL15 ;
    ksh:expressesProposition rex:Prop-Rain ;
    ksh:hasStatus ksh:Finalized ;
    ksh:closeTime "2026-07-16T03:59:00Z"^^xsd:dateTime ;
    ksh:expectedExpirationTime "2026-07-16T14:00:00Z"^^xsd:dateTime ;
    ksh:latestExpirationTime   "2026-07-22T14:00:00Z"^^xsd:dateTime .

rex:Quote-Prior a ksh:Quote ;
    rdfs:label "quote for KXRAINNYC-26JUL15-T0 before the day began" ;
    ksh:quoteForMarket rex:Market-Rain-T0 ;
    fm:referenceTime "2026-07-14T20:00:00Z"^^xsd:dateTime ;
    ksh:yesBidCents 7 ;
    ksh:yesAskCents 28 ;
    ksh:lastPriceCents 24 .

rex:MarketProb-Prior a fm:MarketImpliedProbability ;
    rdfs:label "market implied P(rain) before the day began" ;
    fm:assignsProbabilityTo rex:Prop-Rain ;
    fm:probabilityValue "0.24"^^xsd:decimal ;
    fm:referenceTime "2026-07-14T20:00:00Z"^^xsd:dateTime ;
    ksh:derivedFromQuote rex:Quote-Prior ;
    fm:statedAs "Last traded price of 24 cents divided by 100. Ignores spread, fees, and carry. The 21-cent spread here is much wider than the temperature example's 4 cents, which is what the placeholder derivation cannot see." .

rex:Derivation-Prior a ksh:PriceToProbabilityDerivation ;
    fm:hasInput rex:Quote-Prior ;
    fm:hasOutput rex:MarketProb-Prior .

################################################################
# 5. The forecast side -- same proposition, different agent
################################################################

rex:Forecast-Rain a wx:ProbabilisticForecast ;
    rdfs:label "probability-of-precipitation forecast for Central Park, 2026-07-15" ;
    wx:forecastFor rex:Target-Precip ;
    wx:producedByModel ex:GEFS ;
    wx:issuanceTime "2026-07-14T18:00:00Z"^^xsd:dateTime ;
    wx:leadTimeHours "11.0"^^xsd:decimal ;
    bfo:BFO_0000178 rex:ForecastProb-Rain .     # has continuant part

rex:ForecastProb-Rain a fm:ForecastProbability ;
    rdfs:label "P(measurable precipitation) for 2026-07-15" ;
    fm:assignsProbabilityTo rex:Prop-Rain ;
    fm:probabilityValue "0.45"^^xsd:decimal ;
    fm:referenceTime "2026-07-14T18:00:00Z"^^xsd:dateTime .

# 21 points between the forecast and the market, against 8 in the temperature
# example, on the second proposition to carry both. The join is now demonstrated
# on more than one individual, which is what makes it a join rather than a
# coincidence.

################################################################
# 6. What actually happened
#
# The occurrent, at last. It rained; the rainfall process has as output a
# portion of precipitate; that portion bears a precipitation depth; the CLI
# report records the depth. The proposition points at none of this -- its
# subject is the target, which specifies what WOULD be measured. That is
# modelling decision 2 holding under a market that reads as being about a
# process.
################################################################

rex:Rainfall-2026-07-15 a wx:Rainfall ;
    rdfs:label "rainfall at Central Park on the climatological day 2026-07-15" ;
    bfo:BFO_0000199 rex:ClimDay-2026-07-15 ;    # occupies temporal region
    fm:hasOutput rex:Precipitate .

rex:Precipitate a wx:PortionOfPrecipitate ;
    rdfs:label "the water that fell at Central Park on 2026-07-15" ;
    bfo:BFO_0000171 ex:CentralParkSite .        # located in

rex:Depth-2026-07-15 a wx:PrecipitationDepth ;
    rdfs:label "the depth that portion of precipitate occupied" ;
    bfo:BFO_0000197 rex:Precipitate .           # inheres in

rex:Observation-Precip a wx:WeatherObservation ;
    rdfs:label "determination of the daily precipitation total at KNYC" ;
    bfo:BFO_0000057 ex:KNYC ;                   # has participant
    bfo:BFO_0000199 rex:ClimDay-2026-07-15 ;    # occupies temporal region
    fm:hasOutput rex:Datum-Precip .

rex:Datum-Precip a wx:WeatherObservationDatum ;
    rdfs:label "precipitation 0.27 inches" ;
    wx:reportsValueFor rex:Target-Precip ;
    fm:realizedValue "0.27"^^xsd:decimal ;
    fm:hasUnit unit:IN .

rex:CLINYC-2026-07-16 a wx:DailyClimatologicalReport ;
    rdfs:label "NWS CLINYC issued 2026-07-16" ;
    fm:issuedBy ex:NWS ;
    fm:overTemporalInterval rex:ClimDay-2026-07-15 ;
    wx:issuanceTime "2026-07-16T10:00:00Z"^^xsd:dateTime ;
    bfo:BFO_0000178 rex:Datum-Precip .          # has continuant part

################################################################
# 7. Settlement
################################################################

rex:Settlement-Rain a ksh:MarketSettlement ;
    rdfs:label "settlement of KXRAINNYC-26JUL15-T0" ;
    fm:hasAgent ksh:Kalshi ;
    fm:hasInput rex:CLINYC-2026-07-16 ;
    fm:hasOutput rex:Resolution-Rain .

rex:Resolution-Rain a ksh:Resolution ;
    rdfs:label "KXRAINNYC-26JUL15-T0 resolved yes" ;
    ksh:resolutionOf rex:Market-Rain-T0 ;
    ksh:resolvesTo ksh:ResolvedYes ;
    ksh:settlementValue "0.27"^^xsd:decimal ;
    fm:hasUnit unit:IN .

rex:Assessment-Rain-at-settlement a fm:TruthAssessment ;
    rdfs:label "assessment of Prop-Rain at settlement" ;
    fm:assessesProposition rex:Prop-Rain ;
    fm:assessedTruthValue fm:True ;
    fm:basedOnRecord rex:CLINYC-2026-07-16 ;
    fm:referenceTime "2026-07-16T12:00:00Z"^^xsd:dateTime .
```

- [ ] **Step 3: Parse and validate**

Run: `make validate`

Expected: `OK`.

If Task 1 has landed, the coverage note moves. The direct count rises by **exactly 3** — `wx:Rainfall`, `wx:PortionOfPrecipitate` and `wx:PrecipitationDepth` are the only classes this file types that nothing typed before — so `40 direct` becomes `43 direct`. The closure count rises by more, because `wx:PrecipitationProcess` and `wx:MeteorologicalProcess` become reachable through `wx:Rainfall`; do not treat a specific closure number as the gate, only that it rose and stayed below 98.

If the run fails, read the message before changing anything — a failure here is the finding this task exists to produce. Report it rather than working around it.

- [ ] **Step 4: Confirm the four dark classes now have instances**

Run:

```bash
poetry run python3 -c "
from rdflib import Graph, RDF, URIRef
import glob
g = Graph()
for f in sorted(glob.glob('examples/*.ttl')): g.parse(f, format='turtle')
WX = 'https://w3id.org/forecast-market-ontology/weather#'
for name in ['Rainfall', 'PortionOfPrecipitate', 'PrecipitationDepth']:
    n = len(list(g.subjects(RDF.type, URIRef(WX + name))))
    print(f'{name}: {n} instance(s)')
"
```

Expected: each prints `1 instance(s)`.

- [ ] **Step 5: Confirm the join now rests on two propositions**

Run: `make validate | grep 'join demonstrated'`

Expected: `forecast/market join demonstrated on 2 proposition(s)` — the count of expressed, forecast and market-implied propositions each rise by one.

- [ ] **Step 6: Reason over the new graph**

Run: `make reason`

Expected: `consistent`, printed twice-over (schema, then schema plus examples). If HermiT reports an inconsistency, **stop and report it** — the occurrent modelling is a design commitment and its failure is a result worth having, recorded in `docs/design-notes.md` rather than patched away.

- [ ] **Step 7: Regenerate the competency expectations**

The competency queries read `examples/*.ttl` by glob, so a fifth example file changes their results. This is expected, not a regression.

Run: `make cq` first and confirm it FAILS with differing results — that is the proof the queries actually see the new data. Then:

```bash
make cq-update
git diff queries/
```

Review the diff before staging. Expected: `cq01` gains the rain market row, `cq02` gains the rain probability-gap row, `cq04` gains the rain settlement-provenance row. `cq06a`, `cq06b`, `cq07` and `cq08` must be **unchanged** — the rain example adds no verification sample, no correction, and no order flow. If `cq05` changes, read why: the rain grouping asserts no `ksh:mutuallyExclusive`, so it should not appear in a bracket-coherence result at all.

If any expectation shrinks or empties, stop. An empty result set fails by design.

- [ ] **Step 7b: Re-point the cq-update negative test (controller Ruling 2)**

`scripts/test_validate.py` reuses `COMPETENCY_CASES[0]` — the mutation that breaks the temperature example's forecast/market join — for its `--update` case, expecting the output substring `returned 0 rows`. That works today only because cq02 has exactly one joined proposition. This example adds a second, so breaking the temperature join now leaves 1 row, not 0, and the case fails for a reason unrelated to what it tests.

The case exists to prove `make cq-update` does not report success when a query returns nothing. Point it at a query the rain example does not touch. In `scripts/test_validate.py`, find:

```python
    print("\n  -- cq-update --")
    results.append(run_case(
        *COMPETENCY_CASES[0][:4],
        "returned 0 rows",
        script="scripts/run_competency.py --update",
    ))
```

Replace with:

```python
    # Deliberately not COMPETENCY_CASES[0]. That mutation breaks the temperature
    # example's forecast/market join, which emptied cq02 back when the temperature
    # example was the only one joining a forecast to a market. The rain example is
    # a second, so breaking one leaves the other and the result is short, not
    # empty. cq08 is single-sourced by the trading example, which no other example
    # feeds, so removing the execution price still empties it -- and emptiness is
    # the whole point of this case.
    print("\n  -- cq-update --")
    results.append(run_case(
        "cq-update reporting success on a query that returned nothing",
        TRADING,
        "    ksh:executionPriceCents 60 ;\n",
        "",
        "returned 0 rows",
        script="scripts/run_competency.py --update",
    ))
```

- [ ] **Step 7c: Watch the re-pointed case fail for the right reason**

Run: `poetry run python3 scripts/test_validate.py 2>&1 | tail -6`

Expected: all cases pass, including `ok   [cq-update reporting success on a query that returned nothing]`.

Then prove it is real: temporarily change the anchor string to `"    ksh:executionPriceCents 61 ;\n"` (a value that does not exist), re-run, and confirm it reports `SETUP FAIL` rather than passing silently. Restore the correct anchor. A case whose anchor has drifted reports success while testing nothing, which is the failure mode this whole file exists to prevent.

- [ ] **Step 8: Correct the scope note the exchange contradicts**

In `src/weather.ttl`, in `wx:PrecipitationProcess`, find:

```
    skos:scopeNote "\"Rain\" is ambiguous between this process and the portion of precipitate it produces. Markets that ask whether it will rain are about the process; markets that ask how many inches are about a quality of the output." .
```

Replace with:

```
    skos:scopeNote "\"Rain\" is ambiguous between this process and the portion of precipitate it produces. The ambiguity does not survive contact with a settlement rule: Kalshi lists \"will it rain\" as a threshold of strictly greater than zero inches, so both that market and an inches market are about a quality of the output, and neither is about this process. The process is what the observational record reports on -- see examples/kxrainnyc-2026-07-15.ttl, where it bears the depth the report carries and the proposition points at the target instead." .
```

- [ ] **Step 9: Run the full suite**

Run: `make test`

Expected: every stage green — validator `OK`, `67/67 checks passed` (68 if Task 2 landed), synthetic dataset matches, diagram check `OK`, `8/8 competency questions answered as expected`, `consistent`, `6/6 reasoner guards fire`, and `PASS: ksh:WeatherMarket inferred`.

- [ ] **Step 10: Commit**

```bash
git add examples/kxrainnyc-2026-07-15.ttl scripts/validate.py src/weather.ttl queries/
git commit -m "Exercise the precipitation branch on a real settled rain market

Eighteen classes in weather.ttl had no instance, no query and no check --
the condition the trading layer was in through 0.7.1, where unused turned
out to mean unusable. KXRAINNYC-26JUL15-T0 answers the question for the
precipitation branch.

It also decides something the model had left to prose. Kalshi settles
'will it rain' as a threshold on precipitation depth, not on the occurrence
of a process, so the proposition's subject is the depth target and the
rainfall process sits in the record of what happened. weather.ttl's scope
note claimed the opposite split; it now says what the exchange does.

Second proposition to carry both a forecast and a market-implied
probability, so the join is demonstrated on more than one individual."
```

---

### Task 4: Record what stays open, and release 0.10.0

**Files:**
- Modify: `README.md` (Open questions, status line)
- Modify: `src/core.ttl:15,29`, `src/weather.ttl:16,24`, `src/kalshi.ttl:14,22`, `src/fmo.ttl:8,20`

**Interfaces:**
- Consumes: Tasks 1–3 complete and committed. The README edits assume Task 1's coverage sentence is already in place.
- Produces: the released 0.10.0 tree. Nothing consumes it.

- [ ] **Step 1: Add the two new Open questions entries**

In `README.md`, in the Open questions list, insert these two bullets immediately before the bullet beginning `- **Bracket exhaustiveness is unchecked.**`:

```markdown
- **Nested ladders are modelled as if they partitioned.** `KXRAINNYCM` lists "Above
  8 inches", "Above 9", "Above 10" — each bracket entails the next, so the ladder is
  monotone rather than a partition. `check_grouping_coherence` refuses overlapping
  brackets in a grouping asserted mutually exclusive, and CQ5 prices a ladder as a
  set that should cost a dollar. Neither is right for a monotone ladder, where the
  invariant is non-increasing prices and the correct arbitrage test is a price
  inversion between adjacent rungs. The grouping model assumes partition semantics
  and nothing says so. `examples/kxrainnyc-2026-07-15.ttl` sidesteps it by listing
  one market and asserting no exclusivity.
- **Wind, storms and atmospheric state have no market to model.** Checked against the
  live Kalshi API on 2026-08-23: of 354 series in Climate and Weather, none is a wind
  market. `wx:WindSpeed`, `wx:WindDirection` and `wx:AirMotion` are therefore minted
  against nothing listable, and `wx:Storm`, `wx:Thunderstorm` and `wx:TropicalCyclone`
  remain contested on their own terms (`docs/design-notes.md`). Sixteen of the
  eighteen classes that had no instance at 0.9.0 still have none; the rain example
  closed two of them, plus two parents. Whether the rest earn their place is open.
```

- [ ] **Step 2: Update the status line**

In `README.md`, find:

```
Status: **0.9.0.** Consistent under HermiT, structurally validated, unit-checked against QUDT.
All eight competency questions are mechanically tested. Kalshi field names and enumerations
were checked against the live API on 2026-08-17. Term coverage is deliberately shallow in places; see
[Open questions](#open-questions).
```

Replace with:

```
Status: **0.10.0.** Consistent under HermiT, structurally validated, unit-checked against QUDT.
All eight competency questions are mechanically tested. Kalshi field names and enumerations
were checked against the live API on 2026-08-17, and the precipitation series on 2026-08-23.
Two worked examples: a temperature bracket and a settled rain market. Term coverage is
deliberately shallow in places; see [Open questions](#open-questions).
```

- [ ] **Step 3: Add the rain example to the layout table**

In `README.md`, in the Layout table, find the `examples/` row:

```
| `examples/` | worked data: one bracket end-to-end, the full ladder, a correction, the order flow behind one match, 40 synthetic days |
```

Replace with:

```
| `examples/` | worked data: one bracket end-to-end, the full ladder, a correction, the order flow behind one match, a settled rain market, 40 synthetic days |
```

- [ ] **Step 4: Bump all four modules**

Run:

```bash
sed -i '' 's|forecast-market-ontology/core/0\.9\.0|forecast-market-ontology/core/0.10.0|' src/core.ttl
sed -i '' 's|forecast-market-ontology/weather/0\.9\.0|forecast-market-ontology/weather/0.10.0|' src/weather.ttl
sed -i '' 's|forecast-market-ontology/kalshi/0\.9\.0|forecast-market-ontology/kalshi/0.10.0|' src/kalshi.ttl
sed -i '' 's|forecast-market-ontology/fmo/0\.9\.0|forecast-market-ontology/fmo/0.10.0|' src/fmo.ttl
sed -i '' 's|owl:versionInfo "0\.9\.0"|owl:versionInfo "0.10.0"|' src/core.ttl src/weather.ttl src/kalshi.ttl src/fmo.ttl
```

- [ ] **Step 5: Verify the bump is complete and uniform**

Run: `grep -rn '0\.9\.0' src/ README.md`

Expected: **no output.** Any hit is a version left behind; CLAUDE.md requires all five move together.

Run: `grep -c '0\.10\.0' src/core.ttl src/weather.ttl src/kalshi.ttl src/fmo.ttl`

Expected: `2` for each file — one `versionIRI`, one `versionInfo`.

- [ ] **Step 6: Run the full suite one last time**

Run: `make test`

Expected: every stage green. This is the release gate; nothing ships with a red stage.

- [ ] **Step 7: Commit**

```bash
git add README.md src/core.ttl src/weather.ttl src/kalshi.ttl src/fmo.ttl
git commit -m "Release 0.10.0

Two Open questions added rather than quietly carried: nested ladders are
modelled as if they partitioned, which they do not, and no wind market
exists to model, so those classes are minted against nothing listable.

Sixteen of the eighteen classes with no instance at 0.9.0 still have none.
The version bump says what changed and not more than that -- trading-layer
breadth is untouched, and still one payout and one trade."
```

---

## What this plan deliberately does not do

- **No new payout, trade, or position.** Trading-layer breadth stays exactly where README already says it is. A version bump implying otherwise would be the same mistake as a green check nobody has watched fail.
- **No nested-ladder support.** `check_grouping_coherence` and CQ5 keep their partition assumption. Task 4 writes it down; a later cycle fixes it.
- **No pruning of the dark classes.** Sixteen stay. Whether they earn their place is recorded as open, not decided here.
- **Nothing in `viz/`.** `make diagram-check` already guards it.
