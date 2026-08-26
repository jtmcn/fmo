# FMO — terminology

The controlled vocabulary for FMO. Every term used in a commit message, a PR body,
a design note, or a conversation about this ontology should appear here with one
meaning.

**How this is used.** This file is deliberately *not* a second copy of the ontology.
Every minted term already carries `rdfs:label`, `skos:definition`, and often
`skos:scopeNote`, and the validator fails without them — that is where meaning lives,
and `make diagram` is how you browse it. This file holds the layer Turtle cannot:
**which English words map onto which minted term, and which words not to use.**

> If the *meaning* of a term is in question, `skos:definition` in `src/` wins.
> If the *word* is in question, this file wins.

The `_Avoid_` lists are the load-bearing part. Almost every trap here is one where the
loose word and the minted term both parse, both reason, and disagree — "event" being
the one that would have made the whole ontology wrong.

---

## 1. The pivot

**Proposition** (`fm:Proposition`): the shared object a forecast and a market both point
at.
_Avoid_: "the claim", "the question", "the bet", "the outcome" (that is a
`ksh:ResolutionOutcome`), "the strike" — a bracket carries both `fm:floorValue` and
`fm:capValue`, so say which threshold you mean.

**Target**: never bare. `fm:ObservationTarget` and `wx:WeatherObservationTarget` are
different classes and different sentences need each: `ksh:coversTarget` ranges over the
`fm:` one; the protocol rules attach to the `wx:` one. Write the prefix.

**Protocol** (`wx:MeasurementProtocol`): the rules by which a value is determined —
publishing authority, boundaries, rounding. Carried by the target.
_Avoid_: "the methodology", "the standard", "the source" (see §3).

**Determination**: one target's answer to a physical question. Two protocols give two
determinations, related by `wx:alternativeDeterminationOf` and licensed to disagree.
_Avoid_: "the same reading from a different source" — that phrasing is failure class F1
in `docs/fmo-in-thermaledge.md`.

**Record**: never bare either. Three things wear the word:
`wx:ClimatologicalReport` and `wx:ReportCorrection` (what `wx:supersedes` relates),
`wx:WeatherObservationDatum` (one reading), and `fm:basedOnRecord`, whose range is
`fm:Document`. Say report, datum, or document.

**Realized value** (`fm:realizedValue`) and **settlement value** (`ksh:settlementValue`):
not opposites — the second is a *sub-property* of the first. The separator is the bearer.
A settlement value sits on a `ksh:Resolution` and is what the exchange determined; the
observational record can later say otherwise, which is `wx:ReportCorrection`'s reason to
exist.
_Avoid_: "the actual", "the truth", "the answer", and "distinct from" between these two.

**Truth assessment** (`fm:TruthAssessment`): the output of an evaluation process reading
a record. Truth is never a property of a proposition — it is asserted by an assessment,
which rests on a record, which can be superseded.

**Current assessment**: one resting on a record nothing supersedes. At most one per
proposition, enforced by `check_current_assessments`.
> Say "current", matching the check name and the message it prints. _Avoid_ "live",
> "active" (that is a `ksh:MarketStatus`), "the latest".

---

## 2. Weather side (`wx:`)

**Site** (`wx:ObservingSite`) vs **station** (`wx:WeatherStation`): the site is the
persistent location of record; the station is the equipment, and `KNYC` identifies one.
> Never use "station" where the settlement rules mean the site. Replacing a station does
> not change the target; changing site does.

**Climatological day** (`wx:ClimatologicalDay`): the interval the protocol defines.
_Avoid_: "the day", "the date", "midnight to midnight" without saying which midnight —
this one runs local *standard* time all year.

**Forecast** (`wx:Forecast`): deterministic or probabilistic — say which when it matters.
A `fm:ForecastProbability` is a *part* of a probabilistic forecast, not a synonym for it.

**Lead time** (`wx:leadTimeHours`): issuance to interval start. Derived and checked.
_Avoid_: "horizon", "forecast age".

