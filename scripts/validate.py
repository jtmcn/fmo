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
 11. Everything CONTEXT.md names in backticks still exists: minted terms declared
     (not merely mentioned, and not retired to an owl:deprecated tombstone), example
     individuals defined, and the paths, make targets and check names its repo-mechanics
     section runs on. The vocabulary file is prose and nothing else reads it, so a
     rename leaves its mentions pointing at nothing, exactly as a dangling IRI does in
     the examples. A name the project rejected is written struck through and skipped.
 12. The trading layer settles what it says it settles: a match outputs one yes lot and
     one no lot of equal quantity, and a payout pays the side its resolution determined,
     to the holder whose obligation it realizes, at one dollar a contract.
 13. Every minted class no example instantiates is classified in
     queries/class-coverage-expectations.json with a reason, and the ledger is made to
     shrink: an entry for a class an example now reaches, or for one that no longer
     exists, fails. No count is pinned.

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

import json
import re
import sys
from datetime import date
from pathlib import Path

from rdflib import Graph, RDF, RDFS, OWL, URIRef, Literal
from rdflib.namespace import SKOS

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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from registry import (  # noqa: E402
    CONTEXT_PREFIXES, EXAMPLE_PREFIXES, IRI_TO_PREFIX, MODULES, OUR_NS,
    PROSE_FILES, ROOT, SRC, examples,
)

# A term is declared when something types it. A retirement that leaves a tombstone behind
# -- owl:deprecated plus the old label -- is not a declaration, and CONTEXT.md must stop
# naming it rather than keep pointing at a term the model no longer has.
DECLARED_AS = (OWL.Class, OWL.ObjectProperty, OWL.DatatypeProperty, OWL.AnnotationProperty, OWL.NamedIndividual)

CONTEXT = ROOT / "CONTEXT.md"
# Backticked only: prose says "the fm: side" and names files, and neither is a term.
# Struck through (~~`ksh:Event`~~) is exempt: that is how the file spells a name the
# project rejected, which by construction is declared nowhere.
CONTEXT_TERM = re.compile(rf"(?<!~)`({'|'.join(CONTEXT_PREFIXES)}):([A-Za-z][A-Za-z0-9_]*)`(?!~)")
# Globs are patterns, not paths (`queries/cqNN-*.rq` names no file), and build/ is generated.
CONTEXT_PATH = re.compile(r"`((?:src|scripts|queries|docs|examples)/[^`*]*)`")
CONTEXT_MAKE = re.compile(r"`make ([a-z][a-z-]*)`")
CONTEXT_CHECK = re.compile(r"`(check_[a-z_]+)`")

# Snapshotting the glob at import is safe here and only here: this script is always
# a process whose ROOT is derived from its own location, so the negative-test copy
# gets its own import. An in-process caller must call examples() instead.
EXAMPLES = examples()

failures: list[str] = []
notes: list[str] = []


def fail(msg: str) -> None:
    failures.append(msg)


coverage_log: list[tuple[str, int]] = []


def coverage(name: str, count: int, detail: str, on_empty: str = "",
             *, always: bool = False) -> None:
    """Record a check's traversal count, and fail when it is zero.

    Every check prints how much it looked at. Printing is not checking: each
    "traverses nothing" guard was written by hand, one per traversal, and the
    one for lead times was never written -- so that count could read 0 and the
    run stayed green. One call per traversal, not one per check: an aggregate
    counter over several traversals stays non-zero when one of them empties.

    on_empty carries the diagnostic the hand-written guard used to print --
    which chain is broken, not merely that something is. A new check that
    passes nothing still gets the guard; it just gets a blunter message until
    someone writes a sharper one.

    The guard is normally gated on there being example data at all, because a
    traversal over examples that do not exist is legitimately empty. always=True
    is for a check whose population is the schema: no example file can empty it,
    so a zero count means the modules themselves stopped carrying what the check
    reads, and gating that on EXAMPLES makes the guard depend on something the
    check never looks at.
    """
    coverage_log.append((name, count))
    # Noted before the guard, not after: the hand-written guards failed AND kept
    # the "0 checked" line, and a failing run still wants the count in the summary.
    notes.append(f"{name}: {count} {detail}")
    if count == 0 and (always or EXAMPLES):
        fail(f"{name}: nothing to check, so this check proved nothing"
             + (f" -- {on_empty}" if on_empty else ""))


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


