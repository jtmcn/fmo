#!/usr/bin/env python3
"""Negative tests for scripts/validate.py and scripts/run_competency.py.

A check that has only ever been seen to pass is not known to work. Each case here
introduces one specific defect into a copy of the tree, runs the checker, and asserts it
fails with the expected message. The source tree is never modified.

Run: python3 scripts/test_validate.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = "examples/kxhighny-2026-08-15.ttl"

# (name, path-to-mutate, find, replace, substring expected in the failure output)
CASES = [
    (
        "Celsius threshold against a Fahrenheit target",
        EXAMPLE,
        """    wtl:capValue "83"^^xsd:decimal ;
    wtl:hasUnit unit:DEG_F ;""",
        """    wtl:capValue "83"^^xsd:decimal ;
    wtl:hasUnit unit:DEG_C ;""",
        "unit mismatch (proposition threshold vs target)",
    ),
    (
        "length unit on a temperature target",
        EXAMPLE,
        """    wx:underProtocol ex:NWSDailyClimateProtocol ;
    wtl:hasUnit unit:DEG_F .""",
        """    wx:underProtocol ex:NWSDailyClimateProtocol ;
    wtl:hasUnit unit:IN .""",
        "dimension mismatch (proposition threshold vs target)",
    ),
    (
        "datum reported in Celsius for a Fahrenheit target",
        EXAMPLE,
        """    wtl:realizedValue "82"^^xsd:decimal ;
    wtl:hasUnit unit:DEG_F .""",
        """    wtl:realizedValue "82"^^xsd:decimal ;
    wtl:hasUnit unit:DEG_C .""",
        "unit mismatch (datum vs target)",
    ),
    (
        "class unrooted from BFO",
        "src/kalshi.ttl",
        """ksh:Position a owl:Class ;
    rdfs:subClassOf wtl:InformationContentEntity ;""",
        """ksh:Position a owl:Class ;""",
        "not grounded in BFO",
    ),
    (
        "information artifact misfiled as a process",
        "src/kalshi.ttl",
        """ksh:Resolution a owl:Class ;
    rdfs:subClassOf wtl:InformationContentEntity ;""",
        """ksh:Resolution a owl:Class ;
    rdfs:subClassOf wtl:InformationContentEntity , bfo:BFO_0000015 ;""",
        "both continuant and occurrent",
    ),
]


# Defects that must break a competency question rather than quietly changing its answer.
COMPETENCY_CASES = [
    (
        "forecast and market probabilities no longer share a proposition",
        EXAMPLE,
        """ex:ForecastProb-82-83 a wtl:ForecastProbability ;
    rdfs:label "GEFS 06Z P(82-83F)" ;
    wtl:assignsProbabilityTo ex:Prop-82-83 ;""",
        """ex:Prop-decoy a wtl:Proposition ;
    rdfs:label "decoy proposition" ;
    wtl:hasSubject ex:Target-HighTemp .

ex:ForecastProb-82-83 a wtl:ForecastProbability ;
    rdfs:label "GEFS 06Z P(82-83F)" ;
    wtl:assignsProbabilityTo ex:Prop-decoy ;""",
        "returned 0 rows",
    ),
    (
        "a probability value silently changed",
        EXAMPLE,
        """    wtl:probabilityValue "0.52"^^xsd:decimal ;""",
        """    wtl:probabilityValue "0.41"^^xsd:decimal ;""",
        "differs from",
    ),
    (
        "settlement no longer records the document it read",
        EXAMPLE,
        """    wtl:hasInput ex:CLINYC-2026-08-16 ;""",
        """""",
        "returned 0 rows",
    ),
]


def run_case(name: str, rel: str, find: str, replace: str, expect: str,
             script: str = "scripts/validate.py") -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "wantology"
        shutil.copytree(
            ROOT, work,
            ignore=shutil.ignore_patterns(".git", "build", "__pycache__", "*.pyc"),
        )
        target = work / rel
        text = target.read_text()
        if text.count(find) != 1:
            print(f"  SETUP FAIL [{name}]: anchor found {text.count(find)} times in {rel}")
            return False
        target.write_text(text.replace(find, replace))

        proc = subprocess.run(
            [sys.executable, script],
            cwd=work, capture_output=True, text=True,
        )
        output = proc.stdout + proc.stderr

        if proc.returncode == 0:
            print(f"  FAIL [{name}]: {Path(script).name} passed but should have failed")
            return False
        if expect not in output:
            print(f"  FAIL [{name}]: exited non-zero but message missing")
            print(f"         expected substring: {expect!r}")
            return False
        print(f"  ok   [{name}]")
        return True


def main() -> int:
    # Baseline: the unmodified tree must pass both checkers, or the negative
    # results below mean nothing.
    baseline_ok = True
    for script in ("scripts/validate.py", "scripts/run_competency.py"):
        proc = subprocess.run(
            [sys.executable, script], cwd=ROOT, capture_output=True, text=True,
        )
        if proc.returncode != 0:
            print(f"BASELINE FAIL: {script} does not pass on the unmodified tree")
            print(proc.stdout + proc.stderr)
            baseline_ok = False
        else:
            print(f"  ok   [baseline: {Path(script).name} passes on clean tree]")
    if not baseline_ok:
        return 1

    print("\n  -- validator --")
    results = [run_case(*case) for case in CASES]
    print("\n  -- competency questions --")
    results += [
        run_case(*case, script="scripts/run_competency.py")
        for case in COMPETENCY_CASES
    ]

    passed, total = sum(results) + 2, len(results) + 2
    print(f"\n{passed}/{total} checks passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
