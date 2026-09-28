---
id: FM-0022
title: Import PROV-O, and trace a trading decision to the copies of the forecasts and observations it read
type: feature
priority: 2
depends_on: []
touches:
  - src/core.ttl
  - src/weather.ttl
  - src/kalshi.ttl
  - src/fmo.ttl
  - src/catalog-v001.xml
  - src/imports/prov-subset.ttl
  - scripts/extract_prov_subset.py
  - scripts/registry.py
  - scripts/validate.py
  - scripts/test_validate.py
  - scripts/test_reason.py
  - scripts/axioms.py
  - queries/axiom-expectations.json
  - queries/prefixes.txt
  - examples/kxhighny-2026-08-15-lineage.ttl
  - queries/cq09-decision-lineage.rq
  - queries/cq09-decision-lineage.expected
  - queries/class-coverage-expectations.json
  - Makefile
  - CONTEXT.md
  - README.md
  - docs/design-notes.md
forbidden:
  - src/imports/bfo-core.ttl
  - src/imports/qudt-subset.ttl
  - shapes/thermaledge-export.ttl
  - shapes/thermaledge-export.pin.json
risk: elevated
acceptance:
  - claim: >-
      The PROV-O subset is generated from a pinned upstream file, and every
      class in it reaches bfo:entity through the bridge axioms in core.ttl.
    witness: make validate (check_bridged_grounding, PROV traversal), with a negative test in test_validate.py
  - claim: >-
      prov:Entity is grounded under bfo:continuant, so a process used as the
      input to another process is a HermiT inconsistency.
    witness: make reason; a mutant in scripts/test_reason.py
  - claim: >-
      fm:hasInput, fm:isOutputOf, fm:issuedBy, fm:hasAgent and wx:supersedes are
      sub-properties of prov:used, prov:wasGeneratedBy, prov:wasAttributedTo,
      prov:wasAssociatedWith and prov:wasRevisionOf; wx:issuanceTime is not a sub-property of
      prov:generatedAtTime.
    witness: src/core.ttl and src/weather.ttl, reviewed; CQ9 walks prov:used without naming fm:hasInput
  - claim: >-
      A retrieval never ends before the issuance of the content its copy
      carries, and a trading decision never ends before the retrievals of the
      copies it cites.
    witness: make validate (check_retrievals, check_trading_decisions), each with a negative test
  - claim: >-
      A decision statement is a trade instruction or a hold statement and never
      both, and every hold carries exactly one reason.
    witness: make reason (disjointness mutant); make validate-negative (check_trading_decisions, hold with no reason)
  - claim: >-
      For each trading decision, CQ9 returns the copies it cited, when and
      where each was retrieved, the issuance time of what each carries, and a
      newer issuance for the same target when one existed before the decision.
      The expected rows include one stale hold and one fresh trade.
    witness: make cq, over queries/cq09-decision-lineage.expected
  - claim: >-
      All four modules move to 0.21.0 with owl:incompatibleWith 0.20.0, and no
      released IRI goes dark.
    witness: make lineage
---

## Context

FMO has provenance terms of its own, all grounded in BFO: `fm:hasInput`,
`fm:hasOutput`, `fm:issuedBy`, `wx:issuanceTime`, `wx:supersedes`,
`wx:producedByModel` and `ksh:settlementSource`. They say which authority
issued what, and which document a settlement read (CQ4). They do not say how
data reached ThermalEdge, or what a decision was based on.

That gap is F4 in `docs/fmo-in-thermaledge.md`: `trading_decisions` stores its
inputs as opaque JSON, and `source_record_id` exists in ten dbt models and no
Python file. `decide()` mostly holds, and a hold leaves no trace a calibration
can join to.

## Problem

Two chains need to be walkable:

- **Ingestion lineage.** Which endpoint a copy of a forecast or observation was
  fetched from, and when, set against when that content was issued.
- **Decision lineage.** Which copies a trading decision read, whether it traded
  or held, and whether a newer issuance for the same target existed when it
  decided. Holds included: a backtest that sees only the days it traded is
  biased toward them.

### Decisions already made