def minted_classes(g: Graph) -> list:
    """Every class in our namespaces, declared or merely reached by rdfs:subClassOf.

    Collected from rdfs:subClassOf as well as `a owl:Class`: a hand-authored class
    that only ever appears as the subject or parent of a subClassOf is a plausible
    slip, and taking the declared ones alone made it invisible rather than unrooted.

    Recomputed per caller rather than passed in, so every check's interface stays
    one graph -- which is the property test_meta.py's sweep depends on to call
    them all uniformly.
    """
    return sorted(
        {s for s in g.subjects(RDF.type, OWL.Class) if is_ours(s)}
        | {s for s in g.subjects(RDFS.subClassOf, None) if is_ours(s)}
        | {o for o in g.objects(None, RDFS.subClassOf) if is_ours(o)},
        key=str,
    )


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
    threshold_compared = 0
    for prop, target in g.subject_objects(HAS_SUBJECT):
        pu, tu = unit_of(prop), unit_of(target)
        check_identical(prop, pu, target, tu, "proposition threshold vs target")
        threshold_compared += 1
    coverage("unit coherence: threshold vs target", threshold_compared, "pair(s) checked",
             "no proposition names a subject; the hasSubject chain is broken")

    # A datum's reading is the value the target's proposition gets evaluated against.
    datum_compared = 0
    for datum, target in g.subject_objects(REPORTS_FOR):
        du, tu = unit_of(datum), unit_of(target)
        check_identical(datum, du, target, tu, "datum vs target")
        datum_compared += 1
    coverage("unit coherence: datum vs target", datum_compared, "pair(s) checked",
             "no datum reaches a target; the reportsFor chain is broken")

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
    coverage("unit coherence: settlement value vs target", settlement_compared,
             "pair(s) checked",
             "no settlement value reaches a target; the resolutionOf or "
             "expressesProposition chain is broken")

    # A target's unit should be dimensionally compatible with its variable's
    # conventional units. Advisory: a target may use an unlisted but valid unit.
    variable_compared = 0
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
        variable_compared += 1
    coverage("unit coherence: target vs conventional unit", variable_compared,
             "pair(s) checked",
             "no target with a unit reaches a variable with conventional units; "
             "the targetVariable or wx:conventionalUnit chain is broken")


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

    coverage("lead times", checked, "checked against issuance and interval start")


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
    coverage("current assessments", len(by_proposition),
             "proposition(s) checked for a single current assessment",
             "the assessesProposition chain is broken")


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
    coverage("skill scores", checked, "Brier score(s) checked against their inputs",
             "the usesScoringRule or scoresAssignment chain is broken")


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
    coverage("target protocols", len(targets), "observation target(s) checked for a protocol",
             "the wx:WeatherObservationTarget typing is broken")

    checked = 0
    reported: set[URIRef] = set()
    for market, grouping in g.subject_objects(IN_EVENT_GROUPING):
        # ksh:settlementSource attaches to a listing; a market inherits it from its
        # grouping or series unless it carries its own. Precedence, not union -- a
        # grouping overriding its series is how the 2026-08-14 migration is modelled,
        # and unioning the levels rejects that correct model as ambiguous.
        levels = ([market], [grouping], list(g.objects(grouping, IN_SERIES)))
        sources: set[URIRef] = set()
        resolved = 0
        for depth, holders in enumerate(levels):
            sources = {s for h in holders for s in g.objects(h, SETTLEMENT_SOURCE)}
            if sources:
                resolved = depth
                break
        if len(sources) != 1:
            # Only a market-level defect is the market's own; one resolved higher
            # belongs to the grouping, and every market under it would repeat it.
            key = market if resolved == 0 else grouping
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
    coverage("settlement protocols", checked, "market/protocol pair(s) checked for settlement agreement",
             "the settlementSource or sourceProtocol chain is broken")


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

    coverage("grouping coherence", checked, "market/grouping pair(s) checked for target agreement",
             "the inEventGrouping or expressesProposition chain is broken")


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
    verified = 0  # payouts whose side, recipient and amount were actually compared
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

    # Counted after the comparisons, not on arrival: a payout on a scalar or voided
    # outcome leaves the loop before its side and amount are ever compared, and
    # reporting it as checked is how a skip reads as a pass.
    coverage("payouts", verified, "payout(s) checked against their resolution, holder and lot",
             "no payout reaches a resolution and a contract lot, or every one was "
             "voided or scalar; the trading layer is unexercised again")


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

    coverage("trades", checked, "trade(s) checked for opposite sides and equal quantity",
             "the trading layer is unexercised again")


