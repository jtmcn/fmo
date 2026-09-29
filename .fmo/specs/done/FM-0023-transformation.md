---
id: FM-0023
title: Model the transformation step, so a decision's derived inputs trace back to the copies they came from
type: feature
priority: 2
depends_on:
  - FM-0022
touches:
  - src/core.ttl
  - src/weather.ttl
  - src/kalshi.ttl
  - src/fmo.ttl
  - scripts/validate.py
  - scripts/test_validate.py
  - scripts/test_reason.py
  - queries/axiom-expectations.json
  - queries/cq02-probability-gap.expected
  - queries/cq09-decision-lineage.rq
  - queries/cq09-decision-lineage.expected
  - examples/kxhighny-2026-08-15-lineage.ttl
  - CONTEXT.md
  - README.md
  - docs/design-notes.md
forbidden:
  - src/imports/**
  - scripts/extract_prov_subset.py
  - shapes/thermaledge-export.ttl
  - shapes/thermaledge-export.pin.json
  - examples/kxhighny-2026-08-15.ttl
  - examples/kxrainnyc-2026-07-15.ttl
risk: elevated
acceptance:
  - claim: >-
      fm:Transformation is a data handling process and an information process,
      and no process is both a transformation and a retrieval.
    witness: make axioms, over a new "fm:Retrieval disjointWith fm:Transformation" entry in queries/axiom-expectations.json
  - claim: >-
      ksh:PriceToProbabilityDerivation is a transformation, so every existing
      derivation individual is one without a data change.
    witness: make meta and make validate (check_transformations), whose content-input traversal is populated only by the two derivations and fails on a zero count if the superclass goes
  - claim: >-
      A transformation's output is new content: it is never the content an
      input copy carries or a part of it, never one of its own inputs, and
      never a carrier.
    witness: make validate (check_transformations), with a negative test in test_validate.py for each of the four
  - claim: >-
      A transformation with an end time never ends before the retrievals of the
      copies it read.
    witness: make validate (check_transformations), with a negative test in test_validate.py
  - claim: >-
      For each trading decision, CQ9 returns every copy it read, directly or
      through a chain of transformations, and names the derived content it was
      reached through. The trade's projected probability traces to the 06Z
      copy through the bracket projection.
    witness: make cq, over queries/cq09-decision-lineage.expected
  - claim: >-
      fm:ForecastProbability admits content derived from a prediction process's
      output, and carries a change note saying so.
    witness: src/core.ttl, reviewed; make lineage passes with the definition changed in place
  - claim: >-
      All four modules move one minor version, with no owl:incompatibleWith,
      and no released IRI goes dark.
    witness: make lineage
---

## Context

FM-0022 modelled the extract and load of ELT as `fm:Retrieval`: a fetch makes
a `fm:RetrievedCopy` of the issuer's content, and nothing new.
`fm:DataHandlingProcess` was defined as acquiring, storing *or transforming*,
and left out of `fm:InformationProcess` because a retrieval produces no new
content. Its scope note, `docs/design-notes.md` ("Copies, not records") and
FM-0022's Out of scope all named this spec as the step that would.

PR #76 made "ingestion" a `skos:altLabel` of `fm:Retrieval`, and wrote the
boundary into `CONTEXT.md`: a lossless change of format still makes a copy,
and anything that changes what the content says is a transformation. This spec
gives the second half of that sentence a class. It should land after #76.

ThermalEdge's transforms are dbt models, and the bracket projector that turns
GEFS member temperatures into a probability per strike range.

## Problem

`lex:Decision-Trade` reads `ex:ForecastProb-82-83`, "GEFS 06Z P(82-83F)". GEFS
issues member temperatures, not bracket probabilities: ThermalEdge computed
that number from the 06Z copy. Nothing in the graph says so, so CQ9 cannot
show that the trade's probability came from the stale fetch, and a decision
reading only derived content would have no walkable lineage at all.

The market side already has the pattern without the name.
`ksh:PriceToProbabilityDerivation` takes a quote and yields a market implied
probability, and `fm:MarketImpliedProbability` is defined as "derived by
transformation". Two models of one step would drift.

### Decisions already made

- **`fm:Transformation ⊑ fm:DataHandlingProcess ⊓ fm:InformationProcess`**, in
  `core.ttl`'s "Data handling" section. The second parent is inherited from
  "new content as output"; the first says it is the system working on content
  for its own use. Restrictions: `fm:hasInput` some `prov:Entity`, and
  `fm:hasOutput` some `fm:InformationContentEntity`. The scope note states the
  boundary in domain terms: re-encoding the same content is not a
  transformation; converting units, aggregating ensemble members, filtering
  and deriving a probability are.
- **Disjoint from `fm:Retrieval`.** A "fetch and convert" step typed as both is
  the one mistake the ELT boundary exists to prevent. The disjointness earns
  its place by the design notes' own test: a real ingest mistake would type
  one process as both. A pipeline step that does both is two processes.
- **Inputs are copies, or content an earlier transformation produced.** The
  copy, not the content, for the reason `ksh:TradingDecision` cites copies: only
  the copy says which fetch was read. A chain of transformations ends at a
  copy when the lineage is recorded.
- **`ksh:PriceToProbabilityDerivation ⊑ fm:Transformation`**, a superclass
  added to a released term. The existing derivations in
  `examples/kxhighny-2026-08-15.ttl` and `examples/kxrainnyc-2026-07-15.ttl`
  read quote *content*, not a copy, and are forbidden here: both are export
  fixtures, and moving their inputs is a change to the fixtures, not to the
  model. The check below therefore accepts content as an input and records
  unrecorded lineage as unrecorded, not as an error.
- **No `prov:wasDerivedFrom`.** FM-0022's Out of scope said transformations
  would be "linked by `prov:wasDerivedFrom`". Asserting it would state twice
  what `fm:hasInput` and `fm:hasOutput` already say, and since
  `fm:hasInput ⊑ prov:used` and `fm:isOutputOf ⊑ prov:wasGeneratedBy`, a PROV
  consumer already walks entity ← activity ← entity. Two statements of one fact
  drift, and a third check would exist only to hold them together. A property
  chain deriving it was also considered and declined: it would apply to every
  FMO process, including retrieval, and commit to more than this spec needs.
  The design notes get the paragraph.
- **`fm:ForecastProbability` is redefined in place**: "a probability assignment
  produced by a prediction process, or derived by transformation from the
  output of one". A `skos:changeNote` records it. A bracket probability
  computed from GEFS members is still the model's belief, and typing it as
  anything else would drop it out of CQ2's forecast side. The disjointness with
  `fm:MarketImpliedProbability` is unchanged: what separates them is the
  source, not whether a transformation touched it.
- **No subclass for the projector.** The example asserts
  `lex:Projection-06Z a fm:Transformation`. A `wx:BracketProjection` waits
  until a check or a query needs to tell it apart.
- **`check_transformations`**, `population="data"`, requires of each
  transformation: at least one input and one output; no output that is an
  input, is carried by an input copy, or is an `fm:InformationBearingEntity`;
  and, where it has a `prov:endedAtTime`, an end not before the end of any
  input copy's retrieval. It does not require an end time, because the
  existing derivations have none.
- **CQ9 walks through transformations.** An input reached by
  `(fm:hasOutput|^fm:isOutputOf)` and `fm:hasInput`, repeated, until a copy.
  A new `?via` column names the derived content a copy was reached through,
  unbound for a direct read. The trade's new row is `lex:Copy-06Z` via
  `lex:ProjectedProb-06Z-82-83` (see Comments).
- **Release.** A minor bump from whatever #76 leaves (0.21.1 → 0.22.0): a
  released term gains a superclass and another is redefined. No
  `owl:incompatibleWith`: every restriction added is existential, and data
  valid today still conforms.

## Out of scope

- `ksh:TradingDecision`'s restriction to at least one `fm:RetrievedCopy` as
  input. With transformations walkable, a decision reading only derived
  content has lineage, and the restriction could relax. It is a released
  term's signature and a separate argument.
- Moving the existing derivations' inputs from quote content to quote copies.
  That touches two export fixtures and the pin.
- A push-fed sibling of `fm:Retrieval`, for a websocket feed. `fm:Retrieval`'s
  definition says "requests"; a feed that is not requested needs its own class,
  when one is ingested.
- dbt model names, and any change to the ThermalEdge exporter or the export
  contract.
- `prov:wasDerivedFrom`, per the decision above.

## Notes for the agent

- `check_transformations` is a `data` check, so `make meta` sweeps it against
  the schema with no examples. Give each ordered comparison its own
  `coverage()` rather than folding them into one counter: the example has one
  timed transformation, and an aggregate would stay non-zero if the untimed
  derivations were all that remained. The traversal of inputs that are content
  rather than copies gets its own `coverage()` too: the two derivations are
  its only population, which is what makes it the reparenting's witness.
- The "carried by an input copy" test is the copy/transformation boundary. Its
  negative test is a transformation whose output is `ex:Forecast-GEFS-06Z`, the
  content `lex:Copy-06Z` carries.
- Add to the lineage example: `lex:Projection-06Z a fm:Transformation`, input
  `lex:Copy-06Z`, output a new `lex:ProjectedProb-06Z-82-83` the trade reads
  (see Comments), associated with `lex:IngestJob-2.4.0`, ending after the 06Z
  retrieval and before the trade.
- `fm:Transformation` is instantiated directly by the example, so
  `queries/class-coverage-expectations.json` needs no entry.
- CQ9 does no reasoning. Reach the derivation's class as
  `a/rdfs:subClassOf*`, and the walk with a property path, not recursion.
- `CONTEXT.md`: a **Transformation** entry (`fm:Transformation`), with the
  boundary sentence from the Retrieval entry pointing at it. _Avoid_:
  "processing" and "pipeline step" for it, and "derivation" bare, which stays
  the market-side name.
  Update **Data handling process** to name both children.
- `docs/design-notes.md`: rewrite the last sentence of "Copies, not records",
  and add the `prov:wasDerivedFrom` paragraph under the PROV-O section.
- `risk: elevated` because a released term gains a superclass and another is
  redefined; `make lineage` does not check the bump size or the change note, so
  review does.

## Comments

- 2026-09-29, implementation: the projection does not output
  `ex:ForecastProb-82-83`. The base example files that probability as a
  continuant part of the NWS-issued forecast, so making it a transformation's
  output would call one individual both the issuer's content and ours. The
  projection outputs `lex:ProjectedProb-06Z-82-83` (0.54) instead, and the trade
  reads that. The "carried by an input copy" test counts parts of the carried
  content, and has its own negative test. CQ2 gains the projected probability's
  two rows against the market, which is the gap ThermalEdge actually trades on.
  `ksh:PriceToProbabilityDerivation`'s definition now names its genus,
  transformation, and both it and `fm:ForecastProbability` carry change notes.
- 2026-09-29, landed as 0.22.0: every acceptance witness passes under
  `make test` (JDK, nothing skipped). Removing the derivation's new superclass
  empties the content-input traversal and fails `make validate` by name.