- **Import PROV-O, not annotate.** Unlike SOSA (`docs/design-notes.md`, "Why not
  SOSA"), PROV-O fills a gap rather than duplicating a pattern FMO already has.
  Lineage is what it is for, and PROV-aware queries should run over FMO data
  unchanged. The design notes get a section, "PROV-O, and not SOSA", saying so.
- **A generated subset.** `scripts/extract_prov_subset.py` extracts
  `src/imports/prov-subset.ttl` from the W3C PROV-O Recommendation (2013-04-30),
  with its digest pinned, as the QUDT subset is built. Only the terms used:
  `Entity`, `Activity`, `Agent`, `SoftwareAgent`, `used`, `wasGeneratedBy`,
  `wasAssociatedWith`, `wasAttributedTo`, `wasDerivedFrom`, `wasRevisionOf`,
  `startedAtTime`, `endedAtTime`.
- **Grounding**, beside the QUDT bridge in `core.ttl`:
  `prov:Entity ⊑ bfo:continuant`, `prov:Activity ⊑ bfo:process`,
  `prov:Agent ⊑ bfo:continuant`, `fm:Agent ⊑ prov:Agent`. Entity under
  continuant makes PROV-DM's entity/activity disjointness a consequence of BFO's.
  Agent is not under `fm:Agent`, because `fm:Agent` is material and the agent
  of a retrieval is usually software.
- **Alignment by sub-property.** `fm:hasInput ⊑ prov:used`,
  `fm:isOutputOf ⊑ prov:wasGeneratedBy`, `fm:issuedBy ⊑ prov:wasAttributedTo`,
  `fm:hasAgent ⊑ prov:wasAssociatedWith`, `wx:supersedes ⊑ prov:wasRevisionOf`. `prov:used`'s range therefore
  makes every FMO input a continuant; every input in `examples/` already is.
- **Issuance is not generation.** `wx:issuanceTime` stays out of
  `prov:generatedAtTime`, and its scope note says why: a report can be
  generated at 05:40 and issued at 06:00, and the staleness question depends
  on keeping the two apart.
- **Retrieval, in `core.ttl`.** Fetching content makes a new carrier of the
  same information content entity, not a new one:
  - `fm:DataHandlingProcess ⊑ bfo:process`. Not under `fm:InformationProcess`,
    whose definition requires a new ICE as output. It is the parent a later
    transformation (FM-0023) sits beside.
  - `fm:Retrieval ⊑ fm:DataHandlingProcess`: some ICE as input, some
    `fm:RetrievedCopy` as output.
  - `fm:RetrievedCopy ⊑ fm:InformationBearingEntity`: carrier of some ICE,
    output of some `fm:Retrieval`. ThermalEdge's `source_record_id` becomes its
    IRI, so no identifier property is minted.
  - `fm:retrievedFrom`, `xsd:anyURI`, on `fm:Retrieval`. Timing and agent use
    `prov:startedAtTime`, `prov:endedAtTime` and `prov:wasAssociatedWith`.
- **Decision, in `kalshi.ttl`**, under "Trading processes":
  - `ksh:TradingDecision ⊑ fm:InformationProcess`: at least one
    `fm:RetrievedCopy` as input, exactly one `ksh:DecisionStatement` as output.
    Derived probabilities may be inputs too; they do not replace the copies.
  - `ksh:DecisionStatement ⊑ fm:DirectiveInformationEntity`, covered by the
    disjoint `ksh:TradeInstruction` and `ksh:HoldStatement`.
  - A `ksh:TradeInstruction` is the input to the `ksh:OrderPlacement` that
    follows; the placement → order chain is unchanged.
  - `ksh:holdReason`, `xsd:string`, on `ksh:HoldStatement`. Prose, not an
    enumeration: the reasons are `decide()`'s code paths and will move.
  - The decision instant is `prov:endedAtTime`; the strategy is
    `prov:wasAssociatedWith` a `prov:SoftwareAgent` whose IRI carries its
    version.
- **Release.** Minor bump to 0.21.0 across all four modules, since
  `fm:hasInput`'s signature moves, with `owl:incompatibleWith` 0.20.0: data
  valid under 0.20.0 with an occurrent as an input is inconsistent now.

## Out of scope

- **Transformations** (depth 2): each pipeline step as a process from input
  content to derived content, linked by `prov:wasDerivedFrom`. FM-0023, which
  depends on this spec.
- The ThermalEdge exporter, and any change to the export contract.
- PROV-O's qualified patterns (`qualifiedUsage`, `prov:Role`, and the rest).
- `prov:generatedAtTime`.
- Failed retrievals: a fetch that errored produces no copy, and nothing here
  records it.

## Notes for the agent

- `check_bridged_grounding` derives its population from the QUDT namespace
  only. Give PROV its own traversal with its own `coverage()` call rather than
  widening the QUDT one: an aggregate counter stays non-zero when one
  namespace empties.
- The two new data checks are `population="data"`; `make meta` will sweep them
  against the schema with no examples.
- The example is `examples/kxhighny-2026-08-15-lineage.ttl`: NWS forecasts for
  one target issued at 06:00 and 12:00, each retrieved once; a hold at 13:00
  citing only the 06:00 copy; a trade at 15:00 citing the 12:00 copy and a
  quote copy, followed by an order placement.
- CQ9 uses `a/rdfs:subClassOf*` for types, and reaches inputs as
  `?d ?p ?copy . ?p rdfs:subPropertyOf* prov:used`, since SPARQL here does no
  reasoning. That pattern is what witnesses the alignment.
- New `CONTEXT.md` entries: **retrieval**, **retrieved copy** (with "record" on
  its _Avoid_ list, since `CONTEXT.md` already forbids it bare), **data
  handling process**, **trading decision**, **decision statement**, **trade
  instruction**, **hold statement**. Note that `prov:wasRevisionOf` is PROV's
  name for what FMO calls *supersedes*; "revision" stays on the _Avoid_ list.
- Adding `prov-subset.ttl` means `MODULES` in `scripts/registry.py`, the
  imports in `src/fmo.ttl`, and `src/catalog-v001.xml`, plus a `make prov`
  target alongside `make qudt` and README rows.

## Comments

- 2026-09-27, planning: the SHACL constraints moved into check_retrievals and
  check_trading_decisions, because example data is validated only against the
  forbidden export contract. fm:hasAgent joined the alignment.