def check_context_terms(g: Graph, ex: Graph) -> None:
    """The prose files name terms, and no tool but this one reads them.

    Everything backticked the repo can be asked about is checked: minted terms and
    example individuals against the graph, source paths, make targets and check names
    against the tree. §4 is entirely repo mechanics, so leaving those unchecked left
    the half of the file most likely to rot as the half nothing watched.

    Coverage is deliberately not checked in the other direction: the file exists to
    say which word to use, not to restate 200 definitions, so demanding an entry per
    term would turn it into the copy of the ontology it is written not to be.
    """
    for path in PROSE_FILES:
        if not path.exists():
            fail(f"missing prose file: {path.name}")
            return
    text = CONTEXT.read_text(encoding="utf-8")

    declared = {s for cls in DECLARED_AS for s in g.subjects(RDF.type, cls) if is_ours(s)}
    deprecated = set(g.subjects(OWL.deprecated, Literal(True)))

    all_mentioned: set = set()
    context_mentioned: set = set()
    for path in PROSE_FILES:
        prose = path.read_text(encoding="utf-8")
        mentioned = set(CONTEXT_TERM.findall(prose))
        # Counted for CONTEXT.md alone: the other prose files backtick plenty of terms
        # themselves, so an aggregate stays non-zero with CONTEXT.md emptied.
        if path == CONTEXT:
            context_mentioned = mentioned
        all_mentioned |= mentioned
        for prefix, local in sorted(mentioned):
            term = URIRef(CONTEXT_PREFIXES[prefix] + local)
            if prefix in EXAMPLE_PREFIXES:
                if (term, RDF.type, None) not in ex:
                    fail(f"{path.name} names an undefined individual: {prefix}:{local}")
            elif term in deprecated:
                fail(f"{path.name} names a deprecated term: {prefix}:{local}")
            elif term not in declared:
                fail(f"{path.name} names an undeclared term: {prefix}:{local}")

    paths = set(CONTEXT_PATH.findall(text))
    for rel in sorted(paths):
        if not (ROOT / rel).exists():
            fail(f"CONTEXT.md names a missing path: {rel}")

    targets = set(CONTEXT_MAKE.findall(text))
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    for target in sorted(targets):
        if not re.search(rf"^{re.escape(target)}:", makefile, re.M):
            fail(f"CONTEXT.md names a missing make target: {target}")

    checks = set(CONTEXT_CHECK.findall(text))
    source = "".join(f.read_text(encoding="utf-8") for f in sorted((ROOT / "scripts").glob("*.py")))
    for name in sorted(checks):
        if f"def {name}(" not in source:
            fail(f"CONTEXT.md names a missing check: {name}")

    # One call per traversal: §4's paths, targets and check names were reported
    # through notes alone, so any of the three could drop to zero and read as a pass.
    coverage("prose terms", len(context_mentioned),
             f"term(s) backticked in CONTEXT.md, {len(all_mentioned)} across "
             f"{len(PROSE_FILES)} prose file(s)",
             "CONTEXT.md names no terms in backticks, so this check matched nothing",
             always=True)
    coverage("prose paths", len(paths), "source path(s) checked against the tree",
             "CONTEXT.md backticks no repo path, so §4's paths went unchecked",
             always=True)
    coverage("prose make targets", len(targets), "make target(s) checked against the Makefile",
             "CONTEXT.md names no make target, so §4's targets went unchecked",
             always=True)
    coverage("prose checks", len(checks), "check name(s) checked against scripts/",
             "CONTEXT.md names no check_* function, so §4's check names went unchecked",
             always=True)


