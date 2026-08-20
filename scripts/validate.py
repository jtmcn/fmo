#!/usr/bin/env python3
"""Structural checks for the FMO modules.

Parses every module plus the vendored BFO, then checks the things that actually
go wrong when hand-authoring a BFO application ontology:

  1. Every file parses as Turtle.
  2. Every term we mint sits under exactly one BFO top-level branch, and
     reaches bfo:entity by rdfs:subClassOf. A term that does not is either
     unrooted or accidentally rooted in owl:Thing.
  3. No class is both a continuant and an occurrent. This is the disjointness
     that BFO cares most about and the one an application ontology breaks by
     mistake, typically by filing an information artifact under process.
  4. Every property we use in the examples is declared somewhere, and every
     individual they reference is defined somewhere. A dangling IRI is legal RDF
     that reads as an untyped resource, so a renamed individual degrades every
     term pointing at it without breaking anything loudly.
  5. Every class and property carries a label and a skos:definition. A scopeNote
     says "why here, not there", which is not a statement of what the term means,
     so it does not substitute.
  6. Derived values match what they are derived from: wx:leadTimeHours against the
     forecast's issuance time and its target interval's first instant.
  6b. A forecast's wx:forecastFor target is the subject of every proposition its
     probabilities assign to. Otherwise the forecast is scored against one
     determination of a quantity while the market settles on another, which is the
     error this ontology exists to prevent and the one it could not previously see.
  6c. A stored fm:BrierScore matches the probability and outcome it is derived
     from, refuses to score an assessment whose truth value is neither fm:True nor
     fm:False (a Brier score against an indeterminate outcome is undefined, not
     zero), and fails if the assessment it scores rests on a superseded record.
  7. Units cohere. Where two values get compared, they must use the *same* QUDT unit;
     where a unit is merely chosen for a variable, its QUDT dimension vector must
     match. This catches both a Fahrenheit threshold read against a Celsius target
     (same dimension, still wrong) and inches read against a temperature. The same
     identical-unit rule reaches ksh:settlementValue through resolutionOf and
     expressesProposition, since it is a sub-property of fm:realizedValue that
     rdflib does not follow.
  8. At most one truth assessment per proposition may rest on a record nothing
     supersedes. Two live assessments make CQ6 double-count the proposition rather
     than contradict it, and every other check stays green while it happens.
  9. A market's grouping covers exactly one target, that target is the one the
     market's proposition names, every bracket is satisfiable, and no two brackets
     in a grouping asserted mutually exclusive overlap.
 10. Every observation target names exactly one measurement protocol, and the protocol
     a market's settlement source publishes under is the one its proposition's target
     names. A missing protocol is invisible to the reasoner -- open-world reads it as
     unnamed rather than absent -- and a settlement source disagreeing with a target's
     protocol is the 2026-08-14 migration expressed as a modelling error.
 11. The trading layer settles what it says it settles: a match outputs one yes lot and
     one no lot of equal quantity, and a payout pays the side its resolution determined,
     to the holder whose obligation it realizes, at one dollar a contract.

Checks 6 and 7 fail on ambiguous input rather than picking one: two units on a term,
or two targets on a forecast, mean the answer would come from whichever triple rdflib
happened to yield first. Absence is likewise a failure, not a skip -- a value with no
unit is as likely an authoring slip as a value with the wrong one, and skipping it
made the checker report OK on a defect it exists to catch.

Negative coverage for every check lives in scripts/test_validate.py -- a checker
nobody has watched fail is not known to work.

Exit code is non-zero if any check fails. Run: python3 scripts/validate.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from rdflib import Graph, RDF, RDFS, OWL, URIRef, Literal
from rdflib.namespace import SKOS

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"

BFO = "http://purl.obolibrary.org/obo/"
ENTITY = URIRef(BFO + "BFO_0000001")
CONTINUANT = URIRef(BFO + "BFO_0000002")
OCCURRENT = URIRef(BFO + "BFO_0000003")

# Branches we expect every minted term to land in, for the summary table.
BRANCHES = {
    URIRef(BFO + "BFO_0000004"): "independent continuant",
    URIRef(BFO + "BFO_0000020"): "specifically dependent continuant",
    URIRef(BFO + "BFO_0000031"): "generically dependent continuant",
    URIRef(BFO + "BFO_0000003"): "occurrent",
}

OUR_NS = (
    "https://w3id.org/forecast-market-ontology/core#",
    "https://w3id.org/forecast-market-ontology/weather#",
    "https://w3id.org/forecast-market-ontology/kalshi#",
)

MODULES = ["imports/bfo-core.ttl", "imports/qudt-subset.ttl", "core.ttl", "weather.ttl", "kalshi.ttl", "fmo.ttl"]
EXAMPLES = sorted((ROOT / "examples").glob("*.ttl"))

failures: list[str] = []
notes: list[str] = []


def fail(msg: str) -> None:
    failures.append(msg)


def is_ours(term) -> bool:
    return isinstance(term, URIRef) and str(term).startswith(OUR_NS)


def ancestors(g: Graph, cls: URIRef) -> set[URIRef]:
    """Named rdfs:subClassOf ancestors, ignoring anonymous restrictions."""
    seen: set[URIRef] = set()
    stack = [cls]
    while stack:
        cur = stack.pop()
        for parent in g.objects(cur, RDFS.subClassOf):
            if isinstance(parent, URIRef) and parent not in seen:
                seen.add(parent)
                stack.append(parent)
    return seen


def types_of(g: Graph, node) -> set:
    """Asserted types plus their named ancestors -- the a/rdfs:subClassOf* the queries walk."""
    out: set = set()
    for cls in g.objects(node, RDF.type):
        out.add(cls)
        out |= ancestors(g, cls)
    return out


def instances_of(g: Graph, cls: URIRef) -> list:
    """Every node whose type reaches cls, asserted subclasses included.

    g.subjects(RDF.type, cls) sees the asserted type only, so a minted subclass --
    a void refund under ksh:Payout, say -- would get no validation while still
    turning up in the competency questions, which all use a/rdfs:subClassOf*.
    """
    return sorted({s for s in g.subjects(RDF.type, None) if cls in types_of(g, s)}, key=str)


QUDT = "http://qudt.org/schema/qudt/"
FM = "https://w3id.org/forecast-market-ontology/core#"
WX = "https://w3id.org/forecast-market-ontology/weather#"
KSH = "https://w3id.org/forecast-market-ontology/kalshi#"

HAS_UNIT = URIRef(FM + "hasUnit")
HAS_SUBJECT = URIRef(FM + "hasSubject")
REPORTS_FOR = URIRef(WX + "reportsValueFor")
TARGET_VAR = URIRef(WX + "targetVariable")
CONVENTIONAL_UNIT = URIRef(WX + "conventionalUnit")
DIM_VECTOR = URIRef(QUDT + "hasDimensionVector")
SETTLEMENT_VALUE = URIRef(KSH + "settlementValue")
RESOLUTION_OF = URIRef(KSH + "resolutionOf")
EXPRESSES = URIRef(KSH + "expressesProposition")
ASSESSES = URIRef(FM + "assessesProposition")
BASED_ON_RECORD = URIRef(FM + "basedOnRecord")
SUPERSEDES = URIRef(WX + "supersedes")
SCORES_ASSIGNMENT = URIRef(FM + "scoresAssignment")
USES_SCORING_RULE = URIRef(FM + "usesScoringRule")
SCORED_AGAINST = URIRef(FM + "scoredAgainst")
SCORE_VALUE = URIRef(FM + "scoreValue")
BRIER_SCORE = URIRef(FM + "BrierScore")
PROBABILITY_VALUE = URIRef(FM + "probabilityValue")
ASSESSED_TRUTH_VALUE = URIRef(FM + "assessedTruthValue")
TRUE_VALUE = URIRef(FM + "True")
FALSE_VALUE = URIRef(FM + "False")
IN_EVENT_GROUPING = URIRef(KSH + "inEventGrouping")
COVERS_TARGET = URIRef(KSH + "coversTarget")
MUTUALLY_EXCLUSIVE = URIRef(KSH + "mutuallyExclusive")
WEATHER_TARGET = URIRef(WX + "WeatherObservationTarget")
UNDER_PROTOCOL = URIRef(WX + "underProtocol")
SETTLEMENT_SOURCE = URIRef(KSH + "settlementSource")
SOURCE_PROTOCOL = URIRef(KSH + "sourceProtocol")
IN_SERIES = URIRef(KSH + "inSeries")
HAS_COMPARATOR = URIRef(FM + "hasComparator")
FLOOR_VALUE = URIRef(FM + "floorValue")
CAP_VALUE = URIRef(FM + "capValue")
HAS_INPUT = URIRef(FM + "hasInput")
PAYOUT = URIRef(KSH + "Payout")
RESOLUTION = URIRef(KSH + "Resolution")
BINARY_CONTRACT = URIRef(KSH + "BinaryContract")
YES_CONTRACT = URIRef(KSH + "YesContract")
NO_CONTRACT = URIRef(KSH + "NoContract")
CONTRACT_IN_MARKET = URIRef(KSH + "contractInMarket")
CONTRACT_QUANTITY = URIRef(KSH + "contractQuantity")
PAYOUT_AMOUNT = URIRef(KSH + "payoutAmountCents")
RESOLVES_TO = URIRef(KSH + "resolvesTo")
TRADE = URIRef(KSH + "Trade")
HAS_OUTPUT = URIRef(FM + "hasOutput")
HELD_BY = URIRef(KSH + "heldBy")
HOLDER_OBLIGATION = URIRef(KSH + "ContractHolderObligation")
REALIZES = URIRef(BFO + "BFO_0000055")
INHERES_IN = URIRef(BFO + "BFO_0000197")
RESOLVED_YES = URIRef(KSH + "ResolvedYes")
RESOLVED_NO = URIRef(KSH + "ResolvedNo")
# A binary contract pays one dollar, stated in the cents its prices are stated in.
CENTS_PER_CONTRACT = 100

# Properties whose presence means a unit is mandatory rather than optional.
VALUE_PROPS = (URIRef(FM + "floorValue"), URIRef(FM + "capValue"),
               URIRef(FM + "realizedValue"), SETTLEMENT_VALUE)


def check_dimensions(g: Graph) -> None:
    """Check unit coherence across each proposition/target/datum chain.

    Two different strengths, because two different questions:

    * Where values are COMPARED -- a proposition's threshold against its target, a
      datum's reading against the target it reports for -- the units must be
      *identical*. Dimensional compatibility is not enough: a 82 degF threshold and a
      target reported in degC share a dimension vector and are still a bug. Same
      dimension but different unit means a conversion is needed and has not been
      recorded, which is worth failing on rather than assuming.

    * Where a unit is merely being CHOSEN from those a variable is reported in, only
      the dimension has to line up, since a target may legitimately use a valid unit
      that is not on the conventional list.

    Dimensional equality remains necessary but not sufficient in general: snowfall
    depth and liquid precipitation are both lengths, percent and degrees are both
    dimensionless. This catches unit mistakes, not quantity confusions.
    """

    def dim(unit_iri):
        dims = list(g.objects(unit_iri, DIM_VECTOR))
        if not dims:
            fail(f"unit has no qudt:hasDimensionVector, cannot check: {unit_iri}")
            return None
        return dims[0]

    def unit_of(entity):
        """None means "not checkable", and says why first.

        fm:hasUnit is functional in OWL, but this runs without a reasoner, so two
        units here is a wrong answer rather than an inconsistency. A missing unit is
        at least as likely an authoring slip as a wrong one, so a value with no unit
        fails instead of quietly dropping out of the comparison.
        """
        units = list(g.objects(entity, HAS_UNIT))
        if len(units) > 1:
            fail(
                f"ambiguous unit: {entity} has {len(units)} fm:hasUnit values "
                f"({sorted(str(u) for u in units)}). fm:hasUnit is functional, so "
                f"this is an inconsistency the reasoner would catch; without one, "
                f"the unit check would compare against whichever came first."
            )
            return None
        if not units:
            # Membership, not truthiness -- a zero value is still a value, and
            # truthiness let it dodge the missing-unit failure.
            if any((entity, p, None) in g for p in VALUE_PROPS):
                fail(
                    f"missing unit: {entity} carries a numeric value but no "
                    f"fm:hasUnit, so it cannot be compared against anything"
                )
            return None
        return units[0]

    compared = 0

    def check_identical(left, left_unit, right, right_unit, phrasing):
        """Units on either side of a comparison must be the same unit, not merely
        the same dimension."""
        if left_unit is None or right_unit is None:
            # One side declared a unit and the other did not. Whatever unit_of
            # already reported, the comparison itself is now unverifiable.
            if left_unit is not None or right_unit is not None:
                missing = right if right_unit is None else left
                fail(
                    f"missing unit ({phrasing}): {missing} has no usable fm:hasUnit, "
                    f"so this comparison cannot be checked"
                )
            return
        if left_unit == right_unit:
            return
        ld, rd = dim(left_unit), dim(right_unit)
        if ld and rd and ld == rd:
            fail(
                f"unit mismatch ({phrasing}): {left} uses {left_unit} but {right} "
                f"uses {right_unit}. Same dimension ({ld}), so these are convertible "
                f"-- but no conversion is recorded, and the raw values are not comparable."
            )
        else:
            fail(
                f"dimension mismatch ({phrasing}): {left} uses {left_unit} ({ld}) "
                f"but {right} uses {right_unit} ({rd}). Not convertible."
            )

    # A proposition's threshold is compared against its target's realized value.
    for prop, target in g.subject_objects(HAS_SUBJECT):
        pu, tu = unit_of(prop), unit_of(target)
        check_identical(prop, pu, target, tu, "proposition threshold vs target")
        compared += 1

    # A datum's reading is the value the target's proposition gets evaluated against.
    for datum, target in g.subject_objects(REPORTS_FOR):
        du, tu = unit_of(datum), unit_of(target)
        check_identical(datum, du, target, tu, "datum vs target")
        compared += 1

    # The exchange's own number, against the target the market settles on. It
    # reaches the target through the market's proposition rather than directly,
    # so no earlier loop sees it -- and ksh:settlementValue is a sub-property of
    # fm:realizedValue, which rdflib does not follow.
    settlement_compared = 0
    for resolution, market in g.subject_objects(RESOLUTION_OF):
        # Membership, not truthiness: bool(Literal(0)) is False, so a settlement
        # of zero used to read as absent and skip the comparison entirely.
        if (resolution, SETTLEMENT_VALUE, None) not in g:
            continue
        for prop in g.objects(market, EXPRESSES):
            for target in g.objects(prop, HAS_SUBJECT):
                check_identical(resolution, unit_of(resolution),
                                target, unit_of(target),
                                "settlement value vs target")
                settlement_compared += 1
    if EXAMPLES and not settlement_compared:
        fail(
            "no settlement value reaches a target, so the settlement-value check "
            "matched nothing; the resolutionOf or expressesProposition chain is broken"
        )
    compared += settlement_compared

    # A target's unit should be dimensionally compatible with its variable's
    # conventional units. Advisory: a target may use an unlisted but valid unit.
    for target, variable in g.subject_objects(TARGET_VAR):
        tu = unit_of(target)
        if tu is None:
            continue
        conventional = list(g.objects(variable, CONVENTIONAL_UNIT))
        if not conventional:
            continue
        td = dim(tu)
        cdims = {d for cu in conventional if (d := dim(cu)) is not None}
        if td and cdims and td not in cdims:
            fail(
                f"dimension mismatch: target {target} uses {tu} ({td}) but variable "
                f"{variable} is conventionally reported in {sorted(str(c) for c in cdims)}"
            )
        compared += 1

    notes.append(f"unit coherence: {compared} comparison pair(s) checked")


LEAD_HOURS = URIRef(WX + "leadTimeHours")
ISSUANCE = URIRef(WX + "issuanceTime")
FORECAST_FOR = URIRef(WX + "forecastFor")
OVER_INTERVAL = URIRef(FM + "overTemporalInterval")
FIRST_INSTANT = URIRef(BFO + "BFO_0000222")
INSTANT_DT = URIRef(FM + "instantDateTime")


def check_lead_times(g: Graph) -> None:
    """wx:leadTimeHours is derived, so verify it against what it is derived from.

    A stored derived value is a liability: it goes stale the moment either input
    moves, and nothing about the graph complains. Since CQ6 groups by lead time,
    a wrong value there does not error, it silently reassigns forecasts to the
    wrong bucket and produces a plausible calibration table.
    """
    from datetime import datetime

    checked = 0
    for forecast, stated in g.subject_objects(LEAD_HOURS):
        issued = list(g.objects(forecast, ISSUANCE))
        targets = list(g.objects(forecast, FORECAST_FOR))
        if not issued or not targets:
            fail(f"{forecast} has a lead time but no issuance time or no target")
            continue
        starts = [
            dt
            for target in targets
            for interval in g.objects(target, OVER_INTERVAL)
            for instant in g.objects(interval, FIRST_INSTANT)
            for dt in g.objects(instant, INSTANT_DT)
        ]
        if not starts:
            fail(f"{forecast}: cannot resolve the first instant of its target's interval")
            continue

        # wx:forecastFor is not functional and the interval walk fans out, so more
        # than one candidate means the stated lead time is derived from whichever
        # rdflib happened to yield first -- an arbitrary answer, not a checked one.
        if len(targets) > 1 or len({str(i) for i in issued}) > 1 or len({str(x) for x in starts}) > 1:
            fail(
                f"{forecast}: lead time is ambiguous -- {len(issued)} issuance time(s), "
                f"{len(targets)} target(s), {len(starts)} interval start(s). "
                f"Cannot say which pair wx:leadTimeHours was derived from."
            )
            continue

        # A naive datetime subtracted from an aware one raises rather than returning
        # a wrong number, and an uncaught raise costs the operator every later check.
        try:
            issued_dt = datetime.fromisoformat(str(issued[0]))
            start_dt = datetime.fromisoformat(str(starts[0]))
            actual = (start_dt - issued_dt).total_seconds() / 3600.0
        except (ValueError, TypeError) as exc:
            fail(
                f"{forecast}: cannot measure lead time from issuance {issued[0]!r} to "
                f"interval start {starts[0]!r}: {exc}. Both need a UTC offset -- see "
                f"the fm:instantDateTime scope note."
            )
            continue
        if abs(float(stated) - actual) > 0.01:
            fail(
                f"{forecast}: wx:leadTimeHours says {stated} but issuance "
                f"{issued_dt.isoformat()} to interval start {start_dt.isoformat()} "
                f"is {actual:.3f} hours"
            )
        checked += 1

    notes.append(f"lead times: {checked} checked against issuance and interval start")


def check_current_assessments(g: Graph) -> None:
    """At most one assessment per proposition may rest on a live record.

    Two make the graph ambiguous rather than wrong: CQ6a and CQ6b aggregate over
    assessments, so a duplicate silently inflates n and shifts every calibration
    statistic while every other check stays green. The correction case is the
    legitimate two-assessment shape, and it is exempt by construction -- the
    settlement-era record is superseded, so only the later one is current.
    """
    superseded = set(g.objects(None, SUPERSEDES))
    by_proposition: dict[URIRef, list[URIRef]] = {}
    for assessment, proposition in g.subject_objects(ASSESSES):
        records = list(g.objects(assessment, BASED_ON_RECORD))
        if records and all(r in superseded for r in records):
            continue
        by_proposition.setdefault(proposition, []).append(assessment)

    for proposition, assessments in sorted(by_proposition.items(), key=lambda kv: str(kv[0])):
        if len(assessments) > 1:
            fail(
                f"more than one current assessment: {proposition} is assessed by "
                f"{sorted(str(a) for a in assessments)}, none of them resting on a "
                f"superseded record. Calibration counts assessments, so this "
                f"double-counts the proposition rather than contradicting itself."
            )
    if EXAMPLES and not by_proposition:
        fail(
            "no proposition has a current assessment, so the assessment check "
            "matched nothing; the assessesProposition chain is broken"
        )
    notes.append(f"{len(by_proposition)} proposition(s) checked for a single current assessment")


def check_scores(g: Graph) -> None:
    """A stored Brier score is derived, so check it against its inputs.

    Same reasoning as wx:leadTimeHours: a derived value stored for query
    convenience goes stale the moment either input moves, and nothing about the
    graph complains. The outcome must come from an assessment resting on a live
    record -- scoring against a superseded one measures what the exchange did
    rather than what the record says, which is the one thing fm:scoredAgainst
    exists to make visible.
    """
    superseded = set(g.objects(None, SUPERSEDES))
    checked = 0
    for score, stated in g.subject_objects(SCORE_VALUE):
        if (score, USES_SCORING_RULE, BRIER_SCORE) not in g:
            continue  # only the Brier arithmetic is reproducible here
        assignments = list(g.objects(score, SCORES_ASSIGNMENT))
        assessments = list(g.objects(score, SCORED_AGAINST))
        if len(assignments) != 1 or len(assessments) != 1:
            fail(
                f"{score}: cannot check a Brier score with {len(assignments)} "
                f"assignment(s) and {len(assessments)} assessment(s); exactly one "
                f"of each is needed to reproduce the arithmetic"
            )
            continue
        for record in g.objects(assessments[0], BASED_ON_RECORD):
            if record in superseded:
                fail(
                    f"score rests on a superseded record: {score} is scored "
                    f"against {assessments[0]}, which read {record}. That measures "
                    f"the outcome the record has since retracted."
                )
        probs = list(g.objects(assignments[0], PROBABILITY_VALUE))
        truths = list(g.objects(assessments[0], ASSESSED_TRUTH_VALUE))
        if len(probs) != 1 or len(truths) != 1:
            fail(f"{score}: its assignment or assessment does not carry exactly one value")
            continue
        if truths[0] not in (TRUE_VALUE, FALSE_VALUE):
            fail(
                f"{score}: scored against {assessments[0]}, whose assessed truth "
                f"value is {truths[0]}, not fm:True or fm:False. A Brier score "
                f"against an indeterminate outcome is undefined, not zero."
            )
            continue
        outcome = 1.0 if truths[0] == TRUE_VALUE else 0.0
        # Same reasoning as check_lead_times: an uncaught raise here costs the
        # operator every later check.
        try:
            expected = (float(probs[0]) - outcome) ** 2
            stated_value = float(stated)
        except (ValueError, TypeError) as exc:
            fail(
                f"{score}: cannot reproduce the arithmetic -- probability "
                f"{probs[0]!r} or score {stated!r} is not numeric ({exc})"
            )
            continue
        if abs(stated_value - expected) > 1e-9:
            fail(
                f"Brier score mismatch: {score} says {stated} but probability "
                f"{probs[0]} against outcome {outcome:.0f} is {expected:.4f}"
            )
        checked += 1
    if EXAMPLES and not checked:
        fail(
            "no Brier score was checked against its inputs, so the score check "
            "matched nothing; the usesScoringRule or scoresAssignment chain is broken"
        )
    notes.append(f"{checked} Brier score(s) checked against their inputs")


def check_protocols(g: Graph) -> None:
    """A target names its protocol, and the exchange settles on that same protocol.

    The class definition of wx:WeatherObservationTarget names four components and the
    axioms constrained three, so a target carrying no wx:underProtocol at all parsed
    clean. The reasoner does not catch it either: under the open-world assumption a
    missing protocol reads as "there is one, unnamed", so absence has to be checked
    here rather than left to HermiT. The definedness check added after the migration
    catches a protocol IRI that no longer resolves; it cannot catch one never asserted.

    The second rule is the source/protocol split. ksh:settlementSource names the
    publication the exchange consults, wx:underProtocol names how the value is
    determined, and nothing tied them together -- so a market could settle on The
    Weather Company while its proposition named an NWS-determined target. That is the
    2026-08-14 migration with the schema in place of the data, and it is the failure
    this ontology's central claim exists to make visible.
    """
    targets = {
        s for s, t in g.subject_objects(RDF.type)
        if t == WEATHER_TARGET or WEATHER_TARGET in ancestors(g, t)
    }
    for target in sorted(targets, key=str):
        protocols = list(g.objects(target, UNDER_PROTOCOL))
        if len(protocols) != 1:
            fail(
                f"target does not name exactly one protocol: {target} has "
                f"{len(protocols)} wx:underProtocol value(s). Protocol is a component "
                f"of the target, not an annotation on it, so without exactly one the "
                f"target does not fix a quantity."
            )
    if EXAMPLES and not targets:
        fail(
            "no observation target was found, so the target-protocol check matched "
            "nothing; the wx:WeatherObservationTarget typing is broken"
        )
    notes.append(f"{len(targets)} observation target(s) checked for a protocol")

    checked = 0
    reported: set[URIRef] = set()
    for market, grouping in g.subject_objects(IN_EVENT_GROUPING):
        # ksh:settlementSource attaches to a listing; a market inherits it from its
        # grouping or series unless it carries its own. Precedence, not union -- a
        # grouping overriding its series is how the 2026-08-14 migration is modelled,
        # and unioning the levels rejects that correct model as ambiguous.
        levels = ([market], [grouping], list(g.objects(grouping, IN_SERIES)))
        sources: set[URIRef] = set()
        for depth, holders in enumerate(levels):
            sources = {s for h in holders for s in g.objects(h, SETTLEMENT_SOURCE)}
            if sources:
                break
        if len(sources) != 1:
            # Only a market-level defect is the market's own; one resolved higher
            # belongs to the grouping, and every market under it would repeat it.
            key = market if depth == 0 else grouping
            if key not in reported:
                reported.add(key)
                fail(
                    f"market does not resolve to exactly one settlement source: "
                    f"{market} resolves to {len(sources)} at the most specific level "
                    f"carrying one ({sorted(str(s) for s in sources)}), so what it "
                    f"settles on cannot be compared with what its proposition is about"
                )
            continue
        source = next(iter(sources))
        source_protocols = set(g.objects(source, SOURCE_PROTOCOL))
        if len(source_protocols) != 1:
            if source not in reported:
                reported.add(source)
                fail(
                    f"settlement source does not name exactly one protocol: {source} "
                    f"has {len(source_protocols)} ksh:sourceProtocol value(s), so no "
                    f"market settling through it can be checked against the "
                    f"determination it settles on"
                )
            continue
        settles_under = next(iter(source_protocols))
        for prop in g.objects(market, EXPRESSES):
            for subject in g.objects(prop, HAS_SUBJECT):
                for protocol in g.objects(subject, UNDER_PROTOCOL):
                    checked += 1
                    if protocol != settles_under:
                        fail(
                            f"market settles on a different protocol than its "
                            f"proposition names: {market} settles through {source} "
                            f"under {settles_under}, but {prop} is about {subject} "
                            f"under {protocol}"
                        )
    if EXAMPLES and not checked:
        fail(
            "no market reaches a target protocol, so the settlement-protocol check "
            "matched nothing; the settlementSource or sourceProtocol chain is broken"
        )
    notes.append(f"{checked} market/protocol pair(s) checked for settlement agreement")


def check_grouping_coherence(g: Graph) -> None:
    """An event grouping's markets partition the values of ONE target.

    Two things follow, and neither was checked. A market whose proposition names a
    different target than its grouping covers is the same drift the forecast-target
    check exists for, one tier up. And in a grouping asserted mutually exclusive,
    two brackets that overlap contradict that assertion -- CQ5 sums their implied
    probabilities and reports an overshoot without ever noticing.

    Exhaustiveness is NOT checked. Whether the brackets leave a gap depends on the
    reporting increment of the protocol -- whole degrees Fahrenheit here, stated in
    prose and nowhere in the model -- so the check would be guessing. See README.
    """
    inf = float("inf")
    # Keyed by comparator IRI: (needs_floor, needs_cap, bounds-from-floor/cap). A
    # comparator that gates on one dict and indexes another can add a key to only
    # one and turn a validation failure into a KeyError -- keeping both under one
    # key makes that impossible.
    COMPARATORS = {
        URIRef(FM + "Between"):            (True, True, lambda f, c: (f, True, c, True)),
        URIRef(FM + "LessThanOrEqual"):    (False, True, lambda f, c: (-inf, False, c, True)),
        URIRef(FM + "LessThan"):           (False, True, lambda f, c: (-inf, False, c, False)),
        URIRef(FM + "GreaterThanOrEqual"): (True, False, lambda f, c: (f, True, inf, False)),
        URIRef(FM + "GreaterThan"):        (True, False, lambda f, c: (f, False, inf, False)),
        URIRef(FM + "EqualTo"):            (True, False, lambda f, c: (f, True, f, True)),
    }

    def interval(prop):
        """None means not evaluable -- fm:Custom, or a threshold not stated."""
        comps = list(g.objects(prop, HAS_COMPARATOR))
        if len(comps) != 1 or comps[0] not in COMPARATORS:
            return None
        needs_floor, needs_cap, bounds = COMPARATORS[comps[0]]
        floors = list(g.objects(prop, FLOOR_VALUE))
        caps = list(g.objects(prop, CAP_VALUE))
        if len(floors) > 1 or len(caps) > 1:
            fail(f"{prop}: more than one threshold value, so its interval is ambiguous")
            return None
        if (needs_floor and not floors) or (needs_cap and not caps):
            fail(f"{prop}: its comparator needs a threshold value that is not stated")
            return None
        try:
            floor_v = float(floors[0]) if floors else None
            cap_v = float(caps[0]) if caps else None
        except ValueError:
            fail(f"{prop}: its threshold value is not numeric")
            return None
        # Checked whether or not the comparator consumes both: an inverted pair is
        # unsatisfiable, and its overlap results against every other bracket are
        # meaningless rather than merely wrong.
        if floor_v is not None and cap_v is not None and floor_v > cap_v:
            fail(
                f"{prop}: floor {floor_v} is above cap {cap_v}, so no value "
                f"satisfies it and its brackets cannot be compared"
            )
            return None
        return bounds(floor_v, cap_v)

    # Compares raw floor/cap numbers with no unit check of its own -- sound only
    # because check_dimensions already forces a proposition's unit to equal its
    # target's, and the market-covers-target rule above puts every bracket in a
    # grouping on one target. Weaken either and this starts comparing numbers in
    # different units.
    def overlaps(a, b):
        lo1, lo1_in, hi1, hi1_in = a
        lo2, lo2_in, hi2, hi2_in = b
        left = lo1 < hi2 or (lo1 == hi2 and lo1_in and hi2_in)
        right = lo2 < hi1 or (lo2 == hi1 and lo2_in and hi1_in)
        return left and right

    checked = 0
    groupings: dict[URIRef, list] = {}
    ambiguous: set[URIRef] = set()
    for market, grouping in g.subject_objects(IN_EVENT_GROUPING):
        # ksh:coversTarget is not functional and absence used to skip the check.
        # Neither zero nor two targets can be compared against, and both break the
        # single-target premise overlaps() below relies on.
        covered = list(g.objects(grouping, COVERS_TARGET))
        if len(covered) != 1 and grouping not in ambiguous:
            ambiguous.add(grouping)
            fail(
                f"grouping does not cover exactly one target: {grouping} holds "
                f"markets but has {len(covered)} ksh:coversTarget value(s) "
                f"({sorted(str(c) for c in covered)}), so its brackets cannot be "
                f"checked against a target or against each other."
            )
        for prop in g.objects(market, EXPRESSES):
            for subject in g.objects(prop, HAS_SUBJECT):
                checked += 1
                if len(covered) == 1 and subject not in covered:
                    fail(
                        f"market covers a different target than its grouping: "
                        f"{market} expresses {prop} about {subject}, but "
                        f"{grouping} covers {sorted(str(c) for c in covered)}"
                    )
            if (grouping, MUTUALLY_EXCLUSIVE, Literal(True)) in g:
                iv = interval(prop)
                if iv is not None:
                    groupings.setdefault(grouping, []).append((prop, iv))

    for grouping, entries in sorted(groupings.items(), key=lambda kv: str(kv[0])):
        for i, (prop_a, iv_a) in enumerate(entries):
            for prop_b, iv_b in entries[i + 1:]:
                if prop_a == prop_b:
                    continue
                if overlaps(iv_a, iv_b):
                    fail(
                        f"overlapping brackets: {grouping} is asserted mutually "
                        f"exclusive, but {prop_a} and {prop_b} can both be true. "
                        f"CQ5 would sum their implied probabilities regardless."
                    )

    if EXAMPLES and not checked:
        fail(
            "no market reaches a proposition subject, so the grouping check "
            "matched nothing; the inEventGrouping or expressesProposition chain "
            "is broken"
        )
    notes.append(f"{checked} market/grouping pair(s) checked for target agreement")


def check_payouts(g: Graph) -> None:
    """A payout pays the side the resolution determined, the holder who held it, what it owes.

    The trading layer was vocabulary with no instances through 0.7.1, so nothing
    connected it to settlement. It is a short walk and an easy one to get wrong:
    a payout names a resolution and a lot of contracts, and it is only correct if
    the lot is on the winning side, in the market that resolved, held by the party
    whose obligation the payout realizes, for one dollar a contract. Paying the
    losing side is the trading-layer form of the mistake fm:scoredAgainst exists
    to expose -- an entry that looks settled, is arithmetically self-consistent,
    and rests on the wrong determination. Paying the right amount to the wrong
    party is the same mistake about the other end of the transfer: the lot names
    its holder, the payout reaches one only through the obligation it realizes,
    and nothing but this compares them.

    Voided and scalar outcomes are skipped rather than guessed at: neither pays a
    fixed sum per contract on one side, and no example produces one.
    """
    reached = 0   # payouts naming a resolution and a lot -- what the coverage guard is about
    verified = 0  # ...and whose side, recipient and amount were actually compared
    for payout in instances_of(g, PAYOUT):
        inputs = list(g.objects(payout, HAS_INPUT))
        resolutions = [i for i in inputs if RESOLUTION in types_of(g, i)]
        lots = [i for i in inputs if BINARY_CONTRACT in types_of(g, i)]
        if len(resolutions) != 1 or len(lots) != 1:
            fail(
                f"payout does not name one resolution and one contract lot: "
                f"{payout} has {len(resolutions)} resolution(s) and {len(lots)} "
                f"lot(s) among its inputs, so what it pays for cannot be checked"
            )
            continue
        resolution, lot = resolutions[0], lots[0]
        reached += 1

        # Same market, or the payout is settling one market's contracts against
        # another's determination. Both are functional, so more than one value is
        # itself the defect.
        markets = set(g.objects(resolution, RESOLUTION_OF))
        held_in = set(g.objects(lot, CONTRACT_IN_MARKET))
        if markets != held_in or len(markets) != 1:
            fail(
                f"payout crosses markets: {payout} pays {lot}, in "
                f"{sorted(str(m) for m in held_in)}, on {resolution}, which "
                f"resolves {sorted(str(m) for m in markets)}"
            )
            continue

        outcomes = list(g.objects(resolution, RESOLVES_TO))
        if len(outcomes) != 1:
            fail(
                f"payout rests on a resolution with {len(outcomes)} outcome(s): "
                f"{resolution}, so the paying side is undetermined"
            )
            continue
        outcome = outcomes[0]
        winning = {RESOLVED_YES: YES_CONTRACT, RESOLVED_NO: NO_CONTRACT}.get(outcome)
        if winning is None:
            notes.append(f"payout skipped: {payout} rests on outcome {outcome}")
            continue

        # A lot with no side, or with both, is a different defect than a lot on the
        # losing one, and saying "pays the losing side" of it sends the reader after
        # the wrong fix. Both sides at once is what ksh:YesContract's disjointness
        # makes a HermiT inconsistency; this is the Java-free half of that guard.
        sides = types_of(g, lot) & {YES_CONTRACT, NO_CONTRACT}
        if len(sides) != 1:
            fail(
                f"payout pays a lot whose side is not determinate: {lot} is typed "
                f"as {len(sides)} of ksh:YesContract, ksh:NoContract, so which side "
                f"{resolution} pays cannot be read off it"
            )
        elif winning not in sides:
            fail(
                f"payout pays the losing side: {payout} pays {lot}, but "
                f"{resolution} resolved to {outcome}, which pays holders of "
                f"{winning}"
            )

        obligations = [
            o for o in g.objects(payout, REALIZES) if HOLDER_OBLIGATION in types_of(g, o)
        ]
        holders = set(g.objects(lot, HELD_BY))
        if len(obligations) != 1 or len(holders) != 1:
            fail(
                f"payout recipient cannot be checked: {payout} realizes "
                f"{len(obligations)} contract holder obligation(s) and {lot} names "
                f"{len(holders)} holder(s)"
            )
        else:
            bearers = set(g.objects(obligations[0], INHERES_IN))
            if bearers != holders:
                fail(
                    f"payout pays the wrong party: {payout} realizes "
                    f"{obligations[0]}, which inheres in "
                    f"{sorted(str(b) for b in bearers)}, but {lot} is held by "
                    f"{sorted(str(h) for h in holders)}"
                )

        quantities = list(g.objects(lot, CONTRACT_QUANTITY))
        amounts = list(g.objects(payout, PAYOUT_AMOUNT))
        if len(quantities) != 1 or len(amounts) != 1:
            fail(
                f"payout amount cannot be checked: {lot} states "
                f"{len(quantities)} quantity value(s) and {payout} states "
                f"{len(amounts)} amount(s)"
            )
            continue
        try:
            expected = float(quantities[0]) * CENTS_PER_CONTRACT
            stated = float(amounts[0])
        except ValueError:
            fail(f"payout amount or contract quantity is not numeric: {payout}")
            continue
        if abs(stated - expected) > 1e-9:
            fail(
                f"payout amount disagrees with what it pays for: {payout} states "
                f"{stated} cents, but {lot} is {quantities[0]} contract(s) at "
                f"{CENTS_PER_CONTRACT} cents, which is {expected}"
            )
        verified += 1

    if EXAMPLES and not reached:
        fail(
            "no payout reaches a resolution and a contract lot, so the payout "
            "check matched nothing; the trading layer is unexercised again"
        )
    # Counted after the comparisons, not on arrival: a payout on a scalar or voided
    # outcome leaves the loop before its side and amount are ever compared, and
    # reporting it as checked is how a skip reads as a pass.
    notes.append(f"{verified} payout(s) checked against their resolution, holder and lot")


def check_trades(g: Graph) -> None:
    """A match outputs two lots: opposite sides, equal quantity.

    "The two sides of a match sum to the payout" is what collateralises a binary
    market, and both CQ8's derived price and ksh:executionPriceCents' scope note
    rest on it. Nothing enforced it: ksh:contractQuantity was read by check_payouts
    alone, and only for a lot that had a payout, so the losing lot could state any
    quantity at all and only a .expected diff would notice.
    """
    checked = 0
    for trade in instances_of(g, TRADE):
        lots = [o for o in g.objects(trade, HAS_OUTPUT) if BINARY_CONTRACT in types_of(g, o)]
        if len(lots) != 2:
            fail(
                f"trade does not output two contract lots: {trade} outputs "
                f"{len(lots)}, so the two sides of the match cannot be compared"
            )
            continue
        checked += 1
        sides = [types_of(g, lot) & {YES_CONTRACT, NO_CONTRACT} for lot in lots]
        if any(len(s) != 1 for s in sides) or sides[0] == sides[1]:
            fail(
                f"trade's two lots are not one yes and one no: {trade} outputs "
                f"{sorted(str(lot) for lot in lots)}"
            )
            continue
        quantities = [list(g.objects(lot, CONTRACT_QUANTITY)) for lot in lots]
        if any(len(q) != 1 for q in quantities):
            fail(
                f"trade's lot quantities cannot be compared: {trade} outputs lots "
                f"stating {[len(q) for q in quantities]} quantity value(s)"
            )
            continue
        try:
            left, right = (float(q[0]) for q in quantities)
        except ValueError:
            fail(f"trade states a non-numeric contract quantity: {trade}")
            continue
        if left != right:
            fail(
                f"trade's two lots state different quantities: {trade} outputs "
                f"{lots[0]} at {quantities[0][0]} and {lots[1]} at "
                f"{quantities[1][0]}, but one match made both"
            )

    if EXAMPLES and not checked:
        fail(
            "no trade outputs two contract lots, so the match check matched "
            "nothing; the trading layer is unexercised again"
        )
    notes.append(f"{checked} trade(s) checked for opposite sides and equal quantity")


def main() -> int:
    g = Graph()

    # 1. parse
    for rel in MODULES:
        path = SRC / rel
        if not path.exists():
            fail(f"missing module: {rel}")
            continue
        try:
            g.parse(path, format="turtle")
        except Exception as exc:  # noqa: BLE001
            fail(f"parse error in {rel}: {exc}")
    if failures:
        return report()
    notes.append(f"parsed {len(MODULES)} modules, {len(g)} triples")

    ex = Graph()
    ex += g
    for path in EXAMPLES:
        try:
            ex.parse(path, format="turtle")
        except Exception as exc:  # noqa: BLE001
            fail(f"parse error in {path.name}: {exc}")
    notes.append(f"parsed {len(EXAMPLES)} example files, {len(ex)} triples with schema")

    # Collected from rdfs:subClassOf as well as `a owl:Class`: a hand-authored class
    # that only ever appears as the subject or parent of a subClassOf is a plausible
    # slip, and taking the declared ones alone made it invisible rather than unrooted.
    our_classes = sorted(
        {s for s in g.subjects(RDF.type, OWL.Class) if is_ours(s)}
        | {s for s in g.subjects(RDFS.subClassOf, None) if is_ours(s)}
        | {o for o in g.objects(None, RDFS.subClassOf) if is_ours(o)},
        key=str,
    )
    notes.append(f"{len(our_classes)} minted classes")

    # 2. BFO grounding
    tally: dict[str, int] = {}
    for cls in our_classes:
        anc = ancestors(g, cls)
        if ENTITY not in anc:
            fail(f"not grounded in BFO: {cls} (ancestors: {sorted(str(a) for a in anc)})")
            continue
        branch = [name for iri, name in BRANCHES.items() if iri in anc or iri == cls]
        if not branch:
            fail(f"grounded in bfo:entity but in no known branch: {cls}")
        else:
            for b in branch:
                tally[b] = tally.get(b, 0) + 1

    # 2b. External classes we bridge into the hierarchy must be grounded too.
    # QUDT makes no upper-level commitment, so without the bridge axioms in core.ttl
    # its classes float under owl:Thing. The per-namespace check above would not
    # notice, because these are not in our namespace.
    # Derived from the subset rather than hard-coded, because the two IRIs named here
    # originally were the two that happened to be floating that day; the generator
    # later added a third (qudt:QuantityKindDimensionVector) and the check missed it.
    qudt_classes = sorted(
        (s for s in g.subjects(RDF.type, OWL.Class) if str(s).startswith(QUDT)), key=str
    )
    for iri in qudt_classes:
        if ENTITY not in ancestors(g, iri):
            fail(f"bridged external class not grounded in BFO: {iri}")
    notes.append(f"{len(qudt_classes)} bridged QUDT class(es) checked for BFO grounding")

    # 3. continuant / occurrent disjointness
    for cls in our_classes:
        anc = ancestors(g, cls)
        if CONTINUANT in anc and OCCURRENT in anc:
            fail(f"both continuant and occurrent: {cls}")

    # 4. properties used in examples are declared
    declared = {
        s
        for t in (OWL.ObjectProperty, OWL.DatatypeProperty, OWL.AnnotationProperty)
        for s in g.subjects(RDF.type, t)
    }
    builtin_ok = {RDF.type, RDFS.label, RDFS.subClassOf, OWL.imports, OWL.versionIRI}
    for path in EXAMPLES:
        eg = Graph()
        try:
            eg.parse(path, format="turtle")
        except Exception:  # noqa: BLE001
            continue  # already reported by the parse loop above; do not lose report()
        for _, p, _ in eg:
            if p in builtin_ok or p in declared:
                continue
            if str(p).startswith(BFO) or str(p).startswith(str(SKOS)):
                continue
            if str(p).startswith("http://purl.org/dc/"):
                continue
            fail(f"{path.name} uses undeclared property: {p}")

    # 4b. individuals referenced in the examples are defined in them
    #
    # Checked against the union of the example files, not per file, because they
    # import each other: the synthetic dataset legitimately references the site and
    # protocol defined in the worked example. Schema IRIs are in scope too: the
    # grounding and documentation checks only see classes and properties, so a
    # deleted individual (ksh:Settled) left dangling in an example passed silently,
    # and rdfs:range made the reasoner infer its type rather than object.
    #
    # This exists because re-pointing the settlement source renamed a protocol
    # individual and verification-synthetic.ttl went on referencing the old IRI for
    # all 40 days. Nothing failed. The targets silently lost their protocol, which
    # for an ontology whose central rule is "the observation target carries the
    # protocol" is the worst available place to lose one.
    in_scope = ("https://w3id.org/forecast-market-ontology/examples/",) + OUR_NS
    defined = {t for t in ex.subjects() if isinstance(t, URIRef)}
    dangling = sorted(
        {
            str(o)
            for _, _, o in ex
            if isinstance(o, URIRef)
            and str(o).startswith(in_scope)
            and o not in defined
        }
    )
    for iri in dangling:
        fail(f"undefined term referenced in examples: {iri}")
    referenced = {
        o
        for _, _, o in ex
        if isinstance(o, URIRef) and str(o).startswith(in_scope)
    }
    notes.append(f"{len(referenced)} referenced IRI(s) checked for definedness")

    # 5. documentation coverage
    for term in our_classes + sorted(
        {
            s
            for t in (OWL.ObjectProperty, OWL.DatatypeProperty)
            for s in g.subjects(RDF.type, t)
            if is_ours(s)
        },
        key=str,
    ):
        if not any(g.objects(term, RDFS.label)):
            fail(f"no rdfs:label: {term}")
        # Was advisory, and a scopeNote counted as a definition. Both the module
        # docstring and CLAUDE.md promise this fails, so make it fail: a scope note
        # says "why here, not there", which is not a statement of what the term means.
        if not any(g.objects(term, SKOS.definition)):
            fail(f"no skos:definition: {term}")

    # Advisory, never a failure. A term with no instance is a term nobody has
    # watched work; the trading layer is deliberately in that state and README
    # says so, but the count should be visible on every run rather than needing
    # an audit to find.
    # Subtract types asserted by the schema graph alone: a class instantiated only
    # by a schema-level individual (fm:BrierScore, ksh:MarketStatus, ...) is not
    # exercised by an example, and counting it overclaimed the figure README cites
    # as the mechanism that keeps the trading-layer gap visible.
    schema_instantiated = {t for t in g.objects(None, RDF.type) if is_ours(t)}
    instantiated = {t for t in ex.objects(None, RDF.type) if is_ours(t)} - schema_instantiated
    covered = sum(1 for c in our_classes if c in instantiated)
    notes.append(
        f"{covered}/{len(our_classes)} minted classes "
        f"have an instance in the examples"
    )

    if tally:
        notes.append("BFO branch distribution:")
        for name, count in sorted(tally.items(), key=lambda kv: -kv[1]):
            notes.append(f"  {count:3d}  {name}")

    # 6. Dimensional coherence.
    #
    # Checked on dimension vectors rather than quantity kinds because QUDT's
    # quantity-kind links are uneven (pressure units point at ForcePerArea, not
    # Pressure), while every unit carries exactly one dimension vector.
    #
    # Dimension equality is necessary, not sufficient: snowfall depth and liquid
    # precipitation are both lengths, and percent and degrees are both dimensionless.
    # This catches unit-system mistakes, not quantity confusions.
    check_dimensions(ex)
    check_lead_times(ex)
    check_current_assessments(ex)
    check_scores(ex)
    check_grouping_coherence(ex)
    check_protocols(ex)
    check_payouts(ex)
    check_trades(ex)

    # Domain sanity: the join the ontology exists for.
    #
    # All three conditions are required. An earlier version intersected "expressed
    # by a market" with "assigned any probability", which a bracket ladder satisfies
    # trivially -- every market has an implied probability, so the count rose with
    # the data while proving strictly less. The join is only demonstrated when the
    # SAME proposition carries a forecast probability AND a market-implied one.
    expressed = set(ex.objects(None, EXPRESSES))
    with_forecast = {
        p for s in ex.subjects(RDF.type, URIRef(FM + "ForecastProbability"))
        for p in ex.objects(s, URIRef(FM + "assignsProbabilityTo"))
    }
    with_market = {
        p for s in ex.subjects(RDF.type, URIRef(FM + "MarketImpliedProbability"))
        for p in ex.objects(s, URIRef(FM + "assignsProbabilityTo"))
    }
    joined = expressed & with_forecast & with_market
    # 6b. a forecast's target is the subject of the propositions it scores
    #
    # wx:forecastFor fixes what a forecast claims to be about; the proposition's
    # subject fixes what the market settles on. Nothing tied the two together, so
    # they could drift apart in silence -- and the examples aligned them only by
    # hand. wx:alternativeDeterminationOf turns the specific cross-authority case
    # from "mismatch" into a diagnosis. The relation licenses no substitution, so
    # being declared alternative determinations is not a defence; it is the point.
    alt_det = URIRef(WX + "alternativeDeterminationOf")
    has_part = URIRef(BFO + "BFO_0000178")
    assigns = URIRef(FM + "assignsProbabilityTo")
    forecast_prob = URIRef(FM + "ForecastProbability")
    scored = 0
    for forecast, ftarget in ex.subject_objects(FORECAST_FOR):
        for part in ex.objects(forecast, has_part):
            if (part, RDF.type, forecast_prob) not in ex:
                continue
            for prop in ex.objects(part, assigns):
                for subject in ex.objects(prop, HAS_SUBJECT):
                    scored += 1
                    if subject == ftarget:
                        continue
                    # Symmetry is asserted, not materialised -- rdflib does no
                    # reasoning here, so both directions are checked explicitly.
                    declared = (ftarget, alt_det, subject) in ex or (
                        subject,
                        alt_det,
                        ftarget,
                    ) in ex
                    detail = (
                        "; they are declared alternative determinations, so this "
                        "forecast is scored against a different authority than the "
                        "market settles on"
                        if declared
                        else ""
                    )
                    fail(
                        f"forecast target is not the subject of the proposition it "
                        f"scores: {forecast} is for {ftarget}, but {prop} has subject "
                        f"{subject}{detail}"
                    )
    if EXAMPLES and not scored:
        fail(
            "no forecast probability reaches a proposition subject, so the "
            "forecast-target check matched nothing; the has-part or "
            "assignsProbabilityTo chain is broken"
        )
    notes.append(f"{scored} forecast probability/proposition pair(s) checked for target agreement")

    if EXAMPLES and not joined:
        fail(
            "no proposition is expressed by a market AND carries both a forecast "
            "probability and a market-implied probability; the forecast/market join "
            "is not demonstrated"
        )
    elif joined:
        notes.append(
            f"forecast/market join demonstrated on {len(joined)} proposition(s) "
            f"({len(expressed)} expressed by markets, {len(with_forecast)} forecast, "
            f"{len(with_market)} market-implied)"
        )

    return report()


def report() -> int:
    for note in notes:
        print(note)
    if failures:
        print(f"\nFAILED ({len(failures)}):", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print("\nOK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
