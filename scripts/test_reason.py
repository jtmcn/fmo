#!/usr/bin/env python3
"""Negative tests for the axioms that only a reasoner enforces.

scripts/validate.py is deliberately Java-free, so the guards whose whole job is to turn
a mistake into a HermiT rejection have no coverage there. One case per guard, eight in
all: the owl:AllDifferent blocks in core.ttl over the units and over the truth values,
the irreflexivity of wx:alternativeDeterminationOf, the disjointness of the two contract
sides, the cardinality restriction on ksh:Payout, the facet on fm:probabilityValue, the
AllDisjointClasses block over the designation vocabularies, and the union axiom that
makes ksh:BinaryContract a partition. Each case injects the mistake its guard exists for
and asserts ROBOT rejects the result.

A guard can be violated in two shapes and the reasoner reports them differently. Bad data
makes the ontology *inconsistent*; a bad class definition with no individuals leaves it
consistent and makes that class *unsatisfiable*, which is how the InformationBearingEntity
bug arrived. Each case names the report it expects, and a class-level case also names the
class, because "some class is unsatisfiable" would be satisfied by an unrelated one -- the
same attribution the SHACL mutants make on sh:minCount violations.

Skips with a notice when ROBOT or Java is absent, like `make reason`.

Run: python3 scripts/test_reason.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = "examples/kxhighny-2026-08-15.ttl"
TRADING = "examples/kxhighny-2026-08-15-trading.ttl"

# (name, path-to-mutate, find, replace) and optionally the substrings the reasoner's
# report must contain, defaulting to "inconsistent" -- the shape a data mistake takes.
CASES = [
    (
        # The trap README and core.ttl both warn about: fm:hasUnit is functional,
        # so a multi-valued sub-property forces every unit listed for a variable to
        # be one individual -- knots identified with metres per second.
        "conventionalUnit made a sub-property of the functional hasUnit",
        "src/weather.ttl",
        """wx:conventionalUnit a owl:ObjectProperty ;
    rdfs:label "conventional unit" ;""",
        """wx:conventionalUnit a owl:ObjectProperty ;
    rdfs:subPropertyOf fm:hasUnit ;
    rdfs:label "conventional unit" ;""",
    ),
    (
        # The AllDifferent block over the truth values. fm:assessedTruthValue is
        # functional, so two values on one assessment would identify fm:True with
        # fm:False -- and everything downstream would keep computing -- if the
        # individuals were not asserted distinct.
        "one assessment asserting two truth values",
        EXAMPLE,
        "    fm:assessedTruthValue fm:True ;",
        "    fm:assessedTruthValue fm:True , fm:False ;",
    ),
    (
        # wx:alternativeDeterminationOf is irreflexive so that a target asserted to
        # be an alternative determination of itself is an inconsistency rather than
        # a quietly meaningless assertion.
        "a target declared an alternative determination of itself",
        EXAMPLE,
        "    wx:alternativeDeterminationOf ex:Target-HighTemp .",
        "    wx:alternativeDeterminationOf ex:Target-HighTemp-NWS .",
    ),
    (
        # The side of a lot lives in its asserted class -- validate.py reads the
        # paying side off it and CQ8 binds ?side from it -- so a lot on both sides
        # lets a payout pay whichever holder it names, with every check green.
        "one lot typed as both a yes and a no contract",
        TRADING,
        "tex:Lot-Yes-A a ksh:YesContract ;",
        "tex:Lot-Yes-A a ksh:YesContract , ksh:NoContract ;",
    ),
    (
        # ksh:Payout takes one lot, because the amount is checked against that lot's
        # quantity. Two lots on opposite sides identifies them under the cardinality
        # restriction, which the disjointness above then rejects.
        "a payout naming two lots on opposite sides",
        TRADING,
        "    fm:hasInput ex:Resolution-B82 , tex:Lot-Yes-A ;",
        "    fm:hasInput ex:Resolution-B82 , tex:Lot-Yes-A , tex:Lot-No-B ;",
    ),
    (
        # fm:probabilityValue ranges over xsd:decimal narrowed by minInclusive and
        # maxInclusive facets. SHACL rejects an out-of-range probability too, and it
        # was the only side of this watched failing; the facet is what makes the
        # ontology itself refuse the value, so it needs its own case.
        "a probability outside the closed interval from 0 to 1",
        EXAMPLE,
        '    fm:probabilityValue "0.60"^^xsd:decimal ;',
        '    fm:probabilityValue "7.41"^^xsd:decimal ;',
    ),
    (
        # The AllDisjointClasses block over the designation vocabularies. Typing the
        # exchange's outcome as the proposition's truth value is the slip it exists
        # for: both are functional-property values, so nothing else would object.
        "a resolution outcome also typed as a truth value",
        "src/kalshi.ttl",
        'ksh:ResolvedYes  a ksh:ResolutionOutcome, owl:NamedIndividual ;',
        'ksh:ResolvedYes  a ksh:ResolutionOutcome, fm:TruthValue, owl:NamedIndividual ;',
    ),
    (
        # The partition on ksh:BinaryContract. A third side is a class-level mistake
        # that no data has to exercise, so the reasoner leaves the ontology consistent
        # and reports the class unsatisfiable instead.
        "a third contract side minted under the binary partition",
        "src/kalshi.ttl",
        "ksh:TraderRole a owl:Class ;",
        """ksh:ScalarContract a owl:Class ;
    rdfs:subClassOf ksh:BinaryContract ;
    owl:disjointWith ksh:YesContract , ksh:NoContract ;
    rdfs:label "scalar contract" ;
    skos:definition "A third side, injected by scripts/test_reason.py." .

