# Using FMO in ThermalEdge

*Design note — 18 August 2026. Written against FMO 0.7.0 and the ThermalEdge prod
checkout at `~/Code/thermal-edge`.*

---

## 0. One thing to check before anything else

FMO’s README asserts that on **2026-08-14 Kalshi moved its daily temperature series
from the NWS to The Weather Company** — same site, same variable, same day boundary,
different publishing authority.

*Provenance caveat, since everything below leans on this:* the README's "checked against the
live API on 2026-08-17" line covers **field names and enumerations**, not the migration. The
migration is an unsourced assertion in the same document. Confirm it against Kalshi's
KXHIGHAUS series rules before acting on Phase 0.

ThermalEdge has not moved with it. `transform/seeds/dim_market_settlement.csv` is a single
row:

```
KXHIGHAUS,KAUS,nws_cli,CLI,daily_high,midnight_to_midnight_lst,America/Chicago,…
```

and `int_observations_daily_authoritative.sql` hardcodes `'nws_cli' AS settlement_source`,
with a comment saying "no consumer branches on it today."

If the KXHIGHAUS family did move, then since 14 August the strategy has been scoring
its forecast against the NWS CLI while the exchange settles on someone else — and
`int_forecast_pairs` / `model_performance` / the obs-conditional prior have been quietly
blending two different quantities into one time series. **This is an operational check to
run today, independent of any ontology work.** It is also the single cleanest illustration
of what the ontology is for, which is why it opens this document rather than sitting in a
footnote.

---

## 1. What ThermalEdge is missing, stated precisely

ThermalEdge and FMO are about the same thing from two directions. ThermalEdge
computes an edge: `p_model − p_market`. FMO exists to make that subtraction
well-formed, by insisting both numbers point at **the same `fm:Proposition` individual**.

Today, in ThermalEdge, they point at the same thing only *by string coincidence*:

| Link | How it is made today | Where |
|---|---|---|
| ticker → strike | regex `T(\d+)` on the title | `domain/market_models.py` |
| ticker → date | regex on the ticker | `parse_event_date_from_ticker` |
| ticker → station | prefix lookup in a 1-row CSV | `dim_market_settlement.csv` |
| station → forecast | Hive partition path | `weather/parquet_writer.py` |
| decision → settlement | `market_id` string join, later | `calibration.py` |
| decision → source document | not linked at all | `source_record_id` is dbt-only |
| day boundary | one global config string | `StrategyConfig.settlement_timezone = "America/Chicago"` |

There is no object anywhere in the system that means *"the maximum air temperature at the
Austin site over the climatological day of 15 Aug 2026, under the NWS CLI protocol."*
The ticker is standing in for it. That works exactly as long as one ticker means one thing
forever — the assumption the August migration would break, and one that has slipped before:
the retired `KXHIGHATX` prefix is still scattered through `web/api/forecast_accuracy/`,
`web/routes/dashboard.py`, `domain/forecast_accuracy.py` and `analytics/performance.py`
(as examples and comments rather than live lookups, but nothing distinguishes the two).

FMO’s three shaping decisions each close a specific hole here:

1. **The observation target carries the protocol.** Change the publishing authority and you
   have a *different target*, therefore a different proposition, therefore two time series
   — not one with a discontinuity.
2. **Propositions, not aboutness.** A forecast about Friday can't point at a quality that
   doesn't exist yet, so the proposition is composed (subject + comparator + thresholds) and
   acquires a truth value only when an evaluation process reads the authoritative record.
   That is precisely ThermalEdge's `[strike, strike+1)` predicate, given an identity.
3. **A Kalshi "event" is not an event.** `ksh:EventGrouping` is the ladder — the set of
   markets that partition one target, mutually exclusive and exhaustive. ThermalEdge has
   `MarketData.event_ticker` as a regex-derived string and nothing that treats the ladder
   as an object.

### Five failure classes, each with a live referent in the code