**Correction** (`wx:ReportCorrection`) / **supersedes** (`wx:supersedes`): a later record
displacing an earlier one. The earlier record is *superseded*, never "wrong" or
"deleted"; both stay in the graph.
_Avoid_: "amendment" — `ksh:Amended` is a market status, on the other side of the model.
_Avoid_ also "revision", "restatement".

**Verification** vs **validation**: verification is the weather-science sense — scoring a
forecast against what happened (`examples/verification-synthetic.ttl`, CQ6). Validation is
`scripts/validate.py`. "Verification failed" is unreadable; name which.

**Calibration** vs **skill**: CQ6a is reliability per probability bin, CQ6b is skill by
lead time. Both are kept on purpose (`docs/design-notes.md`); neither name covers the
other.

---

## 3. Market side (`ksh:`)

**Market** (`ksh:Market`): one bracket — one proposition, one ticker.

**Event grouping** (`ksh:EventGrouping`): the set of markets partitioning one target.
The ladder. A listing, an information content entity — not an occurrent.
> **Never write bare "event".** Kalshi's API calls this an event and BFO's occurrent
> branch is where events live; a modeller who files it under `bfo:process` gets an
> ontology that parses, reasons, and is wrong. `skos:altLabel "event"` exists so a search
> for the API term still lands on the class — it is not permission to use it.

_Avoid_: "the event", "the market group", "the family". "Ladder" is fine for the markets
in order, not for the grouping object.

**Series** (`ksh:Series`): the recurring listing family, `KXHIGHNY`. A series spanning a
protocol change is **two time series**, not one with a discontinuity.
_Avoid_: "the ticker" bare — say series, event, or market ticker.

**Contract, lot, position**: a `ksh:BinaryContract` individual is a **lot**, carrying
`ksh:contractQuantity`; `ksh:Position` is the net holding. A payout pays one lot, not a
market and not a position — which is why the check is written per lot.
_Avoid_: "the contract" for a market, and "a payout pays a contract", which is ambiguous
exactly where a validator check lives.

**Settlement source**: two terms, and neither one is the publisher.
- `ksh:SettlementSource` — the class: the ICE **designating** the publication an exchange
  consults. A naming document, not the organisation and not the data.
- `ksh:settlementSource` — the property: relates a **listing** to that designation. It
  declares no domain and is resolved market → grouping → series; it does not hang off
  `ksh:MarketRules`.

When the question is what a number *means*, name the protocol, not the source:
`ksh:sourceProtocol` is what the validator checks against the target's protocol.

**Resolution** (`ksh:Resolution`): the exchange's determination. An information content
entity — a sibling of `fm:Document` under ICE, not a document, which is the range of
`fm:basedOnRecord`. Its outcome is a separate `ksh:ResolutionOutcome` designation reached
by `ksh:resolvesTo`.
**Market settlement** (`ksh:MarketSettlement`): the process producing it.
**Payout** (`ksh:Payout`): the process transferring a dollar a contract to the winning
side. Paying the losing side is the trading-layer form of scoring against a retracted
record, and is checked.
_Avoid_: "settlement" bare when you mean the resolution, "expiry", "the result".

**Quote** (`ksh:Quote`) vs **market-implied probability** (`fm:MarketImpliedProbability`):
a quote is prices; the probability is derived from it by
`ksh:PriceToProbabilityDerivation`. `price / 100` is not the derivation, it is a
placeholder.
_Avoid_: "the price is the probability".

**Status** (`ksh:hasStatus`): functional, current only. Not a history.

---

## 4. Repo mechanics

These are the words for working *on* the ontology, and none of them are minted terms.

**Module**: one of the four ontology files in `src/`. The `MODULES` list in
`scripts/registry.py` holds six — the two files in `src/imports/` are loaded but are
not modules, and are not ours to edit.
_Avoid_: "the file", "the namespace" (a namespace is an IRI prefix).

