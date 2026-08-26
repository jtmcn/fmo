#!/usr/bin/env python3
"""Tests for the shapes-drift signer and classifier.

Pure rdflib, no ROBOT: these are questions about the shapes file, not about
what a reasoner derives from the ontology.

Run: python3 scripts/test_shape_drift.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import shape_signatures as S  # noqa: E402


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
    problems = test_facts_shape()
    for p in problems:
        print(f"  FAIL {p}")
    if problems:
        print(f"\n{len(problems)} problem(s)")
        return 1
    print("  ok   [facts] five shapes, constraints captured, message excluded")
    print("\nOK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
