# Wantology

An ontology relating **weather forecasts** to the **Kalshi prediction markets** listed on
them, built on [Basic Formal Ontology 2020](https://github.com/BFO-ontology/BFO-2020)
(ISO/IEC 21838-2).

Status: **0.5.0.** Consistent under HermiT, structurally validated, unit-checked against QUDT.
All seven competency questions are mechanically tested. Term coverage is deliberately shallow in places; see
[Open questions](#open-questions).

## What it is for

A weather forecast and a weather market are two agents' beliefs about the same future fact.
Comparing them is the whole point — that gap is the tradeable signal — but comparing them
naively goes wrong, because "the high in NYC on Friday" means slightly different things to
the NWS and to an exchange's settlement rules.

This ontology makes the comparison well-formed by giving both sides a shared pivot:

```
   wx:ProbabilisticForecast                    ksh:Market
      (GEFS 06Z run)                    (KXHIGHNY-26AUG15-B82.5)
            |                                       |
   has part |                                       | expressesProposition
            v                                       v
  wtl:ForecastProbability  ---------------> wtl:Proposition <--------------- wtl:MarketImpliedProbability
        P = 0.52            assignsProbabilityTo    |    assignsProbabilityTo         P = 0.60
                                                    | hasSubject                  (derived from a quote)
                                                    v
                                        wx:WeatherObservationTarget
                                     (max air temp @ Central Park site,
                                      over climatological day 2026-08-15,
                                      under the NWS CLI protocol)
```

Both probabilities point at **the same `wtl:Proposition` individual**, so subtracting them
means something. Nothing else has to line up — not tickers, not station names, not dates.

## Layout

| Path | Contents |
|---|---|
| `src/core.ttl` | `wtl:` — information content entities, propositions, probability, agents |
| `src/weather.ttl` | `wx:` — atmosphere, qualities, weather processes, observation, forecasting |
| `src/kalshi.ttl` | `ksh:` — series, event groupings, markets, contracts, trading, settlement |
| `src/wantology.ttl` | top module; imports all three |
| `src/imports/bfo-core.ttl` | vendored BFO 2020 core, unmodified |
| `src/imports/qudt-subset.ttl` | 16 units + 10 quantity kinds extracted from QUDT (generated) |
| `src/catalog-v001.xml` | OASIS catalog so imports resolve offline |
| `examples/` | worked data: one bracket end-to-end, the full ladder, a correction, 40 synthetic days |
| `scripts/validate.py` | structural, grounding, and unit checks (no Java needed) |
| `scripts/test_validate.py` | negative tests proving the validator fails when it should |
| `scripts/extract_qudt_subset.py` | regenerates the QUDT subset from an upstream checkout |
| `scripts/run_competency.py` | runs the competency queries against checked-in expected results |
| `scripts/generate_verification_data.py` | regenerates the synthetic calibration dataset (deterministic) |
| `queries/` | competency questions as SPARQL, with `.expected` results |
| `docs/design-notes.md` | why terms sit where they do, and what is still unresolved |

Namespaces are `https://w3id.org/wantology/{core,weather,kalshi}#`. These are deliberately
non-resolving: the ontology has no external consumers, so `src/catalog-v001.xml` handles
resolution locally and registering w3id redirects would buy nothing. Tools that want to
dereference the IRIs need the catalog, which Protégé and ROBOT both pick up automatically.

## Usage

```bash
pip install rdflib
python3 scripts/validate.py          # structure, BFO grounding, unit coherence, docs
make cq                              # competency questions 1, 2, 4, 5, 6, 7 as SPARQL
make validate-negative               # prove the checks catch what they claim to
make reason                          # HermiT consistency (needs robot.jar)
make test                            # all of the above, plus the competency check
```

`make` picks up ROBOT from `$ROBOT_JAR`, or `robot` on `PATH`. Get it from
[ontodev/robot](https://github.com/ontodev/robot/releases). Reasoner steps are skipped with a
notice if ROBOT is absent; `validate.py` always runs.

To open in Protégé, open `src/wantology.ttl` — the catalog next to it resolves the imports.

## The three decisions that shape everything

**1. A Kalshi "event" is not an event.** Kalshi's API calls its middle tier an `event`. It is
not a BFO occurrent — it is a listing, an information content entity grouping the markets that
partition one observation target. The weather is the occurrent; the API row is a document about
it. The class is named `ksh:EventGrouping` to keep these apart, with `skos:altLabel "event"`
preserving the source term. Conflating the two is the easiest way to build something that looks
right and reasons wrongly.

**2. Propositions, not aboutness.** Forecasts concern the future, so the quality instance a
forecast "is about" does not exist when the forecast is issued. Asserting `wtl:isAbout` would
commit to a relatum that isn't there. Instead a `wtl:Proposition` is *composed* — a subject
(observation target), a comparator, threshold values — and acquires a truth value only when an
evaluation process consults the authoritative record. `wtl:isAbout` exists but is reserved for
entities that actually exist.

**3. The observation target carries the protocol.** "The high temperature" is not one quantity.
It depends on the station of record, the interval boundaries, and the rounding rules. So
`wx:WeatherObservationTarget` names a variable, a *site* (not a station — the site persists when
the instrument is replaced), a temporal interval, and a `wx:MeasurementProtocol`. Two targets
differing in protocol are different targets, and may legitimately disagree.

The consequence worth knowing: the NWS climatological day runs local **standard** time midnight
to midnight all year, so in summer it runs 01:00 to 00:59 local clock time. The example writes
the boundary instants out explicitly rather than leaving them implied by a date.

## Units

`wtl:hasUnit` points at a [QUDT](https://github.com/qudt/qudt-public-repo) unit individual —
`unit:DEG_F`, not `"degree Fahrenheit"`. Only a 16-unit subset is vendored, generated by
`scripts/extract_qudt_subset.py`; QUDT proper is ~74k triples and importing it to use sixteen
units would swamp everything else.

QUDT makes no upper-level commitment, so `core.ttl` grounds `qudt:Unit` under
`wtl:MeasurementUnit` and `qudt:QuantityKind` under `wtl:Designation`. Without that they float
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
**not** a sub-property of `wtl:hasUnit`. `hasUnit` is functional, so making a multi-valued
property a sub-property of it would infer all four wind-speed units identical — quietly
identifying knots with metres per second. The `owl:AllDifferent` block in `core.ttl` turns that
mistake into a HermiT inconsistency instead of a wrong answer; the guard is verified to fire.

## Validation

`scripts/validate.py` checks parsing, that every minted term reaches `bfo:entity` by
`rdfs:subClassOf`, that bridged external classes are grounded too, that nothing is both
continuant and occurrent, that examples use only declared properties, unit coherence, and
documentation coverage. `make reason` adds HermiT consistency and re-derives
`ksh:WeatherMarket` from a weakened assertion to prove the defined class actually fires.

`make cq` runs the competency questions in `queries/` and diffs the results against checked-in
`.expected` files. **An empty result set fails** — a query matching nothing is how a broken
competency check looks like a passing one, and that rule caught CQ1 on its first run (SPARQL
does no subclass reasoning, so `?m a ksh:Market` missed an individual typed `ksh:WeatherMarket`;
the queries now use `a/rdfs:subClassOf*`).

`scripts/test_validate.py` is the part that makes the rest trustworthy: it injects each defect
the checks claim to catch into a throwaway copy and asserts they fail with the right message.
A checker nobody has watched fail is not known to work — the first version of the unit check
passed a Celsius-vs-Fahrenheit mismatch silently, and only the negative test exposed it.

The checks have caught real bugs at every stage: four classes floating under `owl:Thing`; an
`InformationBearingEntity` axiom using `concretizes` where BFO requires `is carrier of`, making
the class unsatisfiable; and the functional-sub-property trap above. Run them.

## Open questions

Flagged rather than silently decided:

- **Unit conversion is unimplemented.** Units are checked, not converted. A proposition in
  °F over a target in °C is rejected rather than reconciled, which is right for now — silent
  conversion is worse than a refusal — but ingesting a source that reports Celsius will need
  a conversion step. QUDT carries the factors (`qudt:conversionMultiplier`,
  `qudt:conversionOffset`) in the vendored subset, so the data is there; nothing uses it yet.
- **Kalshi enums are unverified.** `docs.kalshi.com` was unreachable from the environment this
  was drafted in, so `ksh:MarketStatus` individuals and some field names come from search results
  and prior knowledge rather than the live schema. Terms at risk carry an `unverified` scope
  note. Check them against the API before relying on them.
- **Status over time.** `ksh:hasStatus` is functional and treated as current status. Modelling
  status history needs either snapshot individuals or BFO's temporalized-relations profile.
- **Corrections after settlement.** An NWS correction can contradict a settled market.
  `wx:ReportCorrection` and `wx:supersedes` record the divergence, but nothing yet says which
  value is authoritative for which question. It depends on the question, which is the point.
- **Price to probability.** `ksh:PriceToProbabilityDerivation` is a process with a quote as
  input so the transformation stays auditable, but no derivation is specified. Naive
  `price/100` ignores spread, fees, and carry.
- **Tropical cyclones as processes.** Defensible and contested; see `docs/design-notes.md`.

## License

Ontology files: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
Vendored BFO retains its own license — see `src/imports/BFO-README.md`.