def check_designation_disjointness(g: Graph) -> None:
    """Every subclass of fm:Designation is in an owl:AllDisjointClasses block.

    The blocks are hand-written enumerations, and the vocabularies they cover keep
    arriving: fm:ScoringRule was left out of the first version and nothing noticed,
    because the defect a missing member allows -- one individual typed into two
    controlled vocabularies at once -- is legal OWL that every other check reads as
    fine. This is the drift the MODULES list has the same shape as, and the same
    answer: derive the expected set instead of trusting the enumeration.

    The zero guard is coverage()'s, not hand-written: a hand-maintained guard is
    what the sweep exists to stop relying on.

    Membership is checked, not the geometry. Whether the pairs are asserted in one
    block or several is a placement question -- core.ttl restates its own so that
    importing core without kalshi still gets them -- and either satisfies this.
    """
    designations = {c for c in g.subjects(RDFS.subClassOf, URIRef(FM + "Designation"))}
    covered: set = set()
    for block in g.subjects(RDF.type, OWL.AllDisjointClasses):
        for members in g.objects(block, OWL.members):
            covered |= set(g.items(members))

    missing = sorted(str(c) for c in designations - covered)
    for iri in missing:
        fail(
            f"designation vocabulary in no owl:AllDisjointClasses block: {iri} -- "
            f"one of its individuals could also be typed into another vocabulary, "
            f"and every functional-property guard would still pass"
        )

    coverage(
        "designations", len(designations),
        f"subclass(es) of fm:Designation, {len(designations & covered)} "
        f"covered by a disjointness block",
        "no subclasses of fm:Designation found -- the class was renamed, or the "
        "module carrying it was not loaded",
        always=True,
    )


def check_forecast_market_join(g: Graph) -> None:
    """The join the ontology exists for: one proposition, both probabilities.

    All three conditions are required. An earlier version intersected "expressed
    by a market" with "assigned any probability", which a bracket ladder satisfies
    trivially -- every market has an implied probability, so the count rose with
    the data while proving strictly less. The join is only demonstrated when the
    SAME proposition carries a forecast probability AND a market-implied one.
    """
    expressed = set(g.objects(None, EXPRESSES))
    with_forecast = {
        p for s in g.subjects(RDF.type, URIRef(FM + "ForecastProbability"))
        for p in g.objects(s, URIRef(FM + "assignsProbabilityTo"))
    }
    with_market = {
        p for s in g.subjects(RDF.type, URIRef(FM + "MarketImpliedProbability"))
        for p in g.objects(s, URIRef(FM + "assignsProbabilityTo"))
    }
    joined = expressed & with_forecast & with_market
    coverage(
        "forecast/market join", len(joined),
        f"proposition(s) carrying both ({len(expressed)} expressed by markets, "
        f"{len(with_forecast)} forecast, {len(with_market)} market-implied)",
        "no proposition is expressed by a market AND carries both a forecast "
        "probability and a market-implied probability; the forecast/market join "
        "is not demonstrated",
    )


