# Validation Gap Remediation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the six gaps found in the 0.7.0 audit, so that every number the ontology carries is either checked or declared unchecked.

**Architecture:** No new modelling. Five of the six fixes are new checks in `scripts/validate.py`, each paired with a negative test in `scripts/test_validate.py` per the repo rule (*new validator check ⇒ new negative test*). Two competency queries get the duplicate-collapsing treatment CQ5 already has. One task adds example data to exercise the scoring layer, which no instance touches today. `src/*.ttl` term definitions are unchanged throughout, so **no version bump** — the exception is the optional trading-layer deletion in Task 5, which would be a 0.8.0 change.

**Tech Stack:** Turtle/OWL 2 DL, rdflib (no reasoner in `validate.py`), SPARQL 1.1, ROBOT + HermiT, GNU make, poetry.

**Spec:** The "Findings" section below — the 2026-08-17 audit of 0.7.0. There is no separate spec document.

## Global Constraints

- Every check runs under `poetry run`; `validate.py` must stay Java-free.
- **An empty result fails.** A new check that traverses nothing must `fail()`, not pass quietly — the precedent is the forecast-target check.
- **New validator check ⇒ new negative test** in `scripts/test_validate.py`, asserting the specific failure message.
- SPARQL does no subclass reasoning: class patterns use `a/rdfs:subClassOf*`.
- `src/imports/bfo-core.ttl` is vendored and never edited. `examples/verification-synthetic.ttl` is generated — change `scripts/generate_verification_data.py`, never the file.
- Adding a source file means updating `MODULES` in `scripts/validate.py` and `scripts/run_competency.py`, plus `src/fmo.ttl` and `src/catalog-v001.xml`. No task here adds one.
- `make test` must pass at the end of every task.

## Findings this plan addresses

| # | Finding | Task |
|---|---|---|
| 1 | `ksh:settlementValue` escapes every unit check; all four example resolutions carry a bare number | 1 |
| 2 | A duplicate `fm:TruthAssessment` silently inflates CQ6a/6b (demonstrated: n 160→161, every statistic moved) while `validate.py` prints OK | 2 |
| 3 | Nothing proves `examples/verification-synthetic.ttl` still matches its generator | 3 |
| 4 | No negative test covers the two reasoner-only guards (`owl:AllDifferent` + functional `hasUnit`; irreflexive `alternativeDeterminationOf`) | 4 |
| 5 | The scoring layer (`fm:SkillScore`, `fm:BrierScore`, `fm:scoresAssignment`, `fm:usesScoringRule`, `fm:scoredAgainst`, `fm:scoreValue`, `wx:ForecastVerification`) has zero instances; so does the trading layer | 5 |
| 6 | No check that a market's proposition subject matches its grouping's `ksh:coversTarget`; no check that a mutually exclusive ladder's brackets do not overlap | 6 |

---

### Task 1: Unit coherence for the settlement value

**Why:** `ksh:settlementValue` is `rdfs:subPropertyOf fm:realizedValue`, but `validate.py` matches predicates literally and runs no reasoner, so the "numeric value with no unit" rule never reaches it. It is the number that decides payouts and it is the only load-bearing quantity in the graph with no unit discipline.

**Files:**
- Modify: `scripts/validate.py` (constants block near `HAS_UNIT`, ~line 100-115; `check_dimensions`, ~line 200-215)
- Modify: `examples/kxhighny-2026-08-15.ttl:262-266` (`ex:Resolution-B82`)
- Modify: `examples/kxhighny-2026-08-15-bracketset.ttl:230,242,254` (`ex:Resolution-T81`, `-B84`, `-T86`)
- Test: `scripts/test_validate.py` (append to `CASES`, before the closing `]` at ~line 205)

**Interfaces:**
- Produces: module-level `KSH` prefix constant and `SETTLEMENT_VALUE` URIRef in `validate.py`, used again by Task 6.
- Failure messages: `"unit mismatch (settlement value vs target)"`, `"missing unit: ... carries a numeric value but no fm:hasUnit"`.

- [ ] **Step 1: Write the failing negative tests**

Append to `CASES` in `scripts/test_validate.py`:

```python
    (
        # ksh:settlementValue is a sub-property of fm:realizedValue, and rdflib
        # does no reasoning, so the unit rules did not reach the one number the
        # exchange actually pays out on.
        "settlement value recorded in Celsius against a Fahrenheit target",
        EXAMPLE,
        """    ksh:resolvesTo ksh:ResolvedYes ;
    ksh:settlementValue "82"^^xsd:decimal ;
    fm:hasUnit unit:DEG_F .""",
        """    ksh:resolvesTo ksh:ResolvedYes ;
    ksh:settlementValue "82"^^xsd:decimal ;
    fm:hasUnit unit:DEG_C .""",
        "unit mismatch (settlement value vs target)",
    ),
    (
        "settlement value with no unit at all",
        EXAMPLE,
        """    ksh:settlementValue "82"^^xsd:decimal ;
    fm:hasUnit unit:DEG_F .""",
        """    ksh:settlementValue "82"^^xsd:decimal .""",
        "missing unit",
    ),
```

