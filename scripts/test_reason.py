#!/usr/bin/env python3
"""Negative tests for the axioms that only a reasoner enforces.

scripts/validate.py is deliberately Java-free, so the guards whose whole job is to
turn a mistake into a HermiT inconsistency have no coverage there: the
owl:AllDifferent blocks in core.ttl -- over the units and over the truth values --
the irreflexivity of wx:alternativeDeterminationOf, and the disjointness of the two
contract sides in kalshi.ttl. Each case here injects the mistake the guard exists for
and asserts ROBOT reports the ontology inconsistent.

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

# (name, path-to-mutate, find, replace)
CASES = [
    (
        # The trap README and core.ttl both warn about: wtl:hasUnit is functional,
        # so a multi-valued sub-property forces every unit listed for a variable to
        # be one individual -- knots identified with metres per second.
        "conventionalUnit made a sub-property of the functional hasUnit",
        "src/weather.ttl",
        """wx:conventionalUnit a owl:ObjectProperty ;
    rdfs:label "conventional unit" ;""",
        """wx:conventionalUnit a owl:ObjectProperty ;
    rdfs:subPropertyOf wtl:hasUnit ;
    rdfs:label "conventional unit" ;""",
    ),
    (
        # The AllDifferent block over the truth values. wtl:assessedTruthValue is
        # functional, so two values on one assessment would identify wtl:True with
        # wtl:False -- and everything downstream would keep computing -- if the
        # individuals were not asserted distinct.
        "one assessment asserting two truth values",
        EXAMPLE,
        "    wtl:assessedTruthValue wtl:True ;",
        "    wtl:assessedTruthValue wtl:True , wtl:False ;",
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
        "    wtl:hasInput ex:Resolution-B82 , tex:Lot-Yes-A ;",
        "    wtl:hasInput ex:Resolution-B82 , tex:Lot-Yes-A , tex:Lot-No-B ;",
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


def run_case(robot: list[str], name: str, rel: str, find: str, replace: str) -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "wantology"
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
             "--input", str(work / "src" / "wantology.ttl"),
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
        if "inconsistent" not in output.lower():
            print(f"  FAIL [{name}]: non-zero exit but not an inconsistency report")
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
            [*robot, "merge", "--input", str(ROOT / "src" / "wantology.ttl"),
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