| # | Failure | Evidence in ThermalEdge | FMO term |
|---|---|---|---|
| F1 | Settlement source changes silently | `'nws_cli'` hardcoded; seed has no validity interval | `wx:MeasurementProtocol`, `wx:alternativeDeterminationOf` |
| F2 | Ladder coherence computed, then discarded | the projector's `renormalization_factor` reaches only `web/`; its ladder-coverage `out_of_grid_mass` is dropped; no market-side check exists at all | `ksh:EventGrouping`, `ksh:mutuallyExclusive` (CQ5) |
| F3 | Post-settlement correction rewrites history | `int_observations_daily_authoritative` ranks `amended > final > preliminary` and takes rn=1; `int_forecast_pairs` is incremental with a 5-day lookback, so a later amendment never reaches its `actual_high` | `wx:ReportCorrection`, `wx:supersedes`, `ksh:settlementValue` vs `fm:realizedValue` (CQ7) |
| F4 | Provenance not walkable | `trading_decisions` stores `market_data`/`weather_data` as opaque JSON + `reasoning` as prose; `source_record_id` exists in ten dbt models and **zero** Python files | settlement as `fm:EvaluationProcess` with a document input (CQ4) |
| F5 | Multi-city is a landmine | one seed row, one `dim_stations` row, `observation_stations` defaults to `KAUS`, one global `settlement_timezone` | per-target `wx:ClimatologicalDay` / `fm:overTemporalInterval` |

F5 is the near-term pragmatic one. The moment a second city is listed, a single
`settlement_timezone` string is wrong for it, and the climatological-day boundary (local
**standard** time midnight — 01:00–00:59 clock time in summer) has to become per-target.
`decide()`'s local-midnight gate — the one that stopped the 0-for-43 run — reads that
config field directly.

F2 is subtler than "missing", and worth stating carefully because the machinery is already
there. `KalshiHighTempBt2fProjector` *does* project per-degree buckets onto the event's
tickers and renormalize them to sum to 1. But:

- The `renormalization_factor` it returns travels only to `web/models.py` and
  `web/routes/adjustments.py` — the **display** layer. Nothing in `strategy/` gates on it.
  So a ladder that projects but sums badly is *recorded* and never *acted on*.
- Two different quantities share the name `out_of_grid_mass`, and only one of them is
  wired up. The KDE one (mass outside `threshold_range`) already reaches `strategy/`,
  where `data_quality.py` grades it ok/warn/fail and `decide()` puts it in the HOLD
  reasoning — that path is fine. The **projector's** ladder-coverage figure
  (`bucket_projection.py`) is discarded at both `projector.project(...)` call sites inside
  `_project_kalshi`: `kalshi_baseline, _, renorm_factor = …`. How much probability the
  *ladder* failed to cover is computed and dropped.
- The projection has five identity-`1.0` early returns — no `forecast_date`, no bucket
  convention or no tickers, an unregistered convention, no T-tickers. These are **not**
  silent: each also returns an empty bucket dict, so `decide()` HOLDs with a named reason
  ("missing projector bucket … refusing to price with 1-degree fallback"). Credit where
  due. The one that *is* silent is the sixth path, which isn't an early return:
  `raw_sum == 0` sets `renorm = 1.0` and passes the raw dict through, so a degenerate
  ladder yields a non-empty projection of zeros rather than a refusal.
- There is no market-side coherence check at all. CQ5 is that check, and it does not exist
  in ThermalEdge in any form.

And one live contradiction the ontology would refuse to hold: `domain/market_models.py`
states in its module docstring that "temperature markets represent EXACTLY one degree
Fahrenheit," with `get_temperature_range(strike) → [X, X+1)`; the live convention seeded as
`kalshi_high_temp_bt_2f` has **2-degree `B<n>.5` buckets plus two open tails**. Those are
two different partitions of the same target, both in the codebase, and nothing reconciles
them. Under the ontology each partition is a distinct set of propositions over one
`wx:WeatherObservationTarget`, and "these markets are mutually exclusive and exhaust the
target" becomes an assertion a validator can fail on rather than a docstring that has gone
stale.

---

## 2. Three depths of integration

### A. Vocabulary only

