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
BRACKETS = "examples/kxhighny-2026-08-15-bracketset.ttl"
CORRECTION = "examples/kxhighny-2026-08-15-correction.ttl"
VERIFICATION = "examples/verification-synthetic.ttl"

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
        """    wx:underProtocol ex:TWCDailyTempProtocol ;
    wtl:hasUnit unit:DEG_F .""",
        """    wx:underProtocol ex:TWCDailyTempProtocol ;
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
        # The bug this check exists for: re-pointing the settlement source renamed
        # ex:NWSDailyClimateProtocol, and verification-synthetic.ttl went on
        # referencing it for all 40 days. Every other check stayed green.
        "a referenced individual no longer exists",
        EXAMPLE,
        """    wx:underProtocol ex:TWCDailyTempProtocol ;""",
        """    wx:underProtocol ex:RenamedAwayProtocol ;""",
        "undefined term referenced in examples",
    ),
    (
        # The same defect one namespace over: this PR deleted ksh:Settled, and the
        # check only looked at example-namespace IRIs, so a stale reference passed.
        # rdfs:range means HermiT infers the type rather than objecting.
        "a referenced schema individual no longer exists",
        EXAMPLE,
        """    ksh:hasStatus ksh:Finalized ;""",
        """    ksh:hasStatus ksh:Settled ;""",
        "undefined term referenced in examples",
    ),
    (
        # The misalignment the bridge relation exists to make detectable: score the
        # forecast against the NWS determination while the market settles on TWC.
        # Both targets are real and declared alternative determinations, so nothing
        # is dangling and nothing is unrooted -- only the authorities differ.
        "forecast scored against a different authority than the market settles on",
        EXAMPLE,
        """    wx:forecastFor ex:Target-HighTemp ;""",
        """    wx:forecastFor ex:Target-HighTemp-NWS ;""",
        "forecast target is not the subject of the proposition",
    ),
    (
        # Zero-coverage guard for check 6b. Mutated in the checker rather than the
        # data because the synthetic set repeats the has-part link 160 times, so no
        # single-anchor edit can empty the traversal -- and a renamed BFO IRI is the
        # refactor that would silently reduce the check to "0 pairs checked, OK".
        "the forecast-target check traverses nothing",
        "scripts/validate.py",
        """    has_part = URIRef(BFO + "BFO_0000178")""",
        """    has_part = URIRef(BFO + "BFO_0000178_renamed")""",
        "the has-part or assignsProbabilityTo chain is broken",
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
        "the only forecast probability downgraded, breaking the join",
        EXAMPLE,
        """ex:ForecastProb-82-83 a wtl:ForecastProbability ;""",
        """ex:ForecastProb-82-83 a wtl:ProbabilityAssignment ;""",
        "the forecast/market join is not demonstrated",
    ),
    (
        # A stored derived value that no longer matches its inputs. Silent without
        # this check, and CQ6 would bucket the forecast by the wrong lead time.
        "lead time no longer matches issuance and interval start",
        EXAMPLE,
        """    wx:leadTimeHours "-4.667"^^xsd:decimal ;""",
        """    wx:leadTimeHours "24"^^xsd:decimal ;""",
        "wx:leadTimeHours says",
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
    (
        # Finding: a missing unit used to be `continue`d, so deleting one made the
        # comparison vanish rather than fail -- an omission is as likely a slip as
        # a wrong unit, and only the wrong-unit case had coverage.
        "threshold with a numeric value but no unit at all",
        EXAMPLE,
        """    wtl:capValue "83"^^xsd:decimal ;
    wtl:hasUnit unit:DEG_F ;""",
        """    wtl:capValue "83"^^xsd:decimal ;""",
        "carries a numeric value but no wtl:hasUnit",
    ),
    (
        # wtl:hasUnit is functional, so HermiT catches this -- but `make reason` is
        # the Java-optional path, and unit_of used to take units[0] from an
        # unordered list, which is precisely the Celsius/Fahrenheit defect above.
        "two units on one term, so the unit check picks one arbitrarily",
        EXAMPLE,
        """    wtl:capValue "83"^^xsd:decimal ;
    wtl:hasUnit unit:DEG_F ;""",
        """    wtl:capValue "83"^^xsd:decimal ;
    wtl:hasUnit unit:DEG_F , unit:DEG_C ;""",
        "ambiguous unit",
    ),
    (
        # Used to raise an uncaught TypeError (naive minus aware), which killed
        # every later check and report() with it, so the operator got a traceback
        # instead of the file and term at fault.
        "issuance time written without a UTC offset",
        EXAMPLE,
        """    wx:issuanceTime "2026-08-15T09:40:00Z"^^xsd:dateTime ;""",
        """    wx:issuanceTime "2026-08-15T09:40:00"^^xsd:dateTime ;""",
        "cannot measure lead time from issuance",
    ),
    (
        # forecastFor is not functional, so a second target left the lead time
        # checked against whichever one rdflib yielded first.
        "forecast covering a second target, making its lead time ambiguous",
        EXAMPLE,
        """    bfo:BFO_0000178 ex:ForecastProb-82-83 .     # has continuant part""",
        """    wx:forecastFor ex:Target-LowTemp ;
    bfo:BFO_0000178 ex:ForecastProb-82-83 .     # has continuant part

ex:Target-LowTemp a wx:ObservationTarget ;
    rdfs:label "min temperature at KNYC" ;
    wtl:overTemporalInterval ex:ClimDay-2026-08-15 ;
    wtl:hasUnit unit:DEG_F .""",
        "lead time is ambiguous",
    ),
    (
        # Check 5 only ever appended to notes, so eight live terms had no
        # definition while CLAUDE.md promised the validator failed without one.
        "a term left without a skos:definition",
        "src/weather.ttl",
        """    skos:definition "The atmospheric quality corresponding to the compass bearing from which a portion of air is moving." .""",
        """    skos:scopeNote "Reported as the bearing the wind blows FROM." .""",
        "no skos:definition: https://w3id.org/wantology/weather#WindDirection",
    ),
    (
        # Check 2b hard-coded two QUDT IRIs, so the third class the generator adds
        # floated under owl:Thing -- the exact defect 2b exists to catch.
        "a bridged QUDT class left unrooted",
        "src/core.ttl",
        """qudt:QuantityKindDimensionVector rdfs:subClassOf wtl:Designation .""",
        """""",
        "bridged external class not grounded in BFO",
    ),
    (
        # our_classes was built from `a owl:Class` alone, so a class introduced by
        # subClassOf only was invisible to every check rather than merely unrooted.
        "a class introduced by rdfs:subClassOf without being declared",
        "src/kalshi.ttl",
        """ksh:Position a owl:Class ;""",
        """ksh:UndeclaredPosition rdfs:subClassOf ksh:Position .

ksh:Position a owl:Class ;""",
        "no rdfs:label: https://w3id.org/wantology/kalshi#UndeclaredPosition",
    ),
    (
        # ksh:settlementValue is a sub-property of wtl:realizedValue, and rdflib
        # does no reasoning, so the unit rules did not reach the one number the
        # exchange actually pays out on.
        "settlement value recorded in Celsius against a Fahrenheit target",
        EXAMPLE,
        """    ksh:resolvesTo ksh:ResolvedYes ;
    ksh:settlementValue "82"^^xsd:decimal ;
    wtl:hasUnit unit:DEG_F .""",
        """    ksh:resolvesTo ksh:ResolvedYes ;
    ksh:settlementValue "82"^^xsd:decimal ;
    wtl:hasUnit unit:DEG_C .""",
        "unit mismatch (settlement value vs target)",
    ),
    (
        "settlement value with no unit at all",
        EXAMPLE,
        """    ksh:settlementValue "82"^^xsd:decimal ;
    wtl:hasUnit unit:DEG_F .""",
        """    ksh:settlementValue "82"^^xsd:decimal .""",
        "missing unit",
    ),
    (
        # Zero-coverage guard for the settlement-value check. Mutated in the checker
        # rather than the data because the four resolutions live in two files, so no
        # single-anchor edit can empty the traversal -- and a renamed property IRI is
        # the refactor that would silently reduce the check to "0 pairs checked, OK".
        "the settlement-value check traverses nothing",
        "scripts/validate.py",
        """RESOLUTION_OF = URIRef(KSH + "resolutionOf")""",
        """RESOLUTION_OF = URIRef(KSH + "resolutionOf_renamed")""",
        "the resolutionOf or expressesProposition chain is broken",
    ),
    (
        # Demonstrated on 0.7.0: one duplicate assessment moved CQ6b's n from 160
        # to 161 and shifted every calibration statistic, while validate.py said OK.
        "a proposition carries two assessments of the current record",
        VERIFICATION,
        """vex:A-20260701-LE81 a wtl:TruthAssessment ;
    wtl:assessesProposition vex:P-20260701-LE81 ;""",
        """vex:A-20260701-LE81-DUPLICATE a wtl:TruthAssessment ;
    wtl:assessesProposition vex:P-20260701-LE81 ;
    wtl:assessedTruthValue wtl:False ;
    wtl:basedOnRecord vex:Report-20260701 ;
    wtl:referenceTime "2026-07-02T10:59:59-04:00"^^xsd:dateTime .

vex:A-20260701-LE81 a wtl:TruthAssessment ;
    wtl:assessesProposition vex:P-20260701-LE81 ;""",
        "more than one current assessment",
    ),
    (
        # A stored derived value with nothing checking it is the lead-time
        # problem again: it goes stale the moment either input moves.
        "Brier score no longer matches the probability and outcome it scores",
        CORRECTION,
        """    wtl:scoreValue "0.2704"^^xsd:decimal ;""",
        """    wtl:scoreValue "0.1024"^^xsd:decimal ;""",
        "Brier score mismatch",
    ),
    (
        # Scoring against the settlement-era assessment measures what the exchange
        # did, not what the record says. The whole point of wtl:scoredAgainst.
        "score points at an assessment of a superseded record",
        CORRECTION,
        """    wtl:scoredAgainst ex:Reassessment-82-83 ;""",
        """    wtl:scoredAgainst ex:Assessment-82-83-at-settlement ;""",
        "score rests on a superseded record",
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
        "a bracket drops out of the ladder",
        BRACKETS,
        """    ksh:marketTicker "KXHIGHNY-26AUG15-T86" ;
    ksh:inEventGrouping ex:KXHIGHNY-26AUG15 ;""",
        """    ksh:marketTicker "KXHIGHNY-26AUG15-T86" ;""",
        "differs from",
    ),
    (
        "ladder priced so the whole set costs under a dollar",
        EXAMPLE,
        """    ksh:yesAskCents 62 ;""",
        """    ksh:yesAskCents 30 ;""",
        "differs from",
    ),
    (
        # Restores empty-result coverage: with no supersedes link there is no
        # correction to check against, so CQ7 has nothing to report.
        "correction no longer supersedes the report it replaces",
        CORRECTION,
        """    wx:supersedes ex:TWCRecord-2026-08-16 ;""",
        """""",
        "returned 0 rows",
    ),
    (
        "corrected value changed, so the contradiction verdicts flip",
        CORRECTION,
        """    wtl:realizedValue "84"^^xsd:decimal ;""",
        """    wtl:realizedValue "81"^^xsd:decimal ;""",
        "differs from",
    ),
    (
        "an outcome flipped in the verification sample",
        VERIFICATION,
        """vex:A-20260701-LE81 a wtl:TruthAssessment ;
    wtl:assessesProposition vex:P-20260701-LE81 ;
    wtl:assessedTruthValue wtl:False ;""",
        """vex:A-20260701-LE81 a wtl:TruthAssessment ;
    wtl:assessesProposition vex:P-20260701-LE81 ;
    wtl:assessedTruthValue wtl:True ;""",
        "differs from",
    ),
    (
        # Was "returned 0 rows" when the example held a single settlement. With the
        # full ladder there are four, so dropping one leaves three and the failure
        # mode is a differing result rather than an empty one. The empty-result path
        # is still covered by the broken-join case above.
        "settlement no longer records the document it read",
        EXAMPLE,
        """    wtl:hasInput ex:TWCRecord-2026-08-16 ;""",
        """""",
        "differs from",
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
            [sys.executable, *script.split()],
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

    # --update used to return 0 unconditionally. A query that errors or returns
    # nothing skips its write, so the stale .expected survives and `make cq-update`
    # reported success with no diff for exactly the query that was broken.
    print("\n  -- cq-update --")
    results.append(run_case(
        *COMPETENCY_CASES[0][:4],
        "returned 0 rows",
        script="scripts/run_competency.py --update",
    ))

    passed, total = sum(results) + 2, len(results) + 2
    print(f"\n{passed}/{total} checks passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
