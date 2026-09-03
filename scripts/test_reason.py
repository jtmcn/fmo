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

Skips with a notice when ROBOT or Java is missing or does not run. What "usable"
means is reasoner.py's to say, and every target now asks it -- `make reason`
included, which used to answer for itself and get it wrong.

Run: python3 scripts/test_reason.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).resolve().parent))

from reasoner import ReasonerBroken, robot_command  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = "examples/kxhighny-2026-08-15.ttl"
TRADING = "examples/kxhighny-2026-08-15-trading.ttl"

# (name, path-to-mutate, find, replace), then optionally the substrings the reasoner's
# report must contain -- defaulting to "inconsistent", the shape a data mistake takes --
# and the modules to reason over, defaulting to the whole ontology plus the two examples.
# A case narrows that last field when the axiom it tests is asserted in more than one
# module and the superset would answer for the one under test.
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
        # The partition on ksh:BinaryContract. Note what this does and does not
        # catch: the union does not refuse a third subclass, it forces one into
        # ksh:YesContract or ksh:NoContract. Minting an undecorated third side is
        # therefore consistent, and correctly so. What the union refuses is a third
        # side that is genuinely a third -- disjoint from both -- which is why the
        # mutant declares that disjointness rather than relying on the name. No data
        # exercises it, so the ontology stays consistent and the class is
        # unsatisfiable instead.
        "a contract side disjoint from both under the binary partition",
        "src/kalshi.ttl",
        "ksh:TraderRole a owl:Class ;",
        """ksh:ScalarContract a owl:Class ;
    rdfs:subClassOf ksh:BinaryContract ;
    owl:disjointWith ksh:YesContract , ksh:NoContract ;
    rdfs:label "scalar contract" ;
    skos:definition "A third side, injected by scripts/test_reason.py." .

ksh:TraderRole a owl:Class ;""",
        ("unsatisfiable", "kalshi#ScalarContract"),
    ),
    (
        # The core-only half of the designation disjointness. Every other case
        # reasons over src/fmo.ttl, where kalshi.ttl's superset block satisfies this
        # too -- so deleting core.ttl's block as redundant left the whole suite
        # green. This case reasons over core.ttl alone, which is the import path the
        # block exists for and the only way to tell the two blocks apart.
        "a core designation cross-typed, reasoning over core.ttl alone",
        "src/core.ttl",
        "fm:BrierScore a fm:ScoringRule, owl:NamedIndividual ;",
        "fm:BrierScore a fm:ScoringRule, fm:TruthValue, owl:NamedIndividual ;",
        "inconsistent",
        ("src/core.ttl",),
    ),
]


# What one case run tells us. The third is not a verdict and must never be read as
# one: a non-zero exit whose report does not name what the case expects can be the
# wrong inconsistency, a JVM that never started, or ROBOT itself failing. Collapsing
# it into "the case did not fire" is what let a broken java score nine axiom pins as
# verified, printing the same OK a real run prints.
FIRED = "fired"
ACCEPTED = "accepted"
UNREADABLE = "unreadable"
Outcome = Literal["fired", "accepted", "unreadable"]


def run_case(robot: list[str], name: str, rel: str, find: str, replace: str,
             expect: str | tuple[str, ...] = "inconsistent",
             inputs: tuple[str, ...] = ("src/fmo.ttl", EXAMPLE, TRADING),
             drop_axiom: str | None = None, quiet: bool = False) -> Outcome:
    # drop_axiom lets check_axioms.py delete one axiom and re-run the case, proving
    # the case is pinned to that axiom rather than merely passing near it. It is
    # applied AFTER the text mutation, never before: deleting an axiom means
    # reserialising the module, which destroys the anchors `find` looks for, and a
    # setup failure would then be indistinguishable from a guard that stopped firing.
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "fmo"
        shutil.copytree(
            ROOT, work,
            ignore=shutil.ignore_patterns(".git", "build", "__pycache__", "*.pyc", ".venv"),
        )
        target = work / rel
        text = target.read_text()
        if text.count(find) != 1:
            if not quiet:
                print(f"  SETUP FAIL [{name}]: anchor found {text.count(find)} times in {rel}")
            raise LookupError(f"anchor found {text.count(find)} times in {rel}")
        target.write_text(text.replace(find, replace))

        if drop_axiom:
            import axioms
            module = work / "src" / drop_axiom.split(":", 1)[0]
            module.write_text(
                axioms.remove_site(drop_axiom, module.read_text(encoding="utf-8")),
                encoding="utf-8",
            )

        merge_inputs = [a for rel_in in inputs for a in ("--input", str(work / rel_in))]
        proc = subprocess.run(
            [*robot, "merge", *merge_inputs,
             "--catalog", str(work / "src" / "catalog-v001.xml"),
             "reason", "--reasoner", "HermiT",
             "--output", str(work / "reasoned.owl")],
            capture_output=True, text=True,
        )
        output = proc.stdout + proc.stderr
        if proc.returncode == 0:
            if not quiet:
                print(f"  FAIL [{name}]: the reasoner accepted the ontology")
            return ACCEPTED
        wanted = (expect,) if isinstance(expect, str) else expect
        # Both sides lower-cased: expectations get written with the IRI as it
        # appears in the source, and a case that can never match reads as a
        # broken ontology rather than as a typo in the expectation.
        missing = [w for w in wanted if w.lower() not in output.lower()]
        if missing:
            if not quiet:
                print(f"  FAIL [{name}]: non-zero exit, but the report is missing {missing}")
                print("        " + output.strip().splitlines()[-1])
            # Deliberately not ACCEPTED. The reasoner exited non-zero, so it did not
            # accept anything; what it did instead is unknown, and a caller asking
            # "did the case fire?" has to be told it has no answer rather than "no".
            return UNREADABLE
        if not quiet:
            print(f"  ok   [{name}]")
        return FIRED


def main() -> int:
    try:
        robot, why = robot_command()
    except ReasonerBroken as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    if robot is None:
        print(f"SKIP test_reason: {why}")
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

    results = []
    for case in CASES:
        try:
            results.append(run_case(robot, *case) == FIRED)
        except LookupError:
            # The anchor moved. That is a broken case, not a guard that stopped
            # firing, and the two must not read alike -- run_case raises so that
            # check_axioms.py cannot score a setup failure as a pinned axiom.
            results.append(False)
    passed, total = sum(results) + 1, len(results) + 1
    print(f"\n{passed}/{total} reasoner guards fire")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