- [ ] **Step 2: Add the units to the example data, so the anchors above exist**

In `examples/kxhighny-2026-08-15.ttl`, change `ex:Resolution-B82` to end:

```turtle
ex:Resolution-B82 a ksh:Resolution ;
    rdfs:label "KXHIGHNY-26AUG15-B82.5 resolved yes" ;
    ksh:resolutionOf ex:Market-B82 ;
    ksh:resolvesTo ksh:ResolvedYes ;
    ksh:settlementValue "82"^^xsd:decimal ;
    fm:hasUnit unit:DEG_F .
```

Make the same edit to `ex:Resolution-T81`, `ex:Resolution-B84` and `ex:Resolution-T86` in `examples/kxhighny-2026-08-15-bracketset.ttl` (each currently ends `ksh:settlementValue "82"^^xsd:decimal .`). The bracket-set file already declares the `unit:` prefix.

- [ ] **Step 3: Run the negative tests to verify they fail**

Run: `poetry run python3 scripts/test_validate.py`
Expected: both new cases print `FAIL [...]: validate.py passed but should have failed` — the check does not exist yet.

- [ ] **Step 4: Implement the check**

In `scripts/validate.py`, beside the existing `QUDT`/`WTL`/`WX` constants:

```python
KSH = "https://w3id.org/forecast-market-ontology/kalshi#"

SETTLEMENT_VALUE = URIRef(KSH + "settlementValue")
RESOLUTION_OF = URIRef(KSH + "resolutionOf")
EXPRESSES = URIRef(KSH + "expressesProposition")
```

Add `SETTLEMENT_VALUE` to `VALUE_PROPS`:

```python
VALUE_PROPS = (URIRef(WTL + "floorValue"), URIRef(WTL + "capValue"),
               URIRef(WTL + "realizedValue"), SETTLEMENT_VALUE)
```

Then inside `check_dimensions`, after the `reportsValueFor` loop:

```python
    # The exchange's own number, against the target the market settles on. It
    # reaches the target through the market's proposition rather than directly,
    # so no earlier loop sees it -- and ksh:settlementValue is a sub-property of
    # fm:realizedValue, which rdflib does not follow.
    for resolution, market in g.subject_objects(RESOLUTION_OF):
        if not any(g.objects(resolution, SETTLEMENT_VALUE)):
            continue
        for prop in g.objects(market, EXPRESSES):
            for target in g.objects(prop, HAS_SUBJECT):
                check_identical(resolution, unit_of(resolution),
                                target, unit_of(target),
                                "settlement value vs target")
                compared += 1
```

- [ ] **Step 5: Verify**

Run: `poetry run python3 scripts/validate.py && poetry run python3 scripts/test_validate.py`
Expected: validate prints `OK` with a higher `unit coherence: N comparison pair(s) checked` (253, up from 249); test_validate prints `31/31 checks passed`.

- [ ] **Step 6: Commit**

```bash
git add scripts/validate.py scripts/test_validate.py examples/kxhighny-2026-08-15.ttl examples/kxhighny-2026-08-15-bracketset.ttl
git commit -m "Unit-check the settlement value, which sub-property matching let through"
```

---

### Task 2: One current assessment per proposition, and collapse duplicates in CQ6

**Why:** Appending one extra `fm:TruthAssessment` for a proposition that already has one leaves `validate.py` printing OK while CQ6b's n goes 160→161 and every calibration figure shifts. Only the pinned `.expected` noticed, and that pin does not exist for real data. CQ5 already solved the same shape by collapsing to one row per market before summing; CQ6a/6b never got the treatment.

**Files:**
- Modify: `scripts/validate.py` (new `check_current_assessments`, called from `main()` beside `check_lead_times`)
- Modify: `queries/cq06a-calibration-reliability.rq`, `queries/cq06b-skill-by-leadtime.rq`
- Regenerate: `queries/cq06a-calibration-reliability.expected`, `queries/cq06b-skill-by-leadtime.expected`
- Test: `scripts/test_validate.py` (append to `CASES`)

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: failure message `"more than one current assessment"`; a new `?sourceRows` column in both CQ6 result sets.

- [ ] **Step 1: Write the failing negative test**

Append to `CASES` in `scripts/test_validate.py`:

```python
    (
        # Demonstrated on 0.7.0: one duplicate assessment moved CQ6b's n from 160
        # to 161 and shifted every calibration statistic, while validate.py said OK.
        "a proposition carries two assessments of the current record",
        VERIFICATION,
        """vex:A-20260701-LE81 a fm:TruthAssessment ;
    fm:assessesProposition vex:P-20260701-LE81 ;""",
        """vex:A-20260701-LE81-DUPLICATE a fm:TruthAssessment ;
    fm:assessesProposition vex:P-20260701-LE81 ;
    fm:assessedTruthValue fm:False ;
    fm:basedOnRecord vex:Report-20260701 ;
    fm:referenceTime "2026-07-02T10:59:59-04:00"^^xsd:dateTime .

vex:A-20260701-LE81 a fm:TruthAssessment ;
    fm:assessesProposition vex:P-20260701-LE81 ;""",
        "more than one current assessment",
    ),
```