Adopt the distinctions in Python and dbt; emit no RDF. `ObservationTarget` becomes a real
frozen dataclass; the settlement seed gains protocol epochs; `EventGrouping` replaces the
`event_ticker` regex.

- **Cost:** low. One domain module, one seed migration, one Alembic migration.
- **Closes:** F5 fully, F1 partially.
- **Doesn't close:** F2, F3, F4 — nothing is *checked*, only better named.
- **Risk:** the distinctions rot. `settlement_source` is already a column that no consumer
  branches on; adding more unenforced structure produces more of the same. The ontology's
  value is that a validator fails, not that a name is right.

### B. Offline conformance layer  ← recommended

RDF is a **build artifact**, never a runtime store. ThermalEdge keeps its Polars/DuckDB hot
path untouched and exports a day's decisions, quotes, settlements and forecasts as Turtle.
FMO’s existing `validate.py` and `queries/*.rq` run against that export in CI and
nightly.

- **Cost:** medium. An IRI-minting module, an exporter, a SHACL contract in FMO, a CI
  job. No change to `decide()`'s latency or dependencies.
- **Closes:** all five. F2/F3/F4 become *alerts* rather than modelling exercises — CQ2
  returning empty means the join broke; CQ7 returning a row means a correction contradicts
  a settled market.
- **Why it fits:** the checks that matter here (did the ladder cohere, did settlement match
  what we scored, did a correction land) are all *after the fact* by nature. Nothing is lost
  by running them out of band, and the operational risk of the in-band version is real —
  see C.

### C. RDF in the decision path

pyoxigraph alongside TimescaleDB/DuckDB; `decide()` resolves the proposition IRI live and
SPARQL runs in-cycle.

- **Gets you:** identity enforced at write time. A mismatched target becomes impossible
  rather than detectable.
- **Costs, specific to this system:** another store in the hot loop of a service whose
  CLAUDE.md documents a DuckDB lock incident that HOLDed *every* market, and whose reader
  and writer retry budgets (9 × 1.5s vs 12 × 5s) are already sized against each other with
  no slack. Adding a per-cycle SPARQL budget to that is a change with an incident attached.
- **And the ontology isn't ready to carry it.** Its own open questions — unit conversion
  unimplemented, scalar markets unmodelled, price→probability underspecified
  (`ksh:PriceToProbabilityDerivation` is a process with no derivation) — are exactly the
  parts `decide()` would need. Naive `price/100` is what the ontology explicitly declines
  to bless, and it is what ThermalEdge does today.
- **Verdict:** not now. B is a strict prerequisite anyway — you cannot put RDF in the hot
  path before you know the export is well-formed.

**Recommendation: B, reached through A.** Phases 1–2 below are A and are worth shipping on
their own merits even if the RDF never arrives.

---

## 3. What changes, concretely (option B)

### New in ThermalEdge

**`thermal_edge/domain/semantics.py`** — pure IRI minting, zero external dependencies, so it
sits legally in the Domain layer:

```python
def mint_target_iri(family: str, day: date, protocol_epoch: str) -> str: ...
def mint_proposition_iri(target_iri: str, comparator: str,
                         floor_value: float, cap_value: float) -> str: ...
```

Deterministic and readable — no hashes. A protocol change produces a visibly different
target IRI, which is the whole point.

> **Watch:** adding a package or moving code across layers means updating the seven
> import-linter contracts in `.importlinter`. `make lint-architecture` fails otherwise, and
> it runs in CI and pre-commit.

**`TradingDecisionRecord`** gains `proposition_iri` and `observation_target_iri` (indexed,
nullable, Alembic migration). This is the highest-leverage single change in the document:
it makes every decision joinable to its settlement and to the forecast that produced it
without JSON-blob spelunking, and it is useful immediately, before any Turtle exists.

**`strategy/calibration.py`** — the JSONL sample gains `proposition_iri`. Today the module
writes a 9-field row carrying no outcome at all, and says settlement outcomes "are joined
later via `market_id`." `market_id` is the ticker, and the ticker does not survive a protocol
change. Bucketing calibration by target-and-protocol instead of by ticker is the ontology's
core claim applied to the one place ThermalEdge most needs it — a calibration curve fitted
across 14 August is fitted across two quantities.

