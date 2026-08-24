# Closing the five analysis findings

Design for 0.10.0. Written 2026-08-23.

Five findings came out of a read of the repo at 0.9.0, with everything green:
67/67 negative tests, 8/8 competency questions, HermiT consistent. Nothing here
fixes a break. Four of the five are about the distance between *green* and
*known to work*, which is the distance this repo has spent forty commits closing.

The load-bearing one is the second. The rest are small.

---

## 1. The coverage metric cannot measure what README says it measures

`scripts/validate.py` reports `40/98 minted classes have an instance in the
examples`, and `README.md` cites that figure as the mechanism that keeps the
trading-layer gap visible.

It counts direct `rdf:type` only. Counting the subclass closure gives 57/98. The
seventeen-class difference is abstract parents — `ksh:Market`, `wx:Forecast`,
`fm:Document` — which are exercised through a child and can never move the
number no matter how much data arrives. So the figure conflates *abstract
parent* with *unusable class*, which is the one distinction it exists to draw.

**Change.** Report both numbers:

```
40 direct / 57 via subclass / 98 minted classes have an instance in the examples
```

**Stays advisory.** The existing comment says so deliberately and this design
does not change that. The CLAUDE.md rule that a new check needs a negative test
does not apply, because nothing new can fail — this is a note, not a check.
`README.md` gains a clause naming the direct count as the one that tracks the
gap.

---

## 2. A worked example on rain

Eighteen classes in `src/weather.ttl` have no instance, no query, no check, and
no mention anywhere outside the module that mints them: the precipitation, wind,
storm, and atmospheric-state branches. That is the condition the trading layer
was in through 0.7.1, and the lesson from `ffd64e0` was that unused meant
*unusable* — the vocabulary could not express an order at all. Eighteen classes
is roughly a fifth of the ontology sitting in that state, untested.

### What the exchange actually lists

Checked against the live Kalshi API on 2026-08-23, 354 series in Climate and
Weather:

- **No wind series exist.** `wx:WindSpeed`, `wx:WindDirection` and `wx:AirMotion`
  have no listable market behind them. That is a finding, not a blocker, and it
  is recorded here rather than acted on.
- Rain in NYC is listed in two shapes, both settling on the NWS climatological
  report for NYC (`site=OKX&issuedby=NYC`) — the same product family the
  temperature example already reads:
  - `KXRAINNYC-26JUL15-T0`, "Will it rain in New York City on Wednesday?",
    settled, result yes.
  - `KXRAINNYCM-26AUG-8` through `-13`, "Rain in NYC in Aug 2026? Above N
    inches", currently open.

This design takes the daily market only. It is settled, so it exercises the full
chain the temperature example does — resolution, market settlement, truth
assessment — where the monthly ladder could exercise none of it.

### The decision the example forces

Kalshi settles "will it rain" as `strike_type: greater` with
`floor_strike: 0`. The market that reads as being about an occurrent is settled
as a threshold on a quality. The scope note at `src/weather.ttl:157` asserts the
opposite split: that markets asking whether it will rain are about the process
and markets asking how many inches are about a quality of the output. The
exchange contradicts the first half.

**Resolution: the quality target settles, the occurrent sits in the record.**

The proposition's subject is a `wx:WeatherObservationTarget` naming
precipitation depth — exactly what the exchange settles on. The occurrent enters
on the observation side: a `wx:Rainfall` process occurred on the day, its output
is a `wx:PortionOfPrecipitate`, and that portion bears the
`wx:PrecipitationDepth` the report records.

This keeps the third modelling decision intact (the target carries the protocol),
keeps the second intact (a proposition is composed, never *about* a thing that
may not exist), and still instantiates four classes that have never had an
instance. `src/weather.ttl:157` is rewritten to say what the exchange does
rather than what the split ought to be.

### The file

`examples/kxrainnyc-2026-07-15.ttl`, prefix `rex:`.

**Market side.** `ksh:Series` `KXRAINNYC`; a `ksh:EventGrouping` covering the
target; one `ksh:Market`, ticker `KXRAINNYC-26JUL15-T0`. Its `fm:Proposition`
has the precipitation-depth target as subject, `fm:GreaterThan` as comparator,
`fm:floorValue 0`, and `unit:IN`. A `ksh:Resolution` reaching `ksh:ResolvedYes`,
produced by a `ksh:MarketSettlement`, with `ksh:sourceProtocol` naming the
precipitation protocol below.

**Weather side, quality.** A `wx:WeatherObservationTarget` naming precipitation
depth, at the observing site the temperature example already defines, over the
`wx:ClimatologicalDay` of 2026-07-15, under a new `rex:NWSDailyPrecipProtocol`.

New protocol rather than reusing `ex:NWSDailyClimateProtocol`, because the
reporting increment differs — hundredths of an inch against whole degrees — and
the protocol is precisely where a reporting increment belongs. Two targets
differing in protocol are different targets; that rule does not get bent for
convenience.

**Weather side, occurrent.** A `wx:Rainfall` process over the interval, its
output a `wx:PortionOfPrecipitate`, that portion bearing a
`wx:PrecipitationDepth`. A `wx:ClimatologicalReport` carrying a
`wx:WeatherObservationDatum` for the depth, and a `fm:TruthAssessment` resting
on that report.