- [ ] **Step 2: Run it to verify it fails**

Run: `poetry run python3 scripts/test_validate.py`
Expected: `FAIL [a proposition carries two assessments of the current record]: validate.py passed but should have failed`.

- [ ] **Step 3: Implement the check**

In `scripts/validate.py`, add the constants beside the others:

```python
ASSESSES = URIRef(WTL + "assessesProposition")
BASED_ON_RECORD = URIRef(WTL + "basedOnRecord")
SUPERSEDES = URIRef(WX + "supersedes")
```

and the function, next to `check_lead_times`:

```python
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
    if EXAMPLES and not by_proposition:
        fail(
            "no proposition has a current assessment, so the assessment check "
            "matched nothing; the assessesProposition chain is broken"
        )
    notes.append(f"{len(by_proposition)} proposition(s) checked for a single current assessment")
```

Call it in `main()` immediately after `check_lead_times(ex)`:

```python
    check_current_assessments(ex)
```

- [ ] **Step 4: Verify the check fires and the clean tree still passes**

Run: `poetry run python3 scripts/validate.py && poetry run python3 scripts/test_validate.py`
Expected: validate prints `OK` and a new note `164 proposition(s) checked for a single current assessment`; test_validate prints `32/32 checks passed`.

- [ ] **Step 5: Harden CQ6a against duplicates**

Replace the body of the inner `SELECT` in `queries/cq06a-calibration-reliability.rq` so one row per forecast probability is fixed before anything is averaged, mirroring CQ5:

```sparql
SELECT ?model ?leadHours ?bin ?n ?sourceRows ?meanForecast ?observedFreq ?calibrationGap ?meanBrier
WHERE {
    {
        SELECT ?model ?leadHours ?bin
               (COUNT(*)      AS ?n)
               (SUM(?rows)    AS ?sourceRows)
               (ROUND(AVG(?p)  * 1000) / 1000 AS ?meanForecast)
               (ROUND(AVG(?o)  * 1000) / 1000 AS ?observedFreq)
               (ROUND(AVG(?sq) * 1000) / 1000 AS ?meanBrier)
        WHERE {
            {
                # One row per forecast probability, before anything is averaged.
                # A proposition with two current assessments would otherwise join
                # twice and inflate n while every statistic quietly shifted.
                # MAX rather than SAMPLE so a duplicate gives the same answer on
                # every run; ?rows carries the fact that it happened.
                SELECT ?model ?leadHours ?fp
                       (MAX(?pv) AS ?p) (MAX(?ov) AS ?o) (COUNT(*) AS ?rows)
                WHERE {
                    ?forecast a/rdfs:subClassOf* wx:ProbabilisticForecast ;
                              wx:producedByModel ?model ;
                              wx:leadTimeHours   ?leadHours ;
                              bfo:BFO_0000178    ?fp .

                    ?fp a/rdfs:subClassOf* fm:ForecastProbability ;
                        fm:assignsProbabilityTo ?proposition ;
                        fm:probabilityValue ?pv .

                    ?assessment fm:assessesProposition ?proposition ;
                                fm:basedOnRecord ?record ;
                                fm:assessedTruthValue ?tv .
                    FILTER NOT EXISTS { ?newer wx:supersedes ?record }

                    BIND(IF(?tv = fm:True, 1, 0) AS ?ov)
                }
                GROUP BY ?model ?leadHours ?fp
            }

            BIND((?p - ?o) * (?p - ?o) AS ?sq)

            # Bins are prefixed so lexical ordering matches numeric ordering.
            BIND(IF(?p < 0.2, "1: 0.0-0.2",
                 IF(?p < 0.4, "2: 0.2-0.4",
                 IF(?p < 0.6, "3: 0.4-0.6",
                 IF(?p < 0.8, "4: 0.6-0.8",
                              "5: 0.8-1.0")))) AS ?bin)
        }
        GROUP BY ?model ?leadHours ?bin
    }
    BIND(ROUND((?meanForecast - ?observedFreq) * 1000) / 1000 AS ?calibrationGap)
}
ORDER BY ?model ?leadHours ?bin
```

Add to the header comment block, above `SELECT`:

```
# ?sourceRows IS THE DUPLICATE DETECTOR. Equals ?n on clean data. Anything higher
# means a forecast probability joined more than one current assessment and one was
# picked -- the same failure CQ5 collapses for, and the reason validate.py now
# refuses two live assessments of one proposition.
```

- [ ] **Step 6: Harden CQ6b the same way**

In `queries/cq06b-skill-by-leadtime.rq`, apply the identical inner-most collapse, add `(SUM(?rows) AS ?sourceRows)` to the outer aggregate, add `?sourceRows` to the top-level `SELECT` list, and move `?absErr` outside the collapse:

```sparql
SELECT ?model ?leadHours ?n ?sourceRows ?meanForecast ?baseRate ?meanBrier ?climatologyBrier ?meanAbsError
WHERE {
    {
        SELECT ?model ?leadHours
               (COUNT(*)   AS ?n)
               (SUM(?rows) AS ?sourceRows)
               (ROUND(AVG(?p)      * 1000) / 1000 AS ?meanForecast)
               (ROUND(AVG(?o)      * 1000) / 1000 AS ?baseRate)
               (ROUND(AVG(?sq)     * 1000) / 1000 AS ?meanBrier)
               (ROUND(AVG(?absErr) * 1000) / 1000 AS ?meanAbsError)
        WHERE {
            {
                SELECT ?model ?leadHours ?fp
                       (MAX(?pv) AS ?p) (MAX(?ov) AS ?o) (COUNT(*) AS ?rows)
                WHERE {
                    ?forecast a/rdfs:subClassOf* wx:ProbabilisticForecast ;
                              wx:producedByModel ?model ;
                              wx:leadTimeHours   ?leadHours ;
                              bfo:BFO_0000178    ?fp .

                    ?fp a/rdfs:subClassOf* fm:ForecastProbability ;
                        fm:assignsProbabilityTo ?proposition ;
                        fm:probabilityValue ?pv .

                    # Only the assessment resting on a record nothing supersedes.
                    ?assessment fm:assessesProposition ?proposition ;
                                fm:basedOnRecord ?record ;
                                fm:assessedTruthValue ?tv .
                    FILTER NOT EXISTS { ?newer wx:supersedes ?record }

                    BIND(IF(?tv = fm:True, 1, 0) AS ?ov)
                }
                GROUP BY ?model ?leadHours ?fp
            }

            BIND((?p - ?o) * (?p - ?o) AS ?sq)
            BIND(IF(?p > ?o, ?p - ?o, ?o - ?p) AS ?absErr)
        }
        GROUP BY ?model ?leadHours
    }
    BIND(ROUND(?baseRate * (1 - ?baseRate) * 1000) / 1000 AS ?climatologyBrier)
}
ORDER BY ?model ?leadHours
```

- [ ] **Step 7: Regenerate the expected results and read the diff**

Run: `poetry run python3 scripts/run_competency.py --update && git diff queries/`
Expected: the only change is a new `sourceRows` column equal to `n` in both files (`160`/`160`, `1`/`1`, and the per-bin counts in cq06a). **Any change to `n`, `meanBrier`, `baseRate` or `meanAbsError` means the rewrite altered the semantics — stop and fix rather than committing the new numbers.**

- [ ] **Step 8: Verify the whole suite**

Run: `make test`
Expected: `32/32 checks passed`, `7/7 competency questions answered as expected`, `consistent`, `PASS: ksh:WeatherMarket inferred...`.

- [ ] **Step 9: Commit**

```bash
git add scripts/validate.py scripts/test_validate.py queries/
git commit -m "Refuse two live assessments of one proposition, and collapse CQ6 before averaging"
```

---

### Task 3: Prove the synthetic dataset still matches its generator

**Why:** `examples/verification-synthetic.ttl` is 7234 generated lines that nothing compares against the generator. A hand-edit — or a generator change committed without regenerating — drifts silently. Same species as the dangling-IRI bug that motivated the definedness check.

**Files:**
- Modify: `scripts/generate_verification_data.py:49-50` (constants), `:229-232` (write and report)
- Modify: `Makefile` (`.PHONY` line, new target, `test` target)

**Interfaces:**
- Produces: `generate_verification_data.py --output PATH`, defaulting to `examples/verification-synthetic.ttl`; make target `verification-data-check`.

- [ ] **Step 1: Give the generator an output path**

In `scripts/generate_verification_data.py`, add `import argparse` at the top of the imports, and replace the write/report block at the end of `main()`:

```python
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=OUT,
        help="where to write the dataset; defaults to examples/verification-synthetic.ttl. "
             "A separate path is how `make verification-data-check` diffs the checked-in "
             "file against a fresh generation without touching the working tree.",
    )
    args = parser.parse_args()
```

Put those four statements at the *top* of `main()`, then change the tail from:

```python
    OUT.write_text("\n".join(out))
    n_assign = N_DAYS * len(BRACKETS) * len(MODELS) * len(LEADS)
    print(f"wrote {OUT.relative_to(ROOT)}")
```

to:

```python
    args.output.write_text("\n".join(out))
    n_assign = N_DAYS * len(BRACKETS) * len(MODELS) * len(LEADS)
    print(f"wrote {args.output}")
```

- [ ] **Step 2: Verify the default path is unchanged**

Run: `poetry run python3 scripts/generate_verification_data.py && git diff --stat examples/`
Expected: no diff. The generator is deterministic (fixed seed), so a diff here means Step 1 changed behaviour.

- [ ] **Step 3: Add the drift check to the Makefile**

Add `verification-data-check` to the `.PHONY` list, add the target after `verification-data`:

```make
## Fail if the checked-in synthetic dataset no longer matches its generator.
## The file is 7000 generated lines; nothing else would notice a hand-edit.
verification-data-check:
	@mkdir -p $(BUILD)
	@$(PY) scripts/generate_verification_data.py --output $(BUILD)/verification-synthetic.ttl >/dev/null
	@cmp -s examples/verification-synthetic.ttl $(BUILD)/verification-synthetic.ttl || { \
		echo "FAIL: examples/verification-synthetic.ttl does not match its generator."; \
		echo "      Run 'make verification-data' and review the diff."; \
		exit 1; }
	@echo "OK: synthetic dataset matches its generator"
```