ksh:TraderRole a owl:Class ;""",
        ("unsatisfiable", "kalshi#scalarcontract"),
    ),
]


def robot_command() -> list[str] | None:
    """Same resolution order as the Makefile: ROBOT_JAR, ./robot.jar, robot on PATH."""
    jar = os.environ.get("ROBOT_JAR")
    if not jar and (ROOT / "robot.jar").exists():
        jar = str(ROOT / "robot.jar")
    if jar:
        if not shutil.which("java"):
            return None
        return ["java", "-jar", jar]
    found = shutil.which("robot")
    return [found] if found else None


def run_case(robot: list[str], name: str, rel: str, find: str, replace: str,
             expect: str | tuple[str, ...] = "inconsistent") -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "fmo"
        shutil.copytree(
            ROOT, work,
            ignore=shutil.ignore_patterns(".git", "build", "__pycache__", "*.pyc", ".venv"),
        )
        target = work / rel
        text = target.read_text()
        if text.count(find) != 1:
            print(f"  SETUP FAIL [{name}]: anchor found {text.count(find)} times in {rel}")
            return False
        target.write_text(text.replace(find, replace))

        proc = subprocess.run(
            [*robot, "merge",
             "--input", str(work / "src" / "fmo.ttl"),
             "--input", str(work / EXAMPLE),
             "--input", str(work / TRADING),
             "--catalog", str(work / "src" / "catalog-v001.xml"),
             "reason", "--reasoner", "HermiT",
             "--output", str(work / "reasoned.owl")],
            capture_output=True, text=True,
        )
        output = proc.stdout + proc.stderr
        if proc.returncode == 0:
            print(f"  FAIL [{name}]: the reasoner accepted the ontology")
            return False
        wanted = (expect,) if isinstance(expect, str) else expect
        missing = [w for w in wanted if w not in output.lower()]
        if missing:
            print(f"  FAIL [{name}]: non-zero exit, but the report is missing {missing}")
            print("        " + output.strip().splitlines()[-1])
            return False
        print(f"  ok   [{name}]")
        return True


def main() -> int:
    robot = robot_command()
    if robot is None:
        print("SKIP test_reason: ROBOT or Java not found. Set ROBOT_JAR or put robot on PATH.")
        return 0

    # Baseline: the unmodified tree must reason cleanly, or the results below
    # mean nothing. ROBOT infers output format from the file extension, so an
    # extensionless os.devnull fails setup -- write to a throwaway .owl instead.
    with tempfile.TemporaryDirectory() as tmp:
        proc = subprocess.run(
            [*robot, "merge", "--input", str(ROOT / "src" / "fmo.ttl"),
             "--input", str(ROOT / EXAMPLE),
             "--input", str(ROOT / TRADING),
             "--catalog", str(ROOT / "src" / "catalog-v001.xml"),
             "reason", "--reasoner", "HermiT", "--output", str(Path(tmp) / "baseline.owl")],
            capture_output=True, text=True,
        )
    if proc.returncode != 0:
        print("BASELINE FAIL: the unmodified tree does not reason cleanly")
        print(proc.stdout + proc.stderr)
        return 1
    print("  ok   [baseline: the unmodified tree is consistent]")

    results = [run_case(robot, *case) for case in CASES]
    passed, total = sum(results) + 1, len(results) + 1
    print(f"\n{passed}/{total} reasoner guards fire")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
