#!/usr/bin/env python3
"""Tests for the shapes-drift signer and classifier.

Pure rdflib, no ROBOT: these are questions about the shapes file, not about
what a reasoner derives from the ontology.

Run: python3 scripts/test_shape_drift.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import shape_signatures as S  # noqa: E402
from registry import SHAPES  # noqa: E402


def with_edit(find: str, replace: str) -> Path:
    """A scratch copy of the shapes file with one textual edit applied.

    Through the file and the real parser, never through the parsed dicts: both
    sides of a comparison would otherwise come from one facts() call, the
    signer/classifier seam would go untested, and a bug in facts() would cancel
    itself out.
    """
    text = SHAPES.read_text(encoding="utf-8")
    if text.count(find) != 1:
        raise LookupError(f"anchor appears {text.count(find)} times: {find!r}")
    tmp = Path(tempfile.mkdtemp()) / SHAPES.name
    tmp.write_text(text.replace(find, replace), encoding="utf-8")
    return tmp


# (name, rule exercised, find, replace, {(shape, verdict)}, detail fragment)
CASES = [
    ("a node shape switched off", "deactivated-set",
     "teh:TargetShape a sh:NodeShape ;",
     "teh:TargetShape a sh:NodeShape ;\n    sh:deactivated true ;",
     {("teh:TargetShape", "WEAKENED")}, "switched off"),

    ("a node shape removed", "shape-removed",
     "teh:ProtocolShape a sh:NodeShape ;", "teh:Unused a sh:NodeShape ;",
     {("teh:ProtocolShape", "WEAKENED"), ("teh:Unused", "CHANGED")}, "removed"),

    ("a node shape added", "shape-added",
     "teh:ProtocolShape a sh:NodeShape ;",
     "teh:Extra a sh:NodeShape ; sh:targetClass fm:Document .\n\nteh:ProtocolShape a sh:NodeShape ;",
     {("teh:Extra", "CHANGED")}, "added"),

    ("targetClass removed", "target-removed",
     "    sh:targetClass ksh:Market ;", "",
     {("teh:MarketShape", "WEAKENED")}, "matches no focus nodes"),

    ("targetClass narrowed to a subclass", "target-narrowed",
     "    sh:targetClass ksh:Market ;", "    sh:targetClass ksh:WeatherMarket ;",
     {("teh:MarketShape", "WEAKENED")}, "narrowed"),

    ("targetClass widened to a superclass", "target-changed",
     "    sh:targetClass fm:ProbabilityAssignment ;",
     "    sh:targetClass fm:InformationContentEntity ;",
     {("teh:ProbabilityShape", "CHANGED")}, "targetClass"),

    ("a required path removed", "path-removed",
     "        sh:path ksh:marketTicker ;", "        sh:path ksh:ignoredTicker ;",
     {("teh:MarketShape", "WEAKENED"), ("teh:MarketShape", "CHANGED")}, "ksh:marketTicker"),

    ("minCount lowered", "min-weakened",
     "        sh:path fm:statedAs ;\n        sh:minCount 1 ;",
     "        sh:path fm:statedAs ;\n        sh:minCount 0 ;",
     {("teh:ProtocolShape", "WEAKENED")}, "minCount 1 -> 0"),

    ("minCount raised", "min-changed",
     "        sh:path fm:statedAs ;\n        sh:minCount 1 ;",
     "        sh:path fm:statedAs ;\n        sh:minCount 2 ;",
     {("teh:ProtocolShape", "CHANGED")}, "minCount 1 -> 2"),

    ("maxCount raised", "max-weakened",
     "        sh:path ksh:expressesProposition ;\n        sh:minCount 1 ; sh:maxCount 1 ;",
     "        sh:path ksh:expressesProposition ;\n        sh:minCount 1 ; sh:maxCount 2 ;",
     {("teh:MarketShape", "WEAKENED")}, "maxCount 1 -> 2"),

    ("maxCount removed", "max-weakened",
     "        sh:path ksh:expressesProposition ;\n        sh:minCount 1 ; sh:maxCount 1 ;",
     "        sh:path ksh:expressesProposition ;\n        sh:minCount 1 ;",
     {("teh:MarketShape", "WEAKENED")}, "maxCount 1 -> None"),

    ("maxCount lowered", "max-changed",
     "        sh:path fm:hasComparator ;\n        sh:minCount 1 ; sh:maxCount 1 ;",
     "        sh:path fm:hasComparator ;\n        sh:minCount 1 ; sh:maxCount 0 ;",
     {("teh:PropositionShape", "CHANGED")}, "maxCount 1 -> 0"),

    ("a value constraint removed", "value-removed",
     "        sh:class wx:WeatherObservationTarget ;", "",
     {("teh:PropositionShape", "WEAKENED")}, "class constraint removed"),

    ("a value constraint changed", "value-changed",
     "        sh:class wx:WeatherObservationTarget ;", "        sh:class fm:ObservationTarget ;",
     {("teh:PropositionShape", "CHANGED")}, "class"),

    ("severity lowered", "severity-weakened",
     "        sh:path wx:underProtocol ;", "        sh:path wx:underProtocol ;\n        sh:severity sh:Warning ;",
     {("teh:TargetShape", "WEAKENED")}, "severity"),
]

# severity-changed, deactivated-cleared and path-added need a mutated BASELINE
# rather than a mutated current file: they are the reverse of a case above.
REVERSE_CASES = [
    ("severity raised", "severity-changed",
     "        sh:path wx:underProtocol ;", "        sh:path wx:underProtocol ;\n        sh:severity sh:Warning ;",
     {("teh:TargetShape", "CHANGED")}, "severity"),
    ("a shape switched back on", "deactivated-cleared",
     "teh:TargetShape a sh:NodeShape ;", "teh:TargetShape a sh:NodeShape ;\n    sh:deactivated true ;",
     {("teh:TargetShape", "CHANGED")}, "cleared"),
    ("a path added", "path-added",
     "        sh:path ksh:marketTicker ;", "        sh:path ksh:ignoredTicker ;",
     {("teh:MarketShape", "CHANGED"), ("teh:MarketShape", "WEAKENED")}, "ksh:marketTicker"),
]


def _check(name, rule, got, expected, fragment) -> list[str]:
    seen = {(v["shape"], v["verdict"]) for v in got}
    if seen != expected:
        return [f"[{name}] verdicts {sorted(seen)} != expected {sorted(expected)}"]
    if not any(fragment in v["detail"] for v in got):
        return [f"[{name}] no detail contains {fragment!r}: {[v['detail'] for v in got]}"]
    if rule not in {v["rule"] for v in got}:
        return [f"[{name}] no verdict came from rule {rule!r}: {[v['rule'] for v in got]}"]
    print(f"  ok   [{name}] {rule}")
    return []


def test_classifier() -> list[str]:
    problems, below = [], S.subclass_map()
    base = S.facts()
    for name, rule, find, replace, expected, fragment in CASES:
        got = S.compare(base, S.facts(with_edit(find, replace)), below)
        problems += _check(name, rule, got, expected, fragment)
    # Reversed: the edited file is the BASELINE and today's file is current.
    for name, rule, find, replace, expected, fragment in REVERSE_CASES:
        got = S.compare(S.facts(with_edit(find, replace)), base, below)
        problems += _check(name, rule, got, expected, fragment)
    return problems


def test_every_rule_is_claimed() -> list[str]:
    """The assertion the plan's first draft only claimed in prose.

    Review ablated each rule by hand and found three that no case exercised --
    including a row of the spec's own table -- while the plan asserted "one case
    per row". A coverage claim nothing checks is the defect this phase is about.
    """
    claimed = {rule for _, rule, *_ in CASES} | {rule for _, rule, *_ in REVERSE_CASES}
    missing = sorted(set(S.RULES) - claimed)
    return [f"rules no mutant exercises: {missing}"] if missing else []


def test_no_false_positives() -> list[str]:
    """The case that keeps the alarm worth reading.

    Not compare(facts(), facts()) -- identical inputs are a tautology that cannot
    fail. This reformats the Turtle, rewrites a message and adds a comment, all
    through the real parser.
    """
    edited = with_edit(
        "        sh:minCount 1 ; sh:maxCount 1 ;\n        sh:datatype",
        "# an added comment\n        sh:minCount 1 ;\n        sh:maxCount 1 ;\n        sh:datatype",
    )
    text = edited.read_text(encoding="utf-8").replace(
        "every market expresses exactly one proposition", "reworded entirely")
    edited.write_text(text, encoding="utf-8")
    got = S.compare(S.facts(), S.facts(edited), S.subclass_map())
    return [] if not got else [f"a reformat and a message edit produced verdicts: {got}"]


def test_facts_shape() -> list[str]:
    problems = []
    facts = S.facts()
    if set(facts) != {
        "teh:MarketShape", "teh:PropositionShape", "teh:TargetShape",
        "teh:ProtocolShape", "teh:ProbabilityShape",
    }:
        problems.append(f"unexpected shape set: {sorted(facts)}")
        return problems

    market = facts["teh:MarketShape"]
    if market["targetClass"] != "ksh:Market":
        problems.append(f"MarketShape targetClass: {market['targetClass']}")
    ticker = market["paths"].get("ksh:marketTicker", {})
    if ticker.get("minCount") != 1 or ticker.get("maxCount") != 1:
        problems.append(f"marketTicker counts: {ticker}")
    if ticker.get("datatype") != "xsd:string":
        problems.append(f"marketTicker datatype: {ticker}")
    if ticker.get("severity") != "sh:Violation":
        problems.append(f"severity must default to Violation, got {ticker}")
    if "message" in ticker:
        problems.append("sh:message must not be captured")
    if market.get("deactivated") is not False:
        problems.append(f"deactivated must be recorded and False here: {market.get('deactivated')}")
    return problems


def test_refuses_unmodelled() -> list[str]:
    """An unmodelled construct must fail the signer, not be ignored.

    This is the guard that would have caught sh:deactivated during design instead
    of during review.
    """
    problems = []
    edited = with_edit("teh:ProtocolShape a sh:NodeShape ;",
                       "teh:ProtocolShape a sh:NodeShape ;\n    sh:closed true ;")
    try:
        S.facts(edited)
        problems.append("sh:closed was ignored rather than refused")
    except SystemExit as exc:
        if "sh:closed" not in str(exc):
            problems.append(f"refusal does not name the construct: {exc}")
        else:
            print("  ok   [refuses unmodelled] sh:closed")

    duplicated = with_edit(
        "        sh:path fm:hasComparator ;",
        "        sh:path fm:hasSubject ;",
    )
    try:
        S.facts(duplicated)
        problems.append("two property shapes on one path collapsed silently")
    except SystemExit as exc:
        if "two property shapes" not in str(exc):
            problems.append(f"duplicate-path refusal is the wrong error: {exc}")
        else:
            print("  ok   [refuses unmodelled] duplicate sh:path")
    return problems


def main() -> int:
    problems = (
        test_facts_shape() + test_refuses_unmodelled() + test_classifier()
        + test_every_rule_is_claimed() + test_no_false_positives()
    )
    for p in problems:
        print(f"  FAIL {p}")
    if problems:
        print(f"\n{len(problems)} problem(s)")
        return 1
    total = len(CASES) + len(REVERSE_CASES)
    print(f"\nOK: {total} mutants over {len(S.RULES)} rules, no false positives")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