and add it to `test`:

```make
test: validate validate-negative verification-data-check cq reason competency
```

- [ ] **Step 4: Prove the check fails when it should**

Run:

```bash
printf '\n# drift\n' >> examples/verification-synthetic.ttl && make verification-data-check; \
  git checkout examples/verification-synthetic.ttl
```

Expected: `FAIL: examples/verification-synthetic.ttl does not match its generator.` and a non-zero exit, then the file is restored.

- [ ] **Step 5: Verify**

Run: `make verification-data-check && make test`
Expected: `OK: synthetic dataset matches its generator`, then the full suite green.

- [ ] **Step 6: Commit**

```bash
git add scripts/generate_verification_data.py Makefile
git commit -m "Fail when the synthetic dataset drifts from its generator"
```

---

### Task 4: Negative tests for the two reasoner-only guards

**Why:** `core.ttl`'s `owl:AllDifferent` blocks and `alternativeDeterminationOf`'s irreflexivity exist to turn specific mistakes into HermiT inconsistencies. `test_validate.py` never invokes a reasoner, so both are asserted in prose only. Both were confirmed to fire by hand during the audit; this makes that repeatable.

**Files:**
- Create: `scripts/test_reason.py`
- Modify: `Makefile` (`.PHONY`, new `reason-negative` target, `test` target)

**Interfaces:**
- Consumes: the same ROBOT resolution order as the Makefile — `$ROBOT_JAR`, then `./robot.jar`, then `robot` on `PATH`.
- Produces: `make reason-negative`, which skips with a notice (exit 0) when ROBOT or Java is absent.

- [ ] **Step 1: Write the test script**

Create `scripts/test_reason.py`:

```python
#!/usr/bin/env python3
"""Negative tests for the axioms that only a reasoner enforces.

scripts/validate.py is deliberately Java-free, so the guards whose whole job is to
turn a mistake into a HermiT inconsistency have no coverage there: the
owl:AllDifferent blocks in core.ttl, and the irreflexivity of
wx:alternativeDeterminationOf. Each case here injects the mistake the guard exists
for and asserts ROBOT reports the ontology inconsistent.

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

# (name, path-to-mutate, find, replace)
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
        # wx:alternativeDeterminationOf is irreflexive so that a target asserted to
        # be an alternative determination of itself is an inconsistency rather than
        # a quietly meaningless assertion.
        "a target declared an alternative determination of itself",
        EXAMPLE,
        "    wx:alternativeDeterminationOf ex:Target-HighTemp .",
        "    wx:alternativeDeterminationOf ex:Target-HighTemp-NWS .",
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
    # mean nothing.
    proc = subprocess.run(
        [*robot, "merge", "--input", str(ROOT / "src" / "fmo.ttl"),
         "--input", str(ROOT / EXAMPLE),
         "--catalog", str(ROOT / "src" / "catalog-v001.xml"),
         "reason", "--reasoner", "HermiT", "--output", os.devnull],
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
```

- [ ] **Step 2: Run it**

Run: `poetry run python3 scripts/test_reason.py`
Expected: `3/3 reasoner guards fire` (baseline plus two cases). Takes about a minute — each case runs HermiT.

- [ ] **Step 3: Prove a case can fail**

Temporarily comment out the units `owl:AllDifferent` block in `src/core.ttl` (the one whose `owl:distinctMembers` list starts `unit:DEG_F unit:DEG_C unit:K`), rerun, then restore it.

Run: `poetry run python3 scripts/test_reason.py; git checkout src/core.ttl`
Expected: `FAIL [conventionalUnit made a sub-property of the functional hasUnit]: the reasoner accepted the ontology` — proving the test is measuring the guard and not something else.

- [ ] **Step 4: Wire it into the Makefile**

Add `reason-negative` to `.PHONY`, add the target after `validate-negative`:

```make
## Prove the reasoner-only guards fire: the axioms validate.py cannot check.
## Skips with a notice when ROBOT or Java is absent, like `make reason`.
reason-negative:
	$(PY) scripts/test_reason.py
```

and extend `test`:

```make
test: validate validate-negative verification-data-check cq reason reason-negative competency
```

- [ ] **Step 5: Verify**

Run: `make test`
Expected: full suite green including `3/3 reasoner guards fire`.

- [ ] **Step 6: Commit**

```bash
git add scripts/test_reason.py Makefile
git commit -m "Test the guards only the reasoner enforces"
```

---

### Task 5: Exercise the scoring layer, and make term coverage visible

**Why:** `fm:SkillScore`, `fm:BrierScore`, `fm:scoresAssignment`, `fm:usesScoringRule`, `fm:scoredAgainst`, `fm:scoreValue` and `wx:ForecastVerification` have no instance anywhere; CQ6a computes Brier inline in SPARQL and never touches them. `fm:scoredAgainst` exists specifically so a score stays interpretable after a correction — the one case the examples do model — and it has never been used. By the repo's own standard, these are terms nobody has watched work.

