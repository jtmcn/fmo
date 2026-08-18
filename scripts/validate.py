#!/usr/bin/env python3
"""Structural checks for the Wantology modules.

Parses every module plus the vendored BFO, then checks the things that actually
go wrong when hand-authoring a BFO application ontology:

  1. Every file parses as Turtle.
  2. Every term we mint sits under exactly one BFO top-level branch, and
     reaches bfo:entity by rdfs:subClassOf. A term that does not is either
     unrooted or accidentally rooted in owl:Thing.
  3. No class is both a continuant and an occurrent. This is the disjointness
     that BFO cares most about and the one an application ontology breaks by
     mistake, typically by filing an information artifact under process.
  4. Every property we use in the examples is declared somewhere.
  5. Every class and property carries a label and a skos:definition. A scopeNote
     says "why here, not there", which is not a statement of what the term means,
     so it does not substitute.
  6. Derived values match what they are derived from: wx:leadTimeHours against the
     forecast's issuance time and its target interval's first instant.
  7. Units cohere. Where two values get compared, they must use the *same* QUDT unit;
     where a unit is merely chosen for a variable, its QUDT dimension vector must
     match. This catches both a Fahrenheit threshold read against a Celsius target
     (same dimension, still wrong) and inches read against a temperature.

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
    "https://w3id.org/wantology/core#",
    "https://w3id.org/wantology/weather#",
    "https://w3id.org/wantology/kalshi#",
)

MODULES = ["imports/bfo-core.ttl", "imports/qudt-subset.ttl", "core.ttl", "weather.ttl", "kalshi.ttl", "wantology.ttl"]
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


QUDT = "http://qudt.org/schema/qudt/"
WTL = "https://w3id.org/wantology/core#"
WX = "https://w3id.org/wantology/weather#"

HAS_UNIT = URIRef(WTL + "hasUnit")
HAS_SUBJECT = URIRef(WTL + "hasSubject")
REPORTS_FOR = URIRef(WX + "reportsValueFor")
TARGET_VAR = URIRef(WX + "targetVariable")
CONVENTIONAL_UNIT = URIRef(WX + "conventionalUnit")
DIM_VECTOR = URIRef(QUDT + "hasDimensionVector")
# Properties whose presence means a unit is mandatory rather than optional.
VALUE_PROPS = (URIRef(WTL + "floorValue"), URIRef(WTL + "capValue"),
               URIRef(WTL + "realizedValue"))


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

        wtl:hasUnit is functional in OWL, but this runs without a reasoner, so two
        units here is a wrong answer rather than an inconsistency. A missing unit is
        at least as likely an authoring slip as a wrong one, so a value with no unit
        fails instead of quietly dropping out of the comparison.
        """
        units = list(g.objects(entity, HAS_UNIT))
        if len(units) > 1:
            fail(
                f"ambiguous unit: {entity} has {len(units)} wtl:hasUnit values "
                f"({sorted(str(u) for u in units)}). wtl:hasUnit is functional, so "
                f"this is an inconsistency the reasoner would catch; without one, "
                f"the unit check would compare against whichever came first."
            )
            return None
        if not units:
            if any(v for p in VALUE_PROPS for v in g.objects(entity, p)):
                fail(
                    f"missing unit: {entity} carries a numeric value but no "
                    f"wtl:hasUnit, so it cannot be compared against anything"
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
                    f"missing unit ({phrasing}): {missing} has no usable wtl:hasUnit, "
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
OVER_INTERVAL = URIRef(WTL + "overTemporalInterval")
FIRST_INSTANT = URIRef(BFO + "BFO_0000222")
INSTANT_DT = URIRef(WTL + "instantDateTime")


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
                f"the wtl:instantDateTime scope note."
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

    # Domain sanity: the join the ontology exists for.
    #
    # All three conditions are required. An earlier version intersected "expressed
    # by a market" with "assigned any probability", which a bracket ladder satisfies
    # trivially -- every market has an implied probability, so the count rose with
    # the data while proving strictly less. The join is only demonstrated when the
    # SAME proposition carries a forecast probability AND a market-implied one.
    KSH = "https://w3id.org/wantology/kalshi#"
    expressed = set(ex.objects(None, URIRef(KSH + "expressesProposition")))
    with_forecast = {
        p for s in ex.subjects(RDF.type, URIRef(WTL + "ForecastProbability"))
        for p in ex.objects(s, URIRef(WTL + "assignsProbabilityTo"))
    }
    with_market = {
        p for s in ex.subjects(RDF.type, URIRef(WTL + "MarketImpliedProbability"))
        for p in ex.objects(s, URIRef(WTL + "assignsProbabilityTo"))
    }
    joined = expressed & with_forecast & with_market
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
