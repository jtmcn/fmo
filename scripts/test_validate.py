#!/usr/bin/env python3
"""Negative tests for scripts/validate.py.

A validator that has only ever been seen to pass is not known to work. Each case here
introduces one specific defect into a copy of the example data, runs the validator, and
asserts it fails with the expected message. The source tree is never modified.

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


def run_case(name: str, rel: str, find: str, replace: str, expect: str) -> bool:
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
            [sys.executable, "scripts/validate.py"],
            cwd=work, capture_output=True, text=True,
        )
        output = proc.stdout + proc.stderr

        if proc.returncode == 0:
            print(f"  FAIL [{name}]: validator passed but should have failed")
            return False
        if expect not in output:
            print(f"  FAIL [{name}]: exited non-zero but message missing")
            print(f"         expected substring: {expect!r}")
            return False
        print(f"  ok   [{name}]")
        return True


def main() -> int:
    # Baseline: the unmodified tree must pass, or the negative results mean nothing.
    proc = subprocess.run(
        [sys.executable, "scripts/validate.py"],
        cwd=ROOT, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        print("BASELINE FAIL: validate.py does not pass on the unmodified tree")
        print(proc.stdout + proc.stderr)
        return 1
    print("  ok   [baseline: clean tree passes]")

    results = [run_case(*case) for case in CASES]
    passed, total = sum(results), len(results) + 1

    print(f"\n{passed + 1}/{total} checks passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