**Assumption, flag if wrong:** the scoring layer gets instantiated rather than deleted, because CQ6 is a stated competency question and the terms are its natural home. The trading layer (`ksh:BinaryContract`, `Order`, `OrderPlacement`, `Trade`, `Position`, `TraderRole`, `ContractHolderObligation`, `Payout`, `OrderBookSnapshot`) is left in place and *declared* unexercised rather than instantiated — no competency question asks about order flow. Deleting it instead is a defensible call and would be a 0.8.0 bump touching all four modules plus README.

**Files:**
- Modify: `examples/kxhighny-2026-08-15-correction.ttl` (append a section)
- Modify: `scripts/validate.py` (new `check_scores`; coverage note in `main()`)
- Modify: `README.md` (Validation section; Open questions)
- Test: `scripts/test_validate.py` (append to `CASES`)

**Interfaces:**
- Consumes: `ex:ForecastProb-82-83` (0.52) and `ex:Reassessment-82-83` (`fm:False`) from existing example files.
- Produces: `ex:Verification-82-83`, `ex:Score-82-83`; failure messages `"Brier score mismatch"` and `"score rests on a superseded record"`.

- [ ] **Step 1: Add the scoring instances**

Append to `examples/kxhighny-2026-08-15-correction.ttl`:

```turtle
################################################################
# Scoring the forecast, against the record that is now authoritative.
#
# The GEFS 06Z run gave the 82-83 bracket 0.52. The corrected record makes the
# proposition false, so the Brier score is (0.52 - 0)^2 = 0.2704. Scored against
# ex:Reassessment-82-83 and not the settlement-era assessment: the market paid
# out yes, and scoring the forecast against what the exchange did rather than
# what the record now says would measure the wrong thing.
#
# fm:scoredAgainst is what makes that choice inspectable after the fact. Without
# it the score is a number whose provenance is a matter of trust.
################################################################

ex:Verification-82-83 a wx:ForecastVerification ;
    rdfs:label "verification of the GEFS 06Z P(82-83F) against the corrected record" ;
    fm:hasInput ex:ForecastProb-82-83 , ex:Reassessment-82-83 ;
    fm:hasOutput ex:Score-82-83 .

ex:Score-82-83 a fm:SkillScore ;
    rdfs:label "Brier score for the GEFS 06Z P(82-83F)" ;
    fm:scoresAssignment ex:ForecastProb-82-83 ;
    fm:usesScoringRule fm:BrierScore ;
    fm:scoredAgainst ex:Reassessment-82-83 ;
    fm:scoreValue "0.2704"^^xsd:decimal ;
    fm:statedAs "(0.52 - 0)^2 = 0.2704. The proposition is false on the corrected record, though the market paid out yes." .
```

- [ ] **Step 2: Write the failing negative tests**

Append to `CASES` in `scripts/test_validate.py`:

```python
    (
        # A stored derived value with nothing checking it is the lead-time
        # problem again: it goes stale the moment either input moves.
        "Brier score no longer matches the probability and outcome it scores",
        CORRECTION,
        """    fm:scoreValue "0.2704"^^xsd:decimal ;""",
        """    fm:scoreValue "0.1024"^^xsd:decimal ;""",
        "Brier score mismatch",
    ),
    (
        # Scoring against the settlement-era assessment measures what the exchange
        # did, not what the record says. The whole point of fm:scoredAgainst.
        "score points at an assessment of a superseded record",
        CORRECTION,
        """    fm:scoredAgainst ex:Reassessment-82-83 ;""",
        """    fm:scoredAgainst ex:Assessment-82-83-at-settlement ;""",
        "score rests on a superseded record",
    ),
```

- [ ] **Step 3: Run them to verify they fail**

Run: `poetry run python3 scripts/test_validate.py`
Expected: both new cases report `validate.py passed but should have failed`.

- [ ] **Step 4: Implement the score check**

In `scripts/validate.py`, add the constants:

```python
SCORES_ASSIGNMENT = URIRef(WTL + "scoresAssignment")
USES_SCORING_RULE = URIRef(WTL + "usesScoringRule")
SCORED_AGAINST = URIRef(WTL + "scoredAgainst")
SCORE_VALUE = URIRef(WTL + "scoreValue")
BRIER_SCORE = URIRef(WTL + "BrierScore")
PROBABILITY_VALUE = URIRef(WTL + "probabilityValue")
ASSESSED_TRUTH_VALUE = URIRef(WTL + "assessedTruthValue")
TRUE_VALUE = URIRef(WTL + "True")
```

and the function, beside `check_current_assessments`:

```python
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
        outcome = 1.0 if truths[0] == TRUE_VALUE else 0.0
        expected = (float(probs[0]) - outcome) ** 2
        if abs(float(stated) - expected) > 1e-9:
            fail(
                f"Brier score mismatch: {score} says {stated} but probability "
                f"{probs[0]} against outcome {outcome:.0f} is {expected:.4f}"
            )
        checked += 1
    notes.append(f"{checked} Brier score(s) checked against their inputs")
```

Call it in `main()` after `check_current_assessments(ex)`:

