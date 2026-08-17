# Design notes

Why terms sit where they do, what was rejected, and what is unresolved. Read alongside
`skos:scopeNote` annotations in the modules, which carry the short version.

## Upper-level commitments

BFO 2020 (ISO/IEC 21838-2), OWL core profile, vendored unmodified at
`src/imports/bfo-core.ttl` from the [BFO-2020 repo](https://github.com/BFO-ontology/BFO-2020).

Not used in 0.1.0:

- **The temporalized-relations profile.** BFO 2020 ships an extension for relations that hold
  at times. Most of what we assert is either atemporal (a market expresses a proposition, full
  stop) or naturally reified as a dated information content entity (a quote at a reference time).
  Adopt it when we need to say that a quality had a magnitude *at* an instant without inventing
  a datum for it.
- **The atemporal profile.** No reason to weaken yet.

Term IRIs use readable local names (`wx:AirTemperature`), not opaque numeric IDs. OBO convention
prefers opaque IDs so that labels can change without breaking references. That tradeoff is worth
it for ontologies with many downstream consumers and a curation team; here it costs legibility
for a benefit nobody is collecting. Revisit if the ontology is ever published for reuse.

## The naming collision that matters most

Kalshi's API tier is called `event`. BFO's `occurrent` branch is where events live. They are not
the same thing and the collision is actively dangerous, because a modeller who files
`ksh:Event` under `bfo:process` gets an ontology that parses, reasons, and is wrong.

A Kalshi event is a **listing**: a document published by an exchange, grouping the markets that
partition the possible values of one observation target. It is a generically dependent
continuant. You can copy it, version it, and take it down. The weather it concerns is the
occurrent, and the two are related only through the proposition.

Named `ksh:EventGrouping`, with `skos:altLabel "event"` so that a search for the source term
still lands on it.

The same reasoning puts `ksh:Series`, `ksh:Market`, `ksh:BinaryContract`, `ksh:Order`,
`ksh:Position`, and `ksh:Resolution` all under information content entity. Everything Kalshi's
API returns is a document. The processes — `ksh:Trade`, `ksh:MarketSettlement`, `ksh:Payout` —
are the things that actually happen, and they are separate.

## Aboutness and the future

The natural move is `Forecast isAbout <the high temperature on Friday>`. It fails. On Monday
there is no such quality instance to be about, and `isAbout` is an existentially committing
relation: asserting it puts the relatum in the domain of quantification.

Options considered:

1. **Relate to the temporal region instead.** The region exists (BFO temporal regions are not
   presentist), but "about Friday" is far too coarse — every forecast for every location shares it.
2. **Modal or possible-worlds machinery.** Out of scope for OWL DL, and overkill.
3. **Compose the proposition.** Chosen.

A `wtl:Proposition` has a `wtl:hasSubject` pointing at a `wtl:ObservationTarget` — itself an
information content entity, so it exists as soon as someone specifies it — plus a comparator and
threshold values. All of that exists at forecast time. The truth value is attached later by a
`wtl:EvaluationProcess` that consults the record. Absence of a truth value means undetermined,
not false.

This has a payoff beyond tidiness: it is exactly the structure Kalshi's own schema has
(`strike_type` with `floor_strike` and `cap_strike`), so market ingestion is close to mechanical,
and forecasts get bucketed into the same brackets by construction.

## Placements worth defending

**`wx:PortionOfAir` under `fiat object part`, not `object`.** BFO objects require causal unity.
A parcel of air has none: its boundaries are ours, and the molecules disperse within days. Fiat
object part is the honest home. `wx:Atmosphere` *is* an object — gravitational binding and
internal fluid dynamics supply the unity.

**Qualities inhere in the air, not in the station.** `wx:AirTemperature` inheres in a
`wx:PortionOfAir`. The station bears a `wx:MeasurementFunction`, realized in a
`wx:WeatherObservation` process, whose output is a datum. Three different entities, routinely
collapsed into "the temperature at KNYC."

**`wx:ObservingSite` is a `site`, so immaterial.** The site persists across instrument
replacement and relocation-within-tolerance, which is what settlement rules actually name. The
`wx:stationOfRecord` relation ties a site to whichever station is currently authoritative for it,
and can change.

**`wx:TropicalCyclone` under `process`.** A hurricane has temporal parts, a beginning and an end,
and no persisting portion of air composes it throughout — it is something the atmosphere *does*.
The named storm is the process; its track is the spatiotemporal region it occupies; its
category is a designation.

This is contested, and worth knowing why. Storms are also treated as material entities —
a rotating vortex you can point at on radar, with a boundary and an interior. The counterargument
to that view is that the "thing" is defined entirely by a pattern of motion, and patterns of
motion are processes. The counter-counterargument is that the same is true of a flame or a
whirlpool, and BFO does not obviously want those as processes either.

The practical consequence is small for us: market propositions about hurricanes are about
landfall, category, and named-storm counts, all of which route through observation targets and
designations rather than through the storm's own classification. If the process reading turns out
to obstruct something, it can be revised without touching the market side.

**`wtl:Designation` under information content entity, not quality.** Truth values, comparators,
market statuses, and resolution outcomes classify things that are themselves information content
entities. BFO qualities inhere only in independent continuants, so they cannot inhere in a
proposition. Designations are individuals in a controlled vocabulary rather than classes, which
keeps the ontology in OWL DL by avoiding punning.

**`ksh:ContractHolderObligation` under `role`, not `disposition`.** Dispositions are grounded in
the bearer's physical make-up. An obligation to pay is grounded in an institutional arrangement
external to the bearer. That is the textbook role/disposition line and this falls cleanly on the
role side.

## Units

Adopted QUDT in 0.2.0, replacing the `xsd:string` unit of 0.1.0. Sixteen units and ten quantity
kinds are vendored via `scripts/extract_qudt_subset.py`; QUDT proper is ~74k triples.

**Grounding.** QUDT makes no upper-level commitment, so `qudt:Unit` is asserted under
`wtl:MeasurementUnit` and `qudt:QuantityKind` under `wtl:Designation` in `core.ttl`. A unit is a
convention rather than a property of the world — the degree Fahrenheit does not inhere in
anything — so it is a generically dependent continuant, not a quality.

**Why dimension vectors and not quantity kinds.** The obvious compatibility check is
`qudt:unitForQuantityKind`, and it does not work. QUDT's links there are uneven: pressure units
link to `ForcePerArea` and not to `quantitykind:Pressure`; of the four wind-speed units only
`M-PER-SEC` links to `Speed`, the rest to `Velocity` and `LinearVelocity`; `PERCENT` links to
thirty-nine kinds, none of them `RelativeHumidity`. Every unit does carry exactly one
`qudt:hasDimensionVector`, consistently. So dimension vectors do the checking and quantity kind
is carried as documentation.

**Why identity and not just dimension where values are compared.** The first version of the
check compared dimension vectors everywhere and passed a °C threshold over a °F target in
silence — the exact mistake units were adopted to prevent, since °F and °C share a dimension.
Where two values are actually compared the units must be the same unit; same-dimension-different-unit
means a conversion is required and has not been recorded, which is worth failing on rather than
assuming. Only when choosing a unit for a variable does dimension alone suffice.

Dimension equality stays necessary but not sufficient. Snowfall depth and liquid-water-equivalent
precipitation are both lengths and would pass; percent and plane-angle degrees are both
dimensionless. Quantity confusions need the variable to be right, which is what
`wx:WeatherVariable` is for.

**The functional sub-property trap.** `wx:conventionalUnit` lists several units per variable.
Making it `rdfs:subPropertyOf wtl:hasUnit` — which looked tidy — would have been a serious bug:
`wtl:hasUnit` is functional, so every listed unit would be inferred identical, silently
identifying knots with metres per second and °F with °C. OWL does not assume named individuals
are distinct, so nothing would have complained. The `owl:AllDifferent` block over the vendored
units in `core.ttl` exists to turn that class of mistake into a HermiT inconsistency. Verified by
reintroducing the bug and confirming the reasoner reports it.

## Bugs the checks caught

Recorded because they are representative of what goes wrong, not for posterity.

**Four classes floating under `owl:Thing`.** `wtl:Comparator`, `wtl:TruthValue`,
`ksh:MarketStatus`, `ksh:ResolutionOutcome` were declared with individuals and definitions but no
`rdfs:subClassOf`. Everything parsed and nothing complained; they were simply not part of the
ontology in any load-bearing sense. Caught by the grounding check in `validate.py`. Fixed by
introducing `wtl:Designation`.

**`InformationBearingEntity` unsatisfiable.** It was defined as a material entity that
`concretizes` some information content entity. BFO 2020 gives `concretizes` the domain *process or
specifically dependent continuant*, so the intersection with material entity is empty. HermiT
flagged it; structural validation could not have. The correct relation is `is carrier of`
(BFO_0000101). The full BFO chain is: the information content entity *generically depends on* the
material carrier, and is *concretized by* a quality of that carrier or a process in it — never by
the carrier itself.

The lesson is that the structural checks and the reasoner catch disjoint classes of error, and
both are needed.

## Competency questions

A competency question is a requirement: a question the ontology must be able to answer, used to
fix scope and then to test it. If a question cannot be answered, a term or a relation is
missing. They are the difference between an ontology that earns its keep and a tidy taxonomy.

Each of 1 to 4 is now mechanically checked by `make test` and fails the build if it regresses.
Through 0.1.0 all four carried a tick mark on the strength of "you could query the example for
this", which was true and not the same as tested; only 3 had a real check. Made honest in 0.2.0.

| # | Question | Status |
|---|---|---|
| 1 | For a given market, what proposition does it express, and over what observation target? | `queries/cq01-market-proposition.rq` |
| 2 | Which forecast probabilities and market-implied probabilities target the same proposition, and what is the gap? | `queries/cq02-probability-gap.rq` |
| 3 | Which markets are weather markets? | `make competency` — inferred, so it needs a reasoner |
| 4 | What document settled this market, and what value did it report? | `queries/cq04-settlement-provenance.rq` |
| 5 | For a mutually exclusive event grouping, do the implied probabilities sum to one, and by how much do they overshoot? | `queries/cq05-bracket-coherence.rq` |
| 6 | Given a lead time, what is the historical calibration of a model against settled outcomes? | `queries/cq06a-...`, `cq06b-...` |
| 7 | Which settled markets were contradicted by a later correction to their settlement source? | `queries/cq07-correction-contradiction.rq` |

Questions 1, 2 and 4 are answered by SPARQL over the asserted graph; 3 needs OWL reasoning
because the answer is derived from the `ksh:WeatherMarket` equivalent-class axiom rather than
stated. That split is why there are two competency targets in the Makefile.

Two things learned wiring these up, both recorded because they generalise:

- **An empty result set must fail.** A query matching nothing is the most common way for a
  broken competency check to look like a passing one. `scripts/run_competency.py` treats zero
  rows as failure, and that rule caught CQ1 the first time it ran.
- **SPARQL does no subclass reasoning.** `?m a ksh:Market` does not match an individual asserted
  as `ksh:WeatherMarket`. The queries use `a/rdfs:subClassOf*` so they stay runnable against the
  raw graph without a reasoner in the loop. This is the same silent-underspecification failure
  as the missing `owl:equivalentProperty` axioms in the IAO analysis above: nothing errors,
  answers just quietly go missing.

Question 5 landed in 0.3.0 and needed no new terms, only a fuller example: the bracket ladder in
`examples/kxhighny-2026-08-15-bracketset.ttl`, since one market cannot overshoot. It reports

```
eventTicker       asOf                  markets  sumImplied  overshoot  bids  asks  arbitrage
KXHIGHNY-26AUG15  2026-08-15T12:00:00Z  4        1.04        0.04       96    110   none
KXHIGHNY-26AUG15  2026-08-15T18:00:00Z  4        1.02        0.02       94    108   none
```

Three things about that query generalise:

- **Grouping by snapshot time is load-bearing.** Quotes accumulate, so summing without binding
  one `?asOf` across both the quote and the implied probability adds noon prices to evening
  prices and yields a meaningless total that still looks like a number. The example carries two
  snapshots specifically so a regression here changes the answer instead of hiding.
- **The overshoot is not profit.** It is what the market charges for immediacy. Turning it into
  an arbitrage claim needs the ask side, so the query reports cents alongside probabilities and
  flags the degenerate cases — a ladder costing ≤ 100c for a guaranteed \$1, or selling for
  ≥ 100c against a \$1 liability. On real data those almost always mean stale quotes or a
  misparse, not free money.
- **`?marketCount` is the honest denominator.** The query only sums markets that have both a
  quote and an implied probability at that instant. A ladder missing a bracket undershoots and
  looks like an arbitrage, so the count has to be checked against the true bracket count.

Interpreting the overshoot as spread plus fee drag still needs a fee model, which does not exist
yet. Remaining:

Question 6 landed in 0.5.0, as two queries rather than one. `cq06a` is the reliability table —
observed frequency against mean forecast probability, per model, per lead time, per probability
bin. `cq06b` aggregates over bins, and is the one to quote:

```
model                 leadHours  n    meanForecast  baseRate  meanBrier  climatologyBrier  meanAbsError
vex:ModelCalibrated   24         160  0.25          0.25      0.134      0.188             0.245
vex:ModelCalibrated   72         160  0.25          0.25      0.159      0.188             0.314
vex:ModelOverconfident 24        160  0.25          0.25      0.154      0.188             0.234
vex:ModelOverconfident 72        160  0.25          0.25      0.165      0.188             0.292
```

Both models beat climatology, both degrade with lead time, and the overconfident one scores
worse at both leads despite seeing exactly the same underlying signal. That last difference is
purely the cost of overstating confidence.

Four things worth carrying forward:

- **Why two queries.** The reliability table is the classic presentation and the right shape for
  the question, but forty days spread across five bins leaves individual rows dominated by
  noise: the calibrated model shows a +0.192 gap in one mid bin on n=23, which is sampling
  error, not miscalibration. The aggregate rests on all 160 assignments per cell. Both are kept
  because the per-bin shape is what "calibration" means, and the aggregate is what is
  trustworthy at this sample size. `?n` is in the output of both so the reader can tell.
- **`meanAbsError` is in `cq06b` as a warning, not a second opinion.** It is not a proper
  scoring rule — it rewards stating extreme probabilities regardless of warrant — and in the
  checked-in result the overconfident model scores *better* on it (0.234 vs 0.245 at 24h) while
  scoring worse on everything honest. That inversion is the argument for Brier, and it is worth
  having in the output where someone will see it rather than in a footnote.
- **Lead time is a grouping key, never averaged over.** Pooling a 72-hour forecast with a
  6-hour one measures the mix of lead times in the sample rather than the skill of the model.
  Negative lead times — a same-day update to a daily maximum, which is routine — are real, get
  their own rows, and must not be folded in. The base example's GEFS forecast has a lead time of
  -4.667 hours and appears as its own n=1 row, which is honest rather than tidy.
- **The outcome must come from the current record.** After a correction a proposition carries
  two assessments with opposite values, so both CQ6 queries filter to assessments resting on a
  record nothing supersedes. Same guard as CQ7, applied for the opposite purpose. Without it,
  calibration would be scored against a value the record has retracted.

CQ2 already showed why lead time matters: it reports the forecast/market gap widening from 0.08
to 0.16 purely because the forecast is a stale 06Z run while the market kept moving. Calibration
work that does not control for forecast age measures staleness and reports it as skill.

## A statistics bug the machinery did not catch

The first version of `scripts/generate_verification_data.py` built its "calibrated" model by
drawing a noisy signal `mu = T + e` and then forecasting `Normal(mu, sigma)`. That is wrong, and
CQ6a said so immediately: the supposedly calibrated model over-predicted in every high bin, with
gaps up to +0.36.

The error is Bayesian rather than ontological. `T` has a climatological prior, so seeing `mu`
should shift belief *toward* climatology and *narrow* it. Forecasting `Normal(mu, sigma)`
over-predicts whichever bracket `mu` lands in. A 20,000-draw Monte Carlo put the naive
construction's gap at +0.17 in the high bins and the posterior construction's within 0.003 of
zero.

Worth recording for two reasons. First, it is a reminder that none of the validation in this
repo checks whether the *content* is right — the naive data was structurally perfect, unit
coherent, BFO conformant and reasoner consistent, and still described a model that was not what
it claimed to be. Second, the thing that caught it was the competency question itself: a query
built to detect miscalibration detected miscalibration, in the one place nobody was looking for
it. That is the argument for competency questions producing numbers a human reads rather than
booleans.
Question 7 landed in 0.4.0 and forced a real modelling change; see **Truth is not a property of
a proposition** below. It reports every market whose settlement document was later superseded,
with a verdict computed by re-evaluating the proposition's own comparator and thresholds against
the corrected value:

```
ticker                  settled  settlementValue  currentValue  implied  verdict
KXHIGHNY-26AUG15-B82.5  Yes      82               84            No       CONTRADICTED
KXHIGHNY-26AUG15-B84.5  No       82               84            Yes      CONTRADICTED
KXHIGHNY-26AUG15-T81    No       82               84            No       consistent
KXHIGHNY-26AUG15-T86    No       82               84            No       consistent
```

Both directions of error appear, which is what makes the example useful: a query that only
caught false positives would still pass on half of it. Two design points:

- **The verdict is computed, not looked up.** The query re-evaluates the comparator, which is
  the first thing in the ontology to actually use `wtl:Comparator` semantics rather than just
  record them. The stored `wtl:TruthAssessment` is carried alongside as a cross-check; if the
  two ever disagree, the stored assessment is wrong.
- **It returns every affected market, not only contradictions.** Filtering to contradictions
  would return zero rows whenever a correction changed nothing, which the runner treats as
  failure — and would hide the useful fact that a correction was issued and checked. The
  finding is in the `verdict` column, not in the row count. `wtl:Custom` conditions are
  excluded explicitly rather than defaulting to "consistent"; they need a human.

## Truth is not a property of a proposition

Writing CQ7 exposed a modelling error in 0.3.0. `wtl:hasTruthValue` is functional and untimed,
so it cannot represent a proposition that was true against the record as it stood and false
against the record as corrected. The proposition did not change and the exchange's resolution
did not change — only the document did.

Asserting both values would have been worse than wrong. OWL does not assume named individuals
are distinct, so a functional property forced to take two values *identifies* them: `wtl:True`
would silently become the same individual as `wtl:False`, and everything downstream would still
compute. `owl:AllDifferent` blocks over the truth values, comparators, resolution outcomes, and
market statuses now turn that into a reasoner inconsistency, verified by asserting a
contradiction and confirming HermiT reports it. Same guard, same reasoning as the units case.

The fix is `wtl:TruthAssessment`: a reified assignment carrying the proposition, the value, the
record consulted, and the time. Truth is a relation between a proposition and a state of the
record, not a property the proposition carries alone. `wtl:hasTruthValue` survives for cases
resting on a record that cannot be superseded, with a scope note saying so — but no example uses
it, which is the honest signal about how often that case arises here.

This also improved CQ4, which now reports the assessment made *from the document the exchange
read* rather than the proposition's current truth value. CQ4 and CQ7 consequently show the same
propositions with opposite values, correctly: one is what was believed at settlement, the other
what the corrected record implies.

## Rejected alternatives

**Skip BFO, use schema.org plus a few custom terms.** Faster to a first ingest and the standard
choice for this kind of project. Rejected because the errors this domain produces are precisely
category errors — treating a listing as an event, a datum as a quality, a protocol as a label —
and a lightweight vocabulary has nothing to say about them. If the ontology is not going to
prevent those, it is an ORM layer with extra steps.

**Import IAO for the information layer.** The [Information Artifact
Ontology](https://github.com/information-artifact-ontology/IAO) is the OBO Foundry mid-level
ontology sitting directly under BFO, covering exactly what `wtl:` covers. Roughly eight of our
terms have IAO counterparts:

| Ours | IAO |
|---|---|
| `wtl:InformationContentEntity` | `IAO_0000030` information content entity |
| `wtl:MeasurementDatum` | `IAO_0000109` measurement datum |
| `wtl:Document` | `IAO_0000310` document |
| `wtl:DirectiveInformationEntity` | `IAO_0000033` directive information entity |
| `wtl:Plan` | `IAO_0000104` plan specification |
| `wtl:InformationBearingEntity` | `IAO_0000015` information carrier |
| `wtl:isAbout` | `IAO_0000136` is about |
| `wtl:hasUnit` | `IAO_0000039` + `IAO_0000003` measurement unit label |

Rejected, because the benefit of IAO is standard IRIs for downstream consumers and this
ontology has none. Without that, importing 210 classes to replace eight is a net loss in
legibility.

The compatibility picture, checked against IAO release 2026-03-30 rather than assumed, since
it is the part most likely to be misremembered later:

- **Classes are byte-identical.** Every BFO class we use appears in IAO under the same
  `obo/BFO_XXXXXXX` IRI. Class-level merging would have been free.
- **Properties diverge.** IAO uses Relation Ontology IDs where BFO-2020 defines the relation
  natively: `RO_0000057` not `BFO_0000057` for *has participant*; `RO_0000052` *characteristic
  of* not `BFO_0000197` *inheres in*; `RO_0000059`/`RO_0000058` for concretization;
  `BFO_0000051` *has part* where we use `BFO_0000178` *has continuant part*. There is no IAO
  counterpart to `BFO_0000101` *is carrier of*. RO has further deprecated its own
  `RO_0004096`/`RO_0004097` inheres-in and bearer-of in favour of the *characteristic* naming,
  moving away from BFO-2020 rather than toward it.
- **IAO declares zero `owl:equivalentProperty` axioms.** Merged, `BFO_0000057` and `RO_0000057`
  would be two unrelated properties sharing a label. Nothing errors; inferences silently stop
  firing. Bridging is only about six axioms given our small property surface, but a broken
  bridge is invisible, so it would need its own competency test.
- **No BFO-2020 temporal terms.** IAO references `BFO_0000008`, `BFO_0000038`, `BFO_0000148`,
  but not `BFO_0000202` temporal interval or `BFO_0000203` temporal instant. Our
  climatological-day boundaries use those, so we would keep our own regardless. Absence, not
  conflict.

Consequence for units: IAO's `measurement unit label` was the one clear win, so with IAO
rejected, `wtl:hasUnit` being a string is now our problem to solve directly. It remains the
one genuine soundness gap in 0.1.0.

**Register the w3id namespace IRIs.** Rejected for the same reason. The IRIs are stable
identifiers, not addresses; `src/catalog-v001.xml` resolves them offline, and Protégé and ROBOT
both honour it. Registering redirects would serve consumers who do not exist.

**One namespace instead of three.** Simpler prefixes, but the weather module is reusable
independently of prediction markets and the market module is reusable for non-weather markets.
Splitting costs three prefix declarations.

**Model price as a quality of a contract.** Prices are not qualities: they are not borne by the
contract independently of a transaction, and they change without the contract changing. Filed as
`wtl:MeasurementDatum` via `ksh:Quote`, with a reference time, which also gives somewhere natural
to hang order book snapshots.