def check_forecast_targets(g: Graph) -> None:
    """A forecast's target is the subject of the propositions it scores.

    wx:forecastFor fixes what a forecast claims to be about; the proposition's
    subject fixes what the market settles on. Nothing tied the two together, so
    they could drift apart in silence -- and the examples aligned them only by
    hand. wx:alternativeDeterminationOf turns the specific cross-authority case
    from "mismatch" into a diagnosis. The relation licenses no substitution, so
    being declared alternative determinations is not a defence; it is the point.
    """
    alt_det = URIRef(WX + "alternativeDeterminationOf")
    has_part = URIRef(BFO + "BFO_0000178")
    assigns = URIRef(FM + "assignsProbabilityTo")
    forecast_prob = URIRef(FM + "ForecastProbability")
    scored = 0
    for forecast, ftarget in g.subject_objects(FORECAST_FOR):
        for part in g.objects(forecast, has_part):
            if (part, RDF.type, forecast_prob) not in g:
                continue
            for prop in g.objects(part, assigns):
                for subject in g.objects(prop, HAS_SUBJECT):
                    scored += 1
                    if subject == ftarget:
                        continue
                    # Symmetry is asserted, not materialised -- rdflib does no
                    # reasoning here, so both directions are checked explicitly.
                    declared = (ftarget, alt_det, subject) in g or (
                        subject,
                        alt_det,
                        ftarget,
                    ) in g
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
    coverage("forecast targets", scored,
             "forecast probability/proposition pair(s) checked for target agreement",
             "the has-part or assignsProbabilityTo chain is broken")


COVERAGE_LEDGER = ROOT / "queries" / "class-coverage-expectations.json"
# schema-instantiated is not here: it is derived below, so no edit to the file can
# claim it for a class the modules do not actually enumerate.
COVERAGE_CATEGORIES = ("unassertable", "unlisted", "unwritten")


def prefixed(term: URIRef) -> str:
    """IRI to `wx:Thing`, over registry's shared map rather than a second one."""
    text = str(term)
    for full, short in IRI_TO_PREFIX.items():
        if text.startswith(full):
            return short + text[len(full):]
    return text