**`transform/seeds/dim_market_settlement.csv`** — gains `protocol_epoch_start`,
`protocol_epoch_end`, `target_iri_template`. Becomes multi-row per family:

```
KXHIGHAUS,KAUS,nws_cli,     …,2025-01-01,2026-08-14
KXHIGHAUS,KAUS,weather_co,  …,2026-08-14,
```

`int_observations_daily_authoritative.sql` then joins on the interval rather than
hardcoding the literal — which is what the existing comment already wishes were true.

**New dbt test** `assert_scoring_target_matches_settlement_target.sql` — fails the build
when a forecast pair's settlement source diverges from what the market family says for that
date. This is F1 caught at build time, and it is the dbt-side twin of the check
`scripts/validate.py` already performs on the examples.

**New CLI** `thermal-edge ontology export --date …` / `… verify --date …`
(Application layer, in `tools/` or `cli/`).

> **Watch:** the exporter must not hold an open DuckDB connection — read the parquet under
> `data/` directly or copy the DB first. A long-lived reader in the strategy service has
> already caused the lock incident once.

### New in FMO

**`shapes/thermaledge-export.ttl`** — SHACL saying what a valid ThermalEdge export looks
like: every `ksh:Market` has exactly one `expressesProposition`; every proposition has a
subject that is a `wx:WeatherObservationTarget` with an `wx:underProtocol`; every
`fm:ForecastProbability` and `fm:MarketImpliedProbability` `assignsProbabilityTo` a
proposition that exists. The contract lives in FMO because the ontology should own
the definition of conformance to itself.

**`scripts/run_competency.py`** — gains a `--data` flag so the CQs load an export instead of
(or alongside) `examples/`. Today `MODULES` plus the checked-in examples are hardcoded.

> **Watch: the "empty result fails" rule does not transfer to production data.** It is
> exactly right for fixtures — a query matching nothing is how a broken competency check
> looks like a passing one, and it caught CQ1 on its first run. Against live data, a quiet
> Sunday with no settlements legitimately returns zero rows for CQ4 and CQ7. Give each query
> a per-mode expectation (fixture: non-empty; production: a documented floor or an explicit
> may-be-empty) rather than relaxing the rule globally. Relaxing it globally is how the
> check stops working while still appearing to run.

**Version bump discipline** — per FMO’s CLAUDE.md, a bump touches `owl:versionIRI` and
`owl:versionInfo` in all four modules plus the README status line. Adding `shapes/` means
updating `MODULES` in `validate.py` and `run_competency.py`, `src/fmo.ttl`, and
`src/catalog-v001.xml`.

### What each competency question becomes operationally

| CQ | Today (fixtures) | As a ThermalEdge check |
|---|---|---|
| CQ2 probability gap | proves the join is well-formed | **empty ⇒ page.** The forecast and the market stopped pointing at the same proposition |
| CQ4 settlement provenance | walks the example chain | which document settled each market, and what it reported — the audit trail `trading_decisions` cannot produce today |
| CQ5 bracket coherence | sums the ladder | the market-side twin of `KalshiHighTempBt2fProjector`, which today only normalizes the *model* side. Pre-trade gate: market overshoot beyond the fee band means don't trust a single-rung edge; and the discarded `out_of_grid_mass` / silent-`1.0` paths become failures instead of defaults |
| CQ6a/b calibration | reliability table | replaces the ad-hoc JSONL fit, bucketed by target-and-protocol and by lead time |
| CQ7 correction contradiction | shows the divergence | **any row is an alert.** A correction has contradicted a market that already paid out — and your backtest is now scoring against a number nobody was paid |

CQ7 deserves emphasis. ThermalEdge has *one* column for the settled value and its
amendment-ranking logic overwrites it. FMO keeps `ksh:settlementValue` (what the
exchange applied) and `fm:realizedValue` (what is now authoritative) apart precisely
because they can diverge. Until ThermalEdge does the same, a backtest can silently score
against a value the market never paid.

