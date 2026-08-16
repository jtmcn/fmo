# Wantology

An ontology relating **weather forecasts** to the **Kalshi prediction markets** listed on
them, built on [Basic Formal Ontology 2020](https://github.com/BFO-ontology/BFO-2020)
(ISO/IEC 21838-2).

Status: **0.1.0, first cut.** Consistent under HermiT, structurally validated, one worked
example. Term coverage is deliberately shallow in places; see [Open questions](#open-questions).

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
| `src/catalog-v001.xml` | OASIS catalog so imports resolve offline |
| `examples/` | worked instance data |
| `scripts/validate.py` | structural checks (no Java needed) |
| `docs/design-notes.md` | why terms sit where they do, and what is still unresolved |

Namespaces are `https://w3id.org/wantology/{core,weather,kalshi}#`. These are deliberately
non-resolving: the ontology has no external consumers, so `src/catalog-v001.xml` handles
resolution locally and registering w3id redirects would buy nothing. Tools that want to
dereference the IRIs need the catalog, which Protégé and ROBOT both pick up automatically.

## Usage

```bash
pip install rdflib
python3 scripts/validate.py          # structure, BFO grounding, docs coverage
make reason                          # HermiT consistency (needs robot.jar)
make test                            # both, plus the defined-class competency check
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

## Validation

`scripts/validate.py` checks parsing, that every minted term reaches `bfo:entity` by
`rdfs:subClassOf`, that nothing is both continuant and occurrent, that examples use only declared
properties, and documentation coverage. `make reason` adds HermiT consistency and re-derives
`ksh:WeatherMarket` from a weakened assertion to prove the defined class actually fires.

Both caught real bugs during the first pass: four classes floating under `owl:Thing`, and an
`InformationBearingEntity` axiom that used `concretizes` where BFO requires `is carrier of`,
making the class unsatisfiable. Run them.

## Open questions

Flagged rather than silently decided:

- **Units are strings.** `wtl:hasUnit` takes a string. Fahrenheit and Celsius both appear in
  this domain, and inches and millimetres both appear for precipitation. This is the one real
  soundness gap in 0.1.0 — fix it before any arithmetic crosses unit systems, either with QUDT
  or with a local unit vocabulary in `wtl:`.
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