**Probabilities.** A `wx:ProbabilisticForecast` with a `fm:ForecastProbability`
part, and a `fm:MarketImpliedProbability` derived from a `ksh:Quote` — both
assigning to the same proposition. This is what carries finding 4.

**Mechanical updates**, per CLAUDE.md: the `MODULES` and example lists in
`scripts/validate.py` and `scripts/run_competency.py`.

### Units

`unit:IN` is already in `src/imports/qudt-subset.ttl`. No extractor change, no
QUDT checkout, no `make qudt`.

### Risk, stated rather than assumed

This is where the "unused means unusable" question gets its answer. If the
precipitation vocabulary has a hole the way the trading layer did, section 2
grows. The response is to stop and re-scope, not to mint terms quietly mid-flight
— a term minted to make an example work is how the eighteen dark classes got
there in the first place.

The occurrent modelling is a design commitment, not data entry. If it does not
survive HermiT, that is a finding worth having and it goes in `docs/design-notes.md`.

---

## 3. The prose guard reads one file

`check_context_terms` guards `CONTEXT.md`: every backticked term must still be
declared, because nothing else reads that file and a rename would leave the
vocabulary pointing at a term that no longer exists.

`README.md` backticks 22 minted terms and `docs/` another 73. None are guarded,
and they rot the same way for the same reason.

**Change.** The check reads a list of files: `CONTEXT.md`, `README.md`,
`docs/design-notes.md`, `docs/fmo-in-thermaledge.md`. Failure messages name the
file they came from.

**`docs/superpowers/**` is deliberately excluded.** A plan or a spec describes a
state the graph does not have yet — this document names `rex:NWSDailyPrecipProtocol`,
which will not exist until section 2 is implemented. Guarding forward-looking
documents against the current graph would fail on correctness. The exclusion is
a design decision, not an oversight, and belongs in the check's docstring.

The path, make-target and check-name assertions stay scoped to `CONTEXT.md`. §4
of that file is repo mechanics and is the reason those assertions exist; README's
paths are already covered by nothing failing to build.

**Strikethrough already works.** `validate.py:121` reads
`(?<!~)`…`(?!~)`, so the rejected-name convention from CONTEXT.md §5 carries
over unchanged. `docs/design-notes.md:29` writes `ksh:Event` unstruck and needs
`~~` around it — the one content fix this section requires.

**Negative test required**, since this widens a check's scope: inject an
undeclared term into a throwaway `README.md` and assert the check fails naming
README.

---

## 4. The central join rests on one individual

`validate.py` reports 641 forecast-probability/proposition pairs checked but the
join demonstrated on one proposition — and one payout, one trade, one Brier
score. The checks are sound; the evidence under them is one bracket wide.

**Closed here, by section 2 and only there.** The join goes to two propositions,
and a second resolution, market settlement and truth assessment enter the graph.

**Not closed here, and the release notes must say so.** Trading-layer breadth
stays at one payout and one trade: no partial fills, no cancellations, no
multi-trade position. `README.md` already flags it under Open questions and that
entry stays exactly as it is. A version bump that quietly implied otherwise
would be the same class of mistake as a green check nobody has watched fail.

---

## 5. viz

No action. `make diagram-check` runs in `make test` and asserts the extraction
still finds every stanza, so the frontend is maintained rather than rotting. The
observation — that it is the largest part of the repo which is neither the
ontology nor its checks — needs no file.

---

## Version

0.10.0: `owl:versionIRI` and `owl:versionInfo` in `core.ttl`, `weather.ttl`,
`kalshi.ttl` and `fmo.ttl`, plus the status line in `README.md`. Four modules
and the README, together.

## Done means

- `make test` green, including `reason` and `reason-negative` with Java present.
- The new negative test fails when reverted, watched failing before it is trusted.
- The coverage note prints three numbers.
- `wx:Rainfall`, `wx:PrecipitationProcess`, `wx:PortionOfPrecipitate` and
  `wx:PrecipitationDepth` have instances.
- The forecast/market join is demonstrated on two propositions.
- `README.md` Open questions records that no wind market exists to model, and
  that the monthly rain ladder is nested rather than a partition — see below.

## Deferred, with reasons

**The nested ladder.** `KXRAINNYCM` runs "Above 8", "Above 9", "Above 10" — each
bracket implies the next. `check_grouping_coherence` refuses overlapping brackets
in a grouping asserted mutually exclusive, and CQ5 prices a ladder as a partition
summing to a dollar. Neither is right for a monotone ladder, whose invariant is
non-increasing prices. The grouping model assumes partition semantics and nothing
says so. This is a real gap and it gets its own cycle; it is recorded in README's
Open questions now.

**Wind, storms, atmospheric state.** Sixteen of the eighteen still dark after
this work: the example gives instances to `wx:Rainfall` and
`wx:PortionOfPrecipitate` directly, and to `wx:PrecipitationProcess` and
`wx:PrecipitationDepth` as their parents.
No wind market exists to model. Storms and tropical cyclones are already flagged
as contested in `docs/design-notes.md`. Recorded, not resolved.