The divergence is bounded but real, and the boundary is arbitrary: `int_forecast_pairs`
sets `unique_key`, so dbt upserts, and an amendment landing **within** the model's 5-day
lookback *does* propagate into `actual_high`. Outside that window it does not. So the
historical record is currently split by an incremental-materialization detail into a
recent stretch that silently tracks corrections and an older stretch that silently
doesn't — with nothing recording which is which. That is worse than either behaviour
chosen deliberately, and it is exactly the distinction the two properties make sayable.

---

## 4. Phasing

**Phase 0 — reconcile the settlement source.** Confirm against Kalshi's series rules
whether KXHIGHAUS moved to The Weather Company on 14 August — the FMO README asserts
it but does not source it. If it did, the calibration history and the obs-conditional prior
span two quantities and need splitting at that date. Independent of everything below; do it
first.

**Phase 1 — identity, no RDF.** `domain/semantics.py`; `proposition_iri` on
`TradingDecisionRecord` and on calibration samples. Ships value alone: decisions become
joinable to settlements without JSON spelunking.
*Accept when:* every new decision row carries a proposition IRI, and a calibration fit can
be grouped by target rather than by ticker.

**Phase 2 — protocol epochs.** Seed gains validity intervals; the authoritative-observations
model joins on them; the new dbt test fails on divergence.
*Accept when:* a synthetic mid-history source change fails `dbt build` with a named error.

**Phase 3 — export and conform.** `ontology export`; FMO’s SHACL shapes; CQ2/CQ4/CQ7
nightly against real exports.
*Accept when:* an injected mismatch (forecast target ≠ settlement target) makes CQ2 return
empty and the job fail, with the per-mode empty-result rule in place.

**Phase 4 — CQ5 as a live gate.** Ladder coherence checked pre-trade. Cheaper than it
looks, because the model half already exists: route the projector's
`renormalization_factor` and its ladder-coverage `out_of_grid_mass` out of the display
layer into `strategy/` and grade them the way `data_quality.py` already grades the KDE
figure; make the `raw_sum == 0` path a refusal rather than an identity; then add the
market-side sum. This is the first phase where the ontology influences a trade rather than
auditing one, and it should not be attempted before Phase 3 has been quiet for a while.

---

## 5. What I'd argue against

- **Putting pyoxigraph in the strategy cycle** (option C) until Phase 3 has run clean and
  the ontology's open questions — unit conversion, scalar markets, price→probability — are
  closed. The value in the near term is *catching mismatches*, and catching them offline
  costs nothing that matters.
- **Modelling the whole Kalshi surface.** `ksh:` already covers orders, positions, payouts
  and order-book snapshots. ThermalEdge doesn't need those in RDF; Postgres holds them
  fine. Export only what the competency questions consume.
- **Making the ontology a source of truth for numbers.** It should be the source of truth
  for *identity and protocol*. TimescaleDB, parquet and DuckDB stay authoritative for
  values — the hybrid split already in the architecture.
- **A "migration" framing.** Nothing migrates. FMO adds a layer that says what the
  existing numbers are *about*, and fails loudly when two of them turn out to be about
  different things.

---

## Sources

- `~/Code/fmo` — `README.md`, `CLAUDE.md`, `src/{core,weather,kalshi}.ttl`,
  `queries/cq0{1,2,4,5,6,7}*.rq`
- `~/Code/thermal-edge` — `CLAUDE.md`, `thermal_edge/strategy/{decide,calibration,config}.py`,
  `thermal_edge/domain/market_models.py`, `thermal_edge/database/trading_models.py`,
  `thermal_edge/constants.py`, `thermal_edge/settings.py`,
  `thermal_edge/weather/adjustments/{bucket_projection,obs_conditioned_estimator}.py`,
  `thermal_edge/data_service/weather_reader.py`,
  `transform/models/intermediate/int_observations_daily_authoritative.sql`,
  `transform/seeds/{dim_market_settlement,dim_stations}.csv`, `transform/seeds/schema.yml`