def check_class_coverage(g: Graph, ex: Graph) -> None:
    """Every unexercised minted class is classified, with a reason.

    A class no example instantiates is a class nobody has watched work. The count
    was advisory for a long time and drifted to 36 of 98 unnoticed, so this makes
    a new one fail the build until someone says which of four things it is.

    No count is pinned. The four situations behind those 36 are not one population
    -- some classes are empty because the ontology is correct, and a floor over the
    lot could not move for reasons that have nothing to do with the model improving.
    """
    our_classes = minted_classes(g)
    # A class the modules enumerate themselves. Derived rather than declared, and
    # deliberately narrow: a class whose *children* carry the schema individuals is
    # not one of these, it just has enumerated children.
    schema_instantiated = {t for t in g.objects(None, RDF.type) if is_ours(t)}
    # Subtracted by class, not by instance, because ex carries the schema too. The
    # assumption: no example types an individual to one of these nine. If one ever
    # does, that class stays schema-only and its parents miss out on reached.
    instantiated = {t for t in ex.objects(None, RDF.type) if is_ours(t)} - schema_instantiated

    # Exercised directly or through a subclass, via ancestors of what examples type.
    reached = set(instantiated)
    for term in instantiated:
        reached |= ancestors(g, term)

    ledger = json.loads(COVERAGE_LEDGER.read_text(encoding="utf-8"))
    # A key nothing reads is worse than a wrong one: entries parked under it escape
    # both staleness guards while reading as authoritative. schema-instantiated is
    # the one to expect, since four documents say it is derived and never written.
    unknown = set(ledger) - {"_comment"} - set(COVERAGE_CATEGORIES)
    if unknown:
        fail(f"ledger has categories nothing reads: {', '.join(sorted(unknown))} -- "
             f"schema-instantiated is derived, never written here")
    classified: dict[str, tuple[str, dict]] = {}
    for category in COVERAGE_CATEGORIES:
        for name, entry in ledger.get(category, {}).items():
            if name in classified:
                fail(f"classified twice: {name} -- in {classified[name][0]} and "
                     f"{category}, and only one reason can be the real one")
            classified[name] = (category, entry)

    for cls in our_classes:
        if cls in reached or cls in schema_instantiated:
            continue
        if prefixed(cls) not in classified:
            fail(f"unexercised and not classified: {prefixed(cls)} -- "
                 f"add it to {COVERAGE_LEDGER.name} under one of {', '.join(COVERAGE_CATEGORIES)}")

    # Deliberately no coverage() call on this loop, unlike every other traversal here:
    # an empty ledger is the goal state, not a broken one, and it cannot pass in
    # silence anyway -- with nothing classified, the loop above fails on all 27.
    by_name = {prefixed(cls): cls for cls in our_classes}
    for name, (category, entry) in sorted(classified.items()):
        cls = by_name.get(name)
        if cls is None:
            fail(f"ledger names a class that does not exist: {name} -- "
                 f"renamed or retired, so its entry in {category} is stale")
            continue
        if cls in reached or cls in schema_instantiated:
            fail(f"classified but exercised: {name} -- an example now reaches it, "
                 f"so drop it from {category} in {COVERAGE_LEDGER.name}")
            continue
        # The reason is the entry. check_axioms refuses a blank one on its own ledger
        # for the same reason: a category with no argument behind it is a silent pass
        # wearing a classification.
        if not isinstance(entry, dict) or not str(entry.get("reason", "")).strip():
            fail(f"classified with no reason given: {name} in {category}")
            continue
        # unassertable is the only category claiming the ontology refuses the class,
        # so it names where that argument is written. A reword that deletes the note
        # leaves the entry citing nothing, and reads as settled while it does.
        if category == "unassertable":
            justifier = by_name.get(entry.get("justified_by", ""))
            if justifier is None:
                fail(f"unassertable entry names no declared justification: {name}")
            elif not any(g.objects(justifier, SKOS.scopeNote)):
                fail(f"justification carries no scope note: {prefixed(justifier)} -- "
                     f"cited by {name}, so its argument is no longer written down")
        # unlisted rests on what Kalshi listed on one day, which nothing here can
        # re-check. The date is the whole claim; without it the entry is undated
        # hearsay about a set that changes weekly.
        if category == "unlisted":
            try:
                date.fromisoformat(str(entry.get("checked", "")))
            except ValueError:
                fail(f"unlisted entry carries no check date: {name} -- "
                     f"say when the series list was read, as YYYY-MM-DD")

    # Advisory, never a failure. Split because a class only the schema can instantiate
    # is not a gap any example could close. See docs/adr/0001-classify-unexercised-classes.md.
    direct = sum(1 for c in our_classes if c in instantiated)
    closure = sum(1 for c in our_classes if c in reached)
    schema_only = sum(1 for c in our_classes if c in schema_instantiated and c not in reached)
    notes.append(
        f"{direct} of {len(our_classes)} minted classes have an instance in the "
        f"examples directly, {closure} counting subclass closure"
    )
    notes.append(
        f"{schema_only} further class(es) only the schema can instantiate, so no "
        f"example file can reach them"
    )
    notes.append(
        f"{len(our_classes) - closure - schema_only} class(es) an example could reach "
        f"and does not, each classified in {COVERAGE_LEDGER.name}"
    )

    coverage("class coverage", len(our_classes),
             "minted class(es) checked for an exercise record",
             "no minted classes found -- the namespaces in registry.py no longer match src/",
             always=True)


def check_bfo_grounding(g: Graph) -> None:
    """Every minted class reaches bfo:entity, and lands in a known BFO branch."""
    our_classes = minted_classes(g)
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
    coverage("BFO grounding", len(our_classes), "minted class(es) checked for a path to bfo:entity",
             "no minted classes found -- the namespaces in registry.py no longer match src/",
             always=True)
    if tally:
        notes.append("BFO branch distribution:")
        for name, count in sorted(tally.items(), key=lambda kv: -kv[1]):
            notes.append(f"  {count:3d}  {name}")


