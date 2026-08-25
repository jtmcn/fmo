# FMO — the Forecast-Market Ontology

An ontology relating **weather forecasts** to the **Kalshi prediction markets** listed on
them, built on [Basic Formal Ontology 2020](https://github.com/BFO-ontology/BFO-2020)
(ISO/IEC 21838-2).

Status: **0.12.0.** Consistent under HermiT, structurally validated, unit-checked against QUDT.
All eight competency questions are mechanically tested. Kalshi field names and enumerations
were checked against the live API on 2026-08-17, and the precipitation series on 2026-08-23.
Worked markets: a temperature bracket ladder and a settled rain market. Term coverage is
deliberately shallow in places; see [Open questions](#open-questions).

## What it is for

A weather forecast and a weather market are two agents' beliefs about the same future fact.
Comparing them is the whole point — that gap is the tradeable signal — but comparing them
naively goes wrong, because "the high in NYC on Friday" means slightly different things to
a forecaster and to an exchange's settlement rules.

This ontology makes the comparison well-formed by giving both sides a shared pivot:

```
   wx:ProbabilisticForecast                    ksh:Market
      (GEFS 06Z run)                    (KXHIGHNY-26AUG15-B82.5)
            |                                       |
   has part |                                       | expressesProposition
            v                                       v
  fm:ForecastProbability  ---------------> fm:Proposition <--------------- fm:MarketImpliedProbability
        P = 0.52            assignsProbabilityTo    |    assignsProbabilityTo         P = 0.60
                                                    | hasSubject                  (derived from a quote)
                                                    v
                                        wx:WeatherObservationTarget
                                     (max air temp @ Central Park site,
                                      over climatological day 2026-08-15,
                                      under The Weather Company protocol)
```

Both probabilities point at **the same `fm:Proposition` individual**, so subtracting them
means something. Nothing else has to line up — not tickers, not station names, not dates.

## Layout

| Path | Contents |
|---|---|
| `src/core.ttl` | `fm:` — information content entities, propositions, probability, agents |
| `src/weather.ttl` | `wx:` — atmosphere, qualities, weather processes, observation, forecasting |
| `src/kalshi.ttl` | `ksh:` — series, event groupings, markets, contracts, trading, settlement |
| `src/fmo.ttl` | top module; imports all three |
| `src/imports/bfo-core.ttl` | vendored BFO 2020 core, unmodified |
| `src/imports/qudt-subset.ttl` | 16 units + 10 quantity kinds extracted from QUDT (generated) |
| `src/catalog-v001.xml` | OASIS catalog so imports resolve offline |
| `examples/` | worked data: one bracket end-to-end, the full ladder, a correction, the order flow behind one match, a settled rain market, 40 synthetic days |
| `scripts/validate.py` | structural, grounding, and unit checks (no Java needed) |
| `scripts/test_validate.py` | negative tests proving the validator fails when it should |
| `shapes/thermaledge-export.ttl` | SHACL shapes: what a valid ThermalEdge export must contain |
| `examples/export/` | a conformant export fixture: what the shapes were written for |
| `examples/negative/` | fixtures that must FAIL, so the checks are known to bite |
| `queries/production-expectations.json` | per-query floors and exemptions for production mode |
| `scripts/validate_shapes.py` | runs the shapes over a data file, or the examples union |
| `scripts/extract_qudt_subset.py` | regenerates the QUDT subset from an upstream checkout |
| `scripts/run_competency.py` | runs the competency queries against checked-in expected results |
| `scripts/generate_verification_data.py` | regenerates the synthetic calibration dataset (deterministic) |
| `scripts/generate_diagram.py` | builds the interactive map from the modules |
| `viz/` | the map's frontend: HTML, CSS, and four small JS modules |
| `queries/` | competency questions as SPARQL, with `.expected` results |
| `docs/design-notes.md` | why terms sit where they do, and what is still unresolved |

Namespaces are `https://w3id.org/forecast-market-ontology/{core,weather,kalshi}#`. These are deliberately
non-resolving: the ontology has no external consumers, so `src/catalog-v001.xml` handles
resolution locally and registering w3id redirects would buy nothing. Tools that want to
dereference the IRIs need the catalog, which Protégé and ROBOT both pick up automatically.

## Usage

```bash
make setup                           # poetry install, plus robot.jar if it is missing
make validate                        # structure, BFO grounding, unit coherence, docs
make cq                              # competency questions 1, 2, 4, 5, 6, 7, 8 as SPARQL
make validate-negative               # prove the checks catch what they claim to
make meta                            # tests about the checks: none may pass with nothing to check
make shapes                          # SHACL: does the data satisfy the export contract?
make shapes-negative                 # tests about the shapes: vacuity, required-property mutants, dead constraints
make export-check                    # production CQ mode: export passes, mismatch fails
make reason                          # HermiT consistency (needs robot.jar)
make axioms                          # every axiom pinned by a case, or exempt with a reason
make signatures                      # per-term semantic digests, for downstream pinning
make diagram                         # build/ontology.html, the interactive map
make test                            # all of the above, plus the competency check
```

## The map

`make diagram` writes `build/ontology.html`: every class, the subsumption
skeleton, and the object properties that join them, on one pannable field. It is
one self-contained file with no dependencies and no network calls, so it opens by
double-clicking and survives being emailed to someone. The build drops the webfont
links `viz/index.html` uses in development; the built file renders on the system
stack `style.css` falls back to rather than blocking on a font server.

Selecting a term shows its definition, its scope note, what it connects to, the
literal values it carries, and the Turtle stanza it is actually declared in — the
axioms, not a summary of them. Datatype properties end at a literal, so there is no
far class to draw an edge to; they are listed on the class that carries them, with
the type they land in, rather than left off the map entirely.

The `ThermalEdge export` chip cuts the map down to the export profile: the classes
`shapes/thermaledge-export.ttl` names and the properties it walks stay lit, and
everything else dims to the ground it was cut from. Classes an edge merely lands on
light too, or a relation would draw at full strength into a dimmed dot — but the
panel calls those *reached*, not constrained, because `fm:hasSubject` ranges over
`fm:ObservationTarget` while the shape narrows it to `wx:WeatherObservationTarget`,
and naming the range would name the wrong class.

The profile is read off the shapes rather than restated in the generator, so a shape
that starts naming a new class or walking a new path lights that term up on the next
build. It reads `sh:targetClass`, `sh:class` and `sh:path`; a shape reaching for a
targeting construct the reader does not handle fails `diagram-check` rather than
quietly shrinking the profile.

Colour follows the ontology's central claim rather than the namespace list: `wx`
is the forecast side, `ksh` is the market side, `fm` is the pivot both point at,
and borrowed BFO ground is held back in grey.

The frontend is `viz/` — `index.html`, `style.css`, and four JS modules that split
by job (`layout` places nodes, `graph` draws, `ui` is the chrome, `main` wires
them). `generate_diagram.py` writes `viz/src/data.js` and inlines the rest; to
change the map, edit `viz/` and rebuild. Open `viz/index.html` directly to work
against the last generated data without a build step.

`make diagram-check` runs in `make test`. It asserts every minted class still
resolves to a Turtle stanza, that every object property with a declared domain and
range still draws an edge, that every class carrying a datatype property is on the
map, that the set of deliberately domain-less ones has not grown, that every term the
export shapes name or walk reaches the map, that the pivot edges above survive, and
that the built file fetches nothing — because a viewer that silently drops half the
graph still renders a convincing picture.

Python deps are managed by poetry (`pyproject.toml`); every target runs through
`poetry run`. ROBOT comes from `$ROBOT_JAR`, a `robot.jar` in this directory, or `robot` on
`PATH` — `make setup` downloads it if none of those exist, but it needs a JRE
(`brew install openjdk`). Reasoner steps skip with a notice if ROBOT or Java is absent; the
Python checks always run.

To open in Protégé, open `src/fmo.ttl` — the catalog next to it resolves the imports.

## The three decisions that shape everything

**1. A Kalshi "event" is not an event.** Kalshi's API calls its middle tier an `event`. It is
not a BFO occurrent — it is a listing, an information content entity grouping the markets that
partition one observation target. The weather is the occurrent; the API row is a document about
it. The class is named `ksh:EventGrouping` to keep these apart, with `skos:altLabel "event"`
preserving the source term. Conflating the two is the easiest way to build something that looks
right and reasons wrongly.

**2. Propositions, not aboutness.** Forecasts concern the future, so the quality instance a
forecast "is about" does not exist when the forecast is issued. Asserting `fm:isAbout` would
commit to a relatum that isn't there. Instead a `fm:Proposition` is *composed* — a subject
(observation target), a comparator, threshold values — and acquires a truth value only when an
evaluation process consults the authoritative record. `fm:isAbout` exists but is reserved for
entities that actually exist.

**3. The observation target carries the protocol.** "The high temperature" is not one quantity.
It depends on the station of record, the interval boundaries, and the rounding rules. So
`wx:WeatherObservationTarget` names a variable, a *site* (not a station — the site persists when
the instrument is replaced), a temporal interval, and a `wx:MeasurementProtocol`. Two targets
differing in protocol are different targets, and may legitimately disagree.

The consequence worth knowing: the NWS climatological day runs local **standard** time midnight
to midnight all year, so in summer it runs 01:00 to 00:59 local clock time. The example writes
the boundary instants out explicitly rather than leaving them implied by a date.

`wx:alternativeDeterminationOf` relates two targets that are meant to capture the same physical
quantity under different protocols. It licenses nothing — no query may substitute one for the
other — and exists so the relationship is sayable and, more to the point, checkable: the
validator fails when a forecast scores one determination while the market settles on another.
The worked example carries both, and they disagree, 83 against 82.

The decision earned its keep on 2026-08-14, when Kalshi moved its daily temperature series from
the NWS to **The Weather Company** — same site, same variable, same day boundary, different
publishing authority. Under the protocol rule that is a different observation target and so a
different proposition, which is the correct answer: a KXHIGHNY series spanning that date is two
time series, not one, and averaging across it would be a category error. The worked example is
dated 15 August 2026 and settles on The Weather Company accordingly.

## Units

`fm:hasUnit` points at a [QUDT](https://github.com/qudt/qudt-public-repo) unit individual —
`unit:DEG_F`, not `"degree Fahrenheit"`. Only a 16-unit subset is vendored, generated by
`scripts/extract_qudt_subset.py`; QUDT proper is ~74k triples and importing it to use sixteen
units would swamp everything else.

QUDT makes no upper-level commitment, so `core.ttl` grounds `qudt:Unit` under
`fm:MeasurementUnit` and `qudt:QuantityKind` under `fm:Designation`. Without that they float
under `owl:Thing`, which the validator now checks for explicitly.

Checking uses two strengths, because there are two questions:

- Where values get **compared** — a proposition's threshold against its target, a datum's
  reading against the target it reports for — units must be *identical*. Dimensional
  compatibility is not enough: 82 °F against a target in °C shares a dimension vector and is
  still a bug.
- Where a unit is merely **chosen** for a variable, only the QUDT dimension vector has to
  match, since a target may use a valid unit that is not on the conventional list.

Dimension equality is necessary, never sufficient. Snowfall depth and liquid precipitation are
both lengths; percent and degrees are both dimensionless. This catches unit mistakes, not
quantity confusions.

One trap worth naming, because it bit during this work: `wx:conventionalUnit` is deliberately
**not** a sub-property of `fm:hasUnit`. `hasUnit` is functional, so making a multi-valued
property a sub-property of it would infer all four wind-speed units identical — quietly
identifying knots with metres per second. The `owl:AllDifferent` block in `core.ttl` turns that
mistake into a HermiT inconsistency instead of a wrong answer; the guard is verified to fire.

## Validation

`scripts/validate.py` checks parsing, that every minted term reaches `bfo:entity` by
`rdfs:subClassOf`, that bridged external classes are grounded too, that nothing is both
continuant and occurrent, that examples use only declared properties and reference only
individuals that exist, that a forecast scores the same target the market settles on, unit
coherence, and documentation coverage. Stored derived values are checked against what they are
derived from: `wx:leadTimeHours` against issuance and interval start, and a `fm:SkillScore`
under `fm:BrierScore` against the probability it scores and the outcome it was scored against. A
score resting on a superseded record fails — scoring against a retracted value is the specific
mistake `fm:scoredAgainst` exists to make visible. At most one truth assessment per proposition
may rest on a record nothing supersedes — two live assessments make calibration double-count the
proposition rather than contradict it, and every other check would stay green while it happened.
A market must express a proposition about the same target its grouping covers, so a market cannot
silently drift onto a different target than the one its grouping ladder was built for. Every
observation target must name exactly one measurement protocol, and the protocol its settlement
source publishes under must be the one its proposition's target names — the open-world assumption
reads a missing protocol as unnamed rather than absent, so the reasoner cannot catch either, and a
source disagreeing with its target is the 2026-08-14 migration as a modelling error. A match must
output one yes lot and one no lot of equal quantity, and a payout must name one resolution and one
lot of contracts, in the same market, on the side that resolution determined, held by the party
whose obligation it realizes, for one dollar a contract — paying the losing side is the
trading-layer form of the mistake `fm:scoredAgainst` exists to expose, arithmetically
self-consistent and resting on the wrong determination, and paying the right amount to the wrong
party is the same mistake about the other end of the transfer. Every term `CONTEXT.md` names in
backticks must still be declared, since nothing else reads that file and a rename would leave the
vocabulary pointing at a term that no longer exists. `make
reason` adds HermiT consistency and re-derives `ksh:WeatherMarket` from a weakened assertion to
prove the defined class actually fires.

`make cq` runs the competency questions in `queries/` and diffs the results against checked-in
`.expected` files. **An empty result set fails** — a query matching nothing is how a broken
competency check looks like a passing one, and that rule caught CQ1 on its first run (SPARQL
does no subclass reasoning, so `?m a ksh:Market` missed an individual typed `ksh:WeatherMarket`;
the queries now use `a/rdfs:subClassOf*`).

`make shapes` asks a different question from `make validate`. The validator checks the
ontology's own integrity and takes no data; the shapes check whether a *dataset* satisfies
the contract a downstream consumer relies on — every market expressing exactly one
proposition, every target naming a protocol, every probability inside 0..1. OWL cannot
do this job: `ksh:Market` asserts `owl:cardinality 1` on `ksh:expressesProposition`, but
under the open-world assumption a second value is not a violation, it is an inference that
the two are the same individual. SHACL closes the world and rejects it.

`examples/export/` holds a conformant export and `examples/negative/` one that must fail.
Both sit outside the `examples/*.ttl` glob, so `validate.py` and fixture-mode `make cq`
never load them: they are data under test, not worked data. The positive fixture matters
because the repo's own examples are a *superset* of any export — they carry the sites, day
boundaries and model runs an export omits — so conformance there showed only that the
shapes were satisfiable by something richer than the thing they describe.

`make export-check` runs production CQ mode both ways: the export fixture must pass and the
target-mismatch fixture must fail. In production mode a query with no entry in
`queries/production-expectations.json` fails, which keeps "empty is a failure" the default
and makes every exemption a visible edit with a stated reason. Only CQ2 and CQ4 are floors:
CQ1 needs `wx:atSite` and the day's boundary instants, which an export does not carry, so it
is a fixture-mode question rather than a production one.

The shapes run over the examples as one graph, because the example files import each other
— checked alone, the correction and bracketset files report a target with no protocol and
propositions whose subjects have no type, none of which is real. Negative tests in
`scripts/test_validate.py` prove the shapes reject a stripped protocol, an out-of-range
probability, a market with two propositions, and several defects on export-shaped data.

Two rules came out of writing them, and both cost a shape that could not fail:

**A shape that matches no focus node conforms.** `teh:MarketShape` targeted
`ksh:WeatherMarket` and `teh:ProbabilityShape` targeted `fm:ForecastProbability` and
`fm:MarketImpliedProbability`. rdfs inference types a subclass instance as its parent,
never the reverse — so an export typing markets as plain `ksh:Market`, or probabilities
as `fm:ProbabilityAssignment`, matched nothing and conformed: a market with no
proposition and no ticker, and a probability of 7.41. Both now target the parent class.

**`sh:class C` is dead on a property whose `rdfs:range` is already `C`.** The shapes run
with `inference="rdfs"`, so range entailment types the object before SHACL looks. The
class constraints on `wx:underProtocol` and `fm:assignsProbabilityTo` could never fire,
and a dangling protocol IRI conformed. A bad protocol is caught instead by requiring
`fm:statedAs` — a literal that entailment cannot fabricate.

`make shapes-negative` (`scripts/test_shapes.py`) mechanically enforces the second rule
in full, plus only the vacuity half of the first: every shape is required to match at
least one focus node in each export fixture. It does not enforce that a shape's
`sh:targetClass` is pitched at the right level of generality — a shape targeting a
subclass narrower than the data conforms vacuously the same way a dead shape does, and
nothing in the mutant matrix can tell that apart from a target that is correctly
specific, because both produce a passing run. That half of the rule rests on the
hand-written cases in `scripts/test_validate.py`.

`make shapes-negative` also proves a third property no one wrote by hand: every shape's
`sh:minCount` properties are mutated directly from the shapes graph — retype a shape's
focus nodes to its own `sh:targetClass`, drop one required property, and require a
violation attributed to that shape. Retyping alone can't prove a shape still fires: the
export fixture is valid, so it conforms whether or not a shape matched it at all, which
is why a mutant must retype *and* break something. The violation must be a `sh:minCount`
one from that exact property shape: the mutant retypes as well as deletes, so any other
constraint firing would otherwise be credited to the property that was dropped.

The size of that matrix is itself an assertion. `EXPECTED_ASSERTIONS` in `test_shapes.py`
is checked in like a CQ `.expected`, because dropping an `sh:minCount` from the export
contract shrinks the matrix by one and a suite that only *prints* its count still reports
success. Focus nodes are counted under the same `inference="rdfs"` that `make shapes`
runs, and only among nodes the fixture itself contributes — an export may leave a
probability untyped and let `rdfs:domain` supply the class, and the two runs have to
agree about that.

`scripts/test_validate.py` is the part that makes the rest trustworthy: it injects each defect
the checks claim to catch into a throwaway copy and asserts they fail with the right message.
A checker nobody has watched fail is not known to work — the first version of the unit check
passed a Celsius-vs-Fahrenheit mismatch silently, and only the negative test exposed it.

`make meta` checks the checks. Every traversal reports how much it covered, and a
traversal that covered nothing has proved nothing — so `scripts/test_meta.py` calls
each check with the schema and no example data and requires every one of its
coverage counts to be zero and to have failed. Those guards were written by hand,
one per traversal, until the one for lead times was never written; a rule enforced
by memory is enforced wherever someone remembered. The assertion is on the coverage
log rather than on "did the check fail somehow", which any unrelated guard satisfies.

The checks have caught real bugs at every stage: four classes floating under `owl:Thing`; an
`InformationBearingEntity` axiom using `concretizes` where BFO requires `is carrier of`, making
the class unsatisfiable; and the functional-sub-property trap above. Run them.

The definedness check is the newest and was added after a miss rather than before one. Renaming
a protocol individual during the Weather Company migration left the synthetic dataset pointing
at an IRI that no longer existed, for all 40 days, and everything stayed green — a dangling IRI
is legal RDF that reads as an untyped resource. The targets silently lost their protocol, which
in an ontology whose central rule is that the target carries the protocol is the worst available
place to lose one.

## What holds the checks honest

Two failures of the same shape shipped in one afternoon: an `owl:AllDisjointClasses`
block whose deletion left every test green, and a union axiom whose test named a
mistake the axiom does not catch. Both read in the prose as guarantees. Neither was
one. The ontology's job is to stop exactly that from happening downstream, so it does
not get to do it itself.

`make axioms` enumerates every axiom in the minted modules — 68 of them — and requires
each to be either **pinned** by a reasoner case or **exempt** with a stated reason in
`queries/axiom-expectations.json`. Adding an axiom fails the build until it is one or
the other. The `pinned` claims are not taken on trust: the checker deletes each pinned
axiom and confirms its case stops firing, because a ledger asserting an unverified
relationship is the original bug wearing the ledger's clothes.

The honest current number is **9 pinned, 59 exempt**. Most of the ontology's axioms are
asserted and untested — the exemptions say why, and most say that the constraint cannot
fail under the open-world assumption and is enforced for data by SHACL instead. That
ratio is now visible rather than assumed, which is the point;
`scripts/check_axioms.py --discover` re-derives it by deleting each axiom in turn and
running every case against the result.

`make signatures` addresses the same failure at the downstream boundary. ThermalEdge
borrows FMO's terms and pins them by the digest of `skos:definition`, which catches a
reworded definition and nothing else: both cardinality restrictions can be deleted from
`ksh:Market` — the axiom this README cites as the reason SHACL is needed — with its
definition untouched, and the pin still reports every term matching. `semantics_sha256`
digests the label, definition, scope notes, parents and axioms together, so it moves
when the commitments move. A consumer tracking prose keeps pinning `definition_sha256`;
one whose inferences depend on the axioms pins the semantic one.

## Open questions

Flagged rather than silently decided:

- **Unit conversion is unimplemented.** Units are checked, not converted. A proposition in
  °F over a target in °C is rejected rather than reconciled, which is right for now — silent
  conversion is worse than a refusal — but ingesting a source that reports Celsius will need
  a conversion step. QUDT carries the factors (`qudt:conversionMultiplier`,
  `qudt:conversionOffset`) in the vendored subset, so the data is there; nothing uses it yet.
- **Scalar markets are unmodelled.** Kalshi's `market_type` is `binary` or `scalar`, and
  `result` can be `scalar`. `ksh:Market` asserts `owl:cardinality 1` on `expressesProposition`,
  which quietly assumes binary: a scalar market settles to a number, not to the truth of one
  proposition. `ksh:ResolvedScalar` exists so the outcome enumeration matches the API's, but
  nothing else accommodates the case.
- **Prices are typed decimal but not gridded.** `ksh:lastPriceCents` and the bid/ask properties
  are decimal because most Kalshi markets now quote in tenths of a cent or finer. Which prices
  are *valid* is per-market, given by the API's `price_ranges` bands; nothing here represents
  that grid, so an off-tick price is expressible.
- **Status over time.** `ksh:hasStatus` is functional and treated as current status. Modelling
  status history needs either snapshot individuals or BFO's temporalized-relations profile.
- **Corrections after settlement.** A correction to the settlement source can contradict a
  settled market. `wx:ReportCorrection` and `wx:supersedes` record the divergence, but nothing
  yet says which value is authoritative for which question. It depends on the question, which
  is the point.
- **Price to probability.** `ksh:PriceToProbabilityDerivation` is a process with a quote as
  input so the transformation stays auditable, but no derivation is specified. Naive
  `price/100` ignores spread, fees, and carry.
- **Tropical cyclones as processes.** Defensible and contested; see `docs/design-notes.md`.
- **The trading layer is thin, but no longer unexercised.** Through 0.7.1 these classes had
  no instance in any example and no competency question asked about order flow. Writing
  `examples/kxhighny-2026-08-15-trading.ttl` showed why the gap had persisted: the
  vocabulary could not express an order at all — no side, no action, no quantity, no limit
  price — so the classes were unusable rather than merely unused. 0.8.0 adds those
  properties, one worked match with both counterparties, CQ8, and a validator check that a
  payout pays the winning side what it owes. What is still unproven is breadth: one market,
  one match, no partial fills, no cancellations, no multi-trade position. `validate.py`
  reports the instantiated-class count on every run so the gap stays
  visible. It prints two figures: the direct count is the one that tracks this gap,
  since a class nothing can instantiate stays in it; the subclass-closure count is
  higher only because abstract parents are exercised through their children.
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
  remain contested on their own terms (`docs/design-notes.md`). Of the weather
  module's classes, 30 had no direct instance at 0.9.0. The rain example directly
  instantiates three of them — `wx:Rainfall`, `wx:PortionOfPrecipitate`,
  `wx:PrecipitationDepth` — and reaches `wx:PrecipitationProcess` only through
  `wx:Rainfall`'s subclass closure, not directly. 27 weather-module classes still
  have no direct instance, and 23 of those aren't reached even through a subclass.
  Whether the rest earn their place is open.
- **Bracket exhaustiveness is unchecked.** The validator refuses overlapping brackets in a
  grouping asserted mutually exclusive, but cannot tell whether they leave a gap: the
  KXHIGHNY ladder tiles the line only because the protocol reports whole degrees, which is
  stated in the protocol's prose and nowhere in the model. Checking for gaps needs a
  reporting increment on `wx:MeasurementProtocol`. Until then a ladder with a hole in it
  passes, and CQ5 reports the undershoot as a possible arbitrage.

## License

Ontology files: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
Vendored BFO retains its own license — see `src/imports/BFO-README.md`.