```python
    check_scores(ex)
```

- [ ] **Step 5: Add the coverage note**

In `main()`, just before the `BFO branch distribution` note, add:

```python
    # Advisory, never a failure. A term with no instance is a term nobody has
    # watched work; the trading layer is deliberately in that state and README
    # says so, but the count should be visible on every run rather than needing
    # an audit to find.
    instantiated = {t for t in ex.objects(None, RDF.type) if is_ours(t)}
    uninstantiated = [c for c in our_classes if c not in instantiated]
    notes.append(
        f"{len(our_classes) - len(uninstantiated)}/{len(our_classes)} minted classes "
        f"have an instance in the examples"
    )
```

- [ ] **Step 6: Verify**

Run: `poetry run python3 scripts/validate.py && poetry run python3 scripts/test_validate.py`
Expected: validate prints `OK`, `1 Brier score(s) checked against their inputs`, and the coverage line; test_validate prints `34/34 checks passed`.

Note the coverage count only counts *directly asserted* types, so a class whose subclasses are instantiated still reports as uninstantiated. That is intended — it is a prompt to look, not a gate.

- [ ] **Step 7: Update the README**

In the Validation section, after the sentence ending "...and documentation coverage.", add:

```markdown
Stored derived values are checked against what they are derived from: `wx:leadTimeHours`
against issuance and interval start, and a `fm:SkillScore` under `fm:BrierScore` against
the probability it scores and the outcome it was scored against. A score resting on a
superseded record fails — scoring against a retracted value is the specific mistake
`fm:scoredAgainst` exists to make visible.
```

In Open questions, add:

```markdown
- **The trading layer is vocabulary, not exercised.** `ksh:BinaryContract`, `ksh:Order`,
  `ksh:Trade`, `ksh:Position`, `ksh:Payout` and `ksh:OrderBookSnapshot` have no instance in
  any example and no competency question asks about order flow, so nothing has ever watched
  them work. They are retained because the settlement story is incomplete without naming what
  settles, but treat them as unproven. `validate.py` reports the instantiated-class count on
  every run so the gap stays visible.
```

- [ ] **Step 8: Verify the whole suite**

Run: `make test`
Expected: green throughout; CQ results unchanged (no query reads scores).

- [ ] **Step 9: Commit**

```bash
git add examples/kxhighny-2026-08-15-correction.ttl scripts/validate.py scripts/test_validate.py README.md
git commit -m "Score the corrected forecast, and check the score against its inputs"
```

---

### Task 6: Grouping agreement and bracket overlap

**Why:** Two invariants of the same shape as check 6b, which exists because the examples aligned forecast and market by hand and nothing complained. A market's proposition may name a target its event grouping does not cover, and a mutually exclusive ladder may contain two brackets that overlap. Both are currently correct in the data and unguarded.

**Scope note:** overlap is checkable, exhaustiveness is not. LE81 / [82,83] / [84,85] / GE86 tiles the line only because the protocol rounds to whole degrees, which is stated in prose in `ex:TWCDailyTempProtocol` and nowhere in the model. Checking for gaps needs a reporting increment on the protocol — new modelling, deliberately not in this plan. Declare it instead.

**Files:**
- Modify: `scripts/validate.py` (new `check_grouping_coherence`)
- Modify: `README.md` (Open questions)
- Test: `scripts/test_validate.py` (append to `CASES`)

**Interfaces:**
- Consumes: `KSH`, `EXPRESSES` from Task 1; `HAS_SUBJECT` already present.
- Produces: failure messages `"market covers a different target than its grouping"` and `"overlapping brackets"`.

- [ ] **Step 1: Write the failing negative tests**

Append to `CASES` in `scripts/test_validate.py`:

```python
    (
        "a market expresses a proposition about a target its grouping does not cover",
        EXAMPLE,
        """    ksh:expressesProposition ex:Prop-82-83 ;
    ksh:hasStatus ksh:Finalized ;""",
        """    ksh:expressesProposition ex:Prop-82-83-NWS ;
    ksh:hasStatus ksh:Finalized ;""",
        "market covers a different target than its grouping",
    ),
    (
        "two brackets of one mutually exclusive ladder overlap",
        BRACKETS,
        """    fm:hasComparator fm:Between ;
    fm:floorValue "84"^^xsd:decimal ;""",
        """    fm:hasComparator fm:Between ;
    fm:floorValue "83"^^xsd:decimal ;""",
        "overlapping brackets",
    ),
```

The first case needs a proposition to point at. Also append to `examples/kxhighny-2026-08-15.ttl`, at the end of section 7b (after `ex:Datum-Max-NWS`):

```turtle
# The same bracket read against the authority the exchange did NOT settle on.
# Nothing points at it; it exists so the grouping-agreement check has a target to
# catch a market drifting onto, the way Target-HighTemp-NWS does for forecasts.
ex:Prop-82-83-NWS a fm:Proposition ;
    rdfs:label "high is between 82 and 83 degrees F, NWS determination" ;
    fm:hasSubject ex:Target-HighTemp-NWS ;
    fm:hasComparator fm:Between ;
    fm:floorValue "82"^^xsd:decimal ;
    fm:capValue "83"^^xsd:decimal ;
    fm:hasUnit unit:DEG_F .
```