def check_bridged_grounding(g: Graph) -> None:
    """External classes we bridge into the hierarchy must be grounded too.

    QUDT makes no upper-level commitment, so without the bridge axioms in core.ttl
    its classes float under owl:Thing. check_bfo_grounding would not notice, because
    these are not in our namespace.

    Derived from the subset rather than hard-coded, because the two IRIs named here
    originally were the two that happened to be floating that day; the generator
    later added a third (qudt:QuantityKindDimensionVector) and the check missed it.
    """
    qudt_classes = sorted(
        (s for s in g.subjects(RDF.type, OWL.Class) if str(s).startswith(QUDT)), key=str
    )
    for iri in qudt_classes:
        if ENTITY not in ancestors(g, iri):
            fail(f"bridged external class not grounded in BFO: {iri}")
    coverage("bridged QUDT classes", len(qudt_classes), "class(es) checked for BFO grounding",
             "the QUDT subset declares no owl:Class, so the bridge axioms guard nothing",
             always=True)


def check_branch_disjointness(g: Graph) -> None:
    """No minted class is both a continuant and an occurrent."""
    our_classes = minted_classes(g)
    for cls in our_classes:
        anc = ancestors(g, cls)
        if CONTINUANT in anc and OCCURRENT in anc:
            fail(f"both continuant and occurrent: {cls}")
    coverage("branch disjointness", len(our_classes),
             "minted class(es) checked for a single BFO branch",
             "no minted classes found -- the namespaces in registry.py no longer match src/",
             always=True)


def check_declared_properties(g: Graph) -> None:
    """Every property an example uses is declared in the modules.

    Reads the example files directly rather than the merged graph, because the
    failure names the file the undeclared property came from.
    """
    declared = {
        s
        for t in (OWL.ObjectProperty, OWL.DatatypeProperty, OWL.AnnotationProperty)
        for s in g.subjects(RDF.type, t)
    }
    builtin_ok = {RDF.type, RDFS.label, RDFS.subClassOf, OWL.imports, OWL.versionIRI}
    checked = 0
    skipped = 0
    for path in EXAMPLES:
        eg = Graph()
        try:
            eg.parse(path, format="turtle")
        except Exception:  # noqa: BLE001
            skipped += 1
            continue  # already reported by main()'s parse loop; do not lose report()
        for _, p, _ in eg:
            checked += 1
            if p in builtin_ok or p in declared:
                continue
            if str(p).startswith(BFO) or str(p).startswith(str(SKOS)):
                continue
            if str(p).startswith("http://purl.org/dc/"):
                continue
            fail(f"{path.name} uses undeclared property: {p}")
    if skipped and not checked:
        # Nothing parsed because everything was broken: main() has already said so, and
        # a zero-coverage failure here points the operator at the wrong thing.
        notes.append(f"declared properties: {skipped} example file(s) did not parse")
        return
    coverage("declared properties", checked, "property use(s) checked against the declarations",
             "no example parsed, so no property use was seen")


def check_defined_terms(ex: Graph) -> None:
    """Individuals and schema terms the examples reference are defined somewhere.

    Checked against the union of the example files, not per file, because they
    import each other: the synthetic dataset legitimately references the site and
    protocol defined in the worked example. Schema IRIs are in scope too: the
    grounding and documentation checks only see classes and properties, so a
    deleted individual (ksh:Settled) left dangling in an example passed silently,
    and rdfs:range made the reasoner infer its type rather than object.

    This exists because re-pointing the settlement source renamed a protocol
    individual and verification-synthetic.ttl went on referencing the old IRI for
    all 40 days. Nothing failed. The targets silently lost their protocol, which
    for an ontology whose central rule is "the observation target carries the
    protocol" is the worst available place to lose one.
    """
    example_ns = "https://w3id.org/forecast-market-ontology/examples/"
    in_scope = (example_ns,) + OUR_NS
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
    # Counted on the example-namespace references alone. Everything in scope includes
    # OUR_NS, which the modules populate by themselves: with examples/ deleted that
    # count reports a healthy 116 while nothing about example data was resolved, which
    # is the printed-a-figure-and-passed failure one level up.
    from_examples = {o for o in referenced if str(o).startswith(example_ns)}
    notes.append(f"defined terms: {len(referenced)} referenced IRI(s) in scope")
    coverage("example references", len(from_examples),
             "example-namespace IRI(s) checked for definedness",
             "the examples reference no example individual, so nothing was resolved")