**Check**: one assertion in `scripts/validate.py`. Pure Python, no Java.
**Negative test**: proof that a check fails when it should, split across three files by
what each proves. `scripts/test_validate.py` injects a defect into a throwaway copy and
asserts the matching check fails with the right message — one check, one defect.
`scripts/test_shapes.py` (`make shapes-negative`) proves properties of the SHACL shapes
themselves: vacuity, dead `sh:class`, and that each shape's required-property mutants are
attributed to the shape under test. `scripts/test_meta.py` (`make meta`) proves every
check function fails when handed a graph that empties its traversal, so a check with
nothing to check cannot pass.
_Avoid_: "test" bare — it reads as any of the three, and they fail for different reasons.

**Competency question** (CQ): a question the ontology must answer, numbered 1–8. Most are
a `queries/cqNN-*.rq` plus its `.expected`, and an empty result set **fails** — but CQ3 is
`make competency` (a reasoner re-derivation, no query file) and CQ6 is two queries. Say
the number, not "the query".

**Reasoning**: HermiT via ROBOT — consistency and re-derivation. Skips without Java.
Never say "the validator caught it" about something only the reasoner catches, or the
reverse; the split is deliberate.

**Worked example**: a hand-authored file in `examples/` naming real tickers.
**Synthetic dataset**: `examples/verification-synthetic.ttl`, generated with a fixed
seed. A diff there means the generator changed, never the data.

**The map**: `build/ontology.html` from `make diagram`. Not "the docs", not "the viewer".

**Vendored** (`src/imports/bfo-core.ttl`, never edited) vs **generated**
(`qudt-subset.ttl`, edit the extractor). Two different prohibitions on hand-editing.

---

## 5. Style

- Terms with their prefix in prose: `ksh:EventGrouping`, not "EventGrouping" and not
  "event grouping" where precision matters. Bare labels are for reading aloud.
- A name the project **rejected** is struck through: ~~`ksh:Event`~~. `validate.py`
  checks that every backticked term exists in `src/`, and a rejected name by definition
  does not; strikethrough is how to spell one without failing the check, and it is the
  only exemption.
- Prefixes are `fm:`, `wx:`, `ksh:` — never "core:". Example data uses `ex:` (worked
  example), `tex:` (trading), `vex:` (verification), `rex:` (rain).
- Kalshi tickers verbatim and uppercase: `KXHIGHNY-26AUG15-B82.5`.
- Files by path from the repo root: `src/weather.ttl`, `queries/cq05-*.rq`.
- Say which side: "the forecast side" (`wx:`) and "the market side" (`ksh:`) meet at
  "the pivot" (`fm:`). The map is coloured on exactly this split.
- Versions are bumped in four modules plus the README status line, together.

---

## Settled naming decisions

1. **event, ~~`ksh:Event`~~ → `ksh:EventGrouping`.** The collision that matters most; see
   `docs/design-notes.md` §"The naming collision that matters most". Everything the
   Kalshi API returns is a document; the processes are separate classes.
2. **station → site.** The target names a site. The station is the instrument, and
   replacing it must not change the proposition.
3. **settlement source → protocol.** The source is who publishes; the protocol is what
   the number means. Describing the 2026-08-14 migration as a source change is what makes
   it look survivable (`README.md`, and design-notes §"The settlement source moved").
4. **unit.** `fm:hasUnit` and `wx:conventionalUnit` are both read aloud as "the unit" and
   the axioms differ — one functional, one not. Always say which.
5. **Wantology → FMO.** The old name survives nowhere in `src/`, `docs/`, `scripts/`,
   `queries/`, `examples/`, or `README.md`, and should not come back in prose about
   history; say "before 0.9.0".

## Open naming decisions

1. **module.** §4 gives the word one meaning: an ontology file in `src/`. Design work on
   `scripts/` needs the other one — a thing with an interface and an implementation —
   and the two collide exactly where precision matters, which is the shape of the
   `ksh:EventGrouping` trap. Candidates: keep **module** for `src/` and say **check**,
   **checker** or **runner** for the Python; or qualify both as *ontology module* and
   *code module*. Unsettled on purpose: pick it deliberately, not inside a refactor.

Add here rather than settling one in a commit message — an ambiguity resolved in
a commit message is an ambiguity that comes back.