- [ ] **Step 2: Run them to verify they fail**

Run: `poetry run python3 scripts/test_validate.py`
Expected: both new cases report `validate.py passed but should have failed`.

- [ ] **Step 3: Implement the checks**

In `scripts/validate.py`, add the constants:

```python
IN_EVENT_GROUPING = URIRef(KSH + "inEventGrouping")
COVERS_TARGET = URIRef(KSH + "coversTarget")
MUTUALLY_EXCLUSIVE = URIRef(KSH + "mutuallyExclusive")
HAS_COMPARATOR = URIRef(WTL + "hasComparator")
FLOOR_VALUE = URIRef(WTL + "floorValue")
CAP_VALUE = URIRef(WTL + "capValue")
```

and the function:

```python
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
    comparators = {
        URIRef(WTL + "Between"):            lambda f, c: (f, True, c, True),
        URIRef(WTL + "LessThanOrEqual"):    lambda f, c: (-inf, False, c, True),
        URIRef(WTL + "LessThan"):           lambda f, c: (-inf, False, c, False),
        URIRef(WTL + "GreaterThanOrEqual"): lambda f, c: (f, True, inf, False),
        URIRef(WTL + "GreaterThan"):        lambda f, c: (f, False, inf, False),
        URIRef(WTL + "EqualTo"):            lambda f, c: (f, True, f, True),
    }

    def interval(prop):
        """None means not evaluable -- fm:Custom, or a threshold not stated."""
        comps = list(g.objects(prop, HAS_COMPARATOR))
        if len(comps) != 1 or comps[0] not in comparators:
            return None
        floors = list(g.objects(prop, FLOOR_VALUE))
        caps = list(g.objects(prop, CAP_VALUE))
        if len(floors) > 1 or len(caps) > 1:
            fail(f"{prop}: more than one threshold value, so its interval is ambiguous")
            return None
        try:
            return comparators[comps[0]](
                float(floors[0]) if floors else None,
                float(caps[0]) if caps else None,
            )
        except TypeError:
            fail(f"{prop}: its comparator needs a threshold value that is not stated")
            return None

    def overlaps(a, b):
        lo1, lo1_in, hi1, hi1_in = a
        lo2, lo2_in, hi2, hi2_in = b
        left = lo1 < hi2 or (lo1 == hi2 and lo1_in and hi2_in)
        right = lo2 < hi1 or (lo2 == hi1 and lo2_in and hi1_in)
        return left and right

    checked = 0
    groupings: dict[URIRef, list] = {}
    for market, grouping in g.subject_objects(IN_EVENT_GROUPING):
        for prop in g.objects(market, EXPRESSES):
            for subject in g.objects(prop, HAS_SUBJECT):
                checked += 1
                covered = list(g.objects(grouping, COVERS_TARGET))
                if covered and subject not in covered:
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

    if EXAMPLES and not checked:
        fail(
            "no market reaches a proposition subject, so the grouping check "
            "matched nothing; the inEventGrouping or expressesProposition chain "
            "is broken"
        )
    notes.append(f"{checked} market/grouping pair(s) checked for target agreement")
```

Call it in `main()` after `check_scores(ex)`:

```python
    check_grouping_coherence(ex)
```

`Literal` is already imported at the top of `validate.py`.

- [ ] **Step 4: Verify**

Run: `poetry run python3 scripts/validate.py && poetry run python3 scripts/test_validate.py`
Expected: validate prints `OK` plus `4 market/grouping pair(s) checked for target agreement`; test_validate prints `36/36 checks passed`.

- [ ] **Step 5: Declare what is still unchecked**

Add to Open questions in `README.md`:

```markdown
- **Bracket exhaustiveness is unchecked.** The validator refuses overlapping brackets in a
  grouping asserted mutually exclusive, but cannot tell whether they leave a gap: the
  KXHIGHNY ladder tiles the line only because the protocol reports whole degrees, which is
  stated in the protocol's prose and nowhere in the model. Checking for gaps needs a
  reporting increment on `wx:MeasurementProtocol`. Until then a ladder with a hole in it
  passes, and CQ5 reports the undershoot as a possible arbitrage.
```

- [ ] **Step 6: Verify the whole suite**

Run: `make test`
Expected: everything green. CQ results are unchanged — `ex:Prop-82-83-NWS` is expressed by no market and forecast by nothing, so no query picks it up.

- [ ] **Step 7: Commit**

```bash
git add scripts/validate.py scripts/test_validate.py examples/kxhighny-2026-08-15.ttl README.md
git commit -m "Check a market against its grouping's target, and refuse overlapping brackets"
```

---

## After the plan

Optional, one line each, not tasks:

- Add `robot validate-profile --profile DL` to `make reason`. The ontology is DL-conformant today (checked during the audit); one command keeps a punning slip from going unnoticed.
- If the trading layer is deleted rather than declared, that is a 0.8.0 bump: `owl:versionIRI` and `owl:versionInfo` in all four modules plus the README status line, per CLAUDE.md.