def check_documentation(g: Graph) -> None:
    """Every minted class and property carries rdfs:label and skos:definition.

    A scopeNote used to count as a definition and this was advisory. Both the module
    docstring and CLAUDE.md promise this fails, so it fails: a scope note says
    "why here, not there", which is not a statement of what the term means.
    """
    terms = minted_classes(g) + sorted(
        {
            s
            for t in (OWL.ObjectProperty, OWL.DatatypeProperty)
            for s in g.subjects(RDF.type, t)
            if is_ours(s)
        },
        key=str,
    )
    for term in terms:
        if not any(g.objects(term, RDFS.label)):
            fail(f"no rdfs:label: {term}")
        if not any(g.objects(term, SKOS.definition)):
            fail(f"no skos:definition: {term}")
    coverage("documentation", len(terms), "minted term(s) checked for label and definition",
             "no minted terms found -- the namespaces in registry.py no longer match src/",
             always=True)


def run_check(fn, *args) -> None:
    """Run one function-shaped check; a raised exception becomes that check's failure.

    An unhandled exception used to abort main(), so every later check went
    unrun and the operator saw a traceback where a verdict belonged. A crashing
    check has failed; the others still have something to say.

    Every check is function-shaped and routes through here, which is also what
    test_meta.py's sweep can see: an inline check body in main() is invisible to it,
    and six lived there long enough to ship a release in which none of them guarded
    a zero count. main() parses and dispatches; it holds no check of its own.
    """
    try:
        fn(*args)
    except Exception as exc:  # noqa: BLE001
        fail(f"{fn.__name__} raised {type(exc).__name__}: {exc}")


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

    our_classes = minted_classes(g)
    notes.append(f"{len(our_classes)} minted classes")

    # 6. Dimensional coherence.
    #
    # Checked on dimension vectors rather than quantity kinds because QUDT's
    # quantity-kind links are uneven (pressure units point at ForcePerArea, not
    # Pressure), while every unit carries exactly one dimension vector.
    #
    # Dimension equality is necessary, not sufficient: snowfall depth and liquid
    # precipitation are both lengths, and percent and degrees are both dimensionless.
    # This catches unit-system mistakes, not quantity confusions.
    for check in (check_dimensions, check_lead_times, check_current_assessments,
                  check_scores, check_grouping_coherence, check_protocols,
                  check_payouts, check_trades, check_forecast_market_join,
                  check_forecast_targets):
        run_check(check, ex)

    # Schema-reading, so these take g rather than ex: what they check is a property
    # of the modules, and no example data can change the answer.
    for check in (check_bfo_grounding, check_bridged_grounding,
                  check_branch_disjointness, check_documentation,
                  check_designation_disjointness):
        run_check(check, g)
    run_check(check_class_coverage, g, ex)

    # Reads the example files itself, to name the file an undeclared property came from.
    run_check(check_declared_properties, g)
    run_check(check_defined_terms, ex)
    run_check(check_context_terms, g, ex)

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
    try:
        code = main()
    except Exception as exc:  # noqa: BLE001
        # run_check catches a crash inside any one check; this catches a crash in
        # main()'s own scaffolding, so the operator still gets a verdict.
        fail(f"validate.py raised {type(exc).__name__}: {exc}")
        code = report()
    raise SystemExit(code)
