#!/usr/bin/env python3
"""Tests about the checks themselves, rather than about the ontology.

A check with nothing to check must not pass. Those guards were written by hand,
one per traversal, until one was missed -- which is what a hand-maintained rule
earns over time. Calling every check with a graph that empties its traversal
enforces the rule for all of them, including checks nobody has written yet.

Which graph empties a traversal depends on what the check reads: data-dependent
checks get the schema with no example data, schema-reading checks get an empty
graph. Getting this wrong reads as a pass, so the two sets are named in code.

The assertion is on coverage_log, not on failures: "the check failed somehow" is
satisfied by any unrelated guard inside it, so a check could lose its coverage()
call entirely and this file would stay green.

Run: python3 scripts/test_meta.py
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

from rdflib import Graph

sys.path.insert(0, str(Path(__file__).resolve().parent))

import validate as V  # noqa: E402
from registry import MODULES, ROOT, SRC  # noqa: E402


def schema_only() -> Graph:
    """The modules with no example data: every check should traverse nothing."""
    g = Graph()
    for rel in MODULES:
        g.parse(SRC / rel, format="turtle")
    return g


# Checks whose traversal empties when the EXAMPLE DATA goes away are swept against
# the schema. Checks that read the modules never empty that way -- their population
# is the schema itself -- so sweeping them needs a graph with nothing in it at all.
# Skipping them instead, as this file once did, exempts them from the one rule the
# sweep exists to enforce.
SCHEMA_READING = {
    "check_bfo_grounding": "its population is the minted classes, which example data cannot empty",
    "check_bridged_grounding": "its population is the bridged QUDT classes",
    "check_branch_disjointness": "its population is the minted classes",
    "check_documentation": "its population is the minted terms",
    "check_defined_terms": "schema IRIs are in scope too, so example data cannot empty it",
    "check_designation_disjointness": "its population is the subclasses of fm:Designation",
}

# Checks that read files off disk rather than the graph they are handed. No graph
# empties their traversal, and coverage() deliberately disables its own guard when
# EXAMPLES is empty, so there is no lever here. Exempting by name, in code, beats
# exempting by judgement at review time.
NOT_SWEEPABLE = {
    "check_context_terms": "reads PROSE_FILES, not the example graph",
    "check_declared_properties": "re-parses the example files itself, not the graph handed to it",
}


def coverage_guard_direction() -> list[str]:
    """coverage(always=True) must still fail on zero when no example file exists.

    The sweep cannot prove this: it runs with EXAMPLES populated, where
    `always or EXAMPLES` is true whichever flag is passed. Both directions are
    asserted, because a fix that dropped the gate entirely would satisfy the
    first assertion and silently make every data-dependent check fail on a tree
    with no examples.
    """
    out: list[str] = []
    saved = V.EXAMPLES
    try:
        V.EXAMPLES = []
        for always, want_failure, why in (
            (True, True, "a schema population cannot be emptied by removing examples"),
            (False, False, "a traversal over examples that do not exist is legitimately empty"),
        ):
            V.failures.clear()
            V.notes.clear()
            V.coverage_log.clear()
            V.coverage("probe", 0, "thing(s) checked", "probe", always=always)
            if bool(V.failures) is not want_failure:
                out.append(
                    f"coverage(always={always}) {'did not fail' if want_failure else 'failed'} "
                    f"on a zero count with no example files -- {why}"
                )
    finally:
        V.EXAMPLES = saved
        V.failures.clear()
        V.notes.clear()
        V.coverage_log.clear()
    return out


def check_names() -> list[str]:
    return sorted(n for n in dir(V) if n.startswith("check_"))


def main() -> int:
    failures: list[str] = []
    names = check_names()
    if not names:
        print("FAIL: found no check_* functions in validate.py")
        return 1

    schema = schema_only()
    for name in names:
        fn = getattr(V, name)
        V.failures.clear()
        V.notes.clear()
        V.coverage_log.clear()
        if name in NOT_SWEEPABLE:
            print(f"  --   [{name}] exempt: {NOT_SWEEPABLE[name]}")
            continue
        # A schema-reading check needs an empty graph; anything else is swept against
        # the schema, where only the example data has gone away.
        schema_reading = name in SCHEMA_READING
        g = Graph() if schema_reading else schema
        given = "an empty graph" if schema_reading else "a graph with no example data"
        # Checks take one graph or two (schema, examples); pass the same one for
        # each parameter, so a two-argument check is tested rather than TypeError-ing
        # and reading as a coverage failure.
        arity = len(inspect.signature(fn).parameters)
        try:
            fn(*[g] * arity)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{name} raised {type(exc).__name__}: {exc} on an empty graph")
            continue

        # Every traversal must be counted, and every empty one must have failed.
        # Checking V.failures instead would accept any unrelated guard firing --
        # which is how check_dimensions and check_payouts passed this sweep while
        # their coverage() calls could have been deleted.
        if not V.coverage_log:
            failures.append(
                f"{name} records no coverage(), so nothing proves it looked at anything"
            )
            continue
        # Every count, not merely one of them: "some traversal emptied" is the
        # aggregate-counter hazard wearing a sweep. A check with four traversals
        # would pass on one zero while the other three went unproven.
        empty = [n for n, count in V.coverage_log if count == 0]
        counted = [f"{n}={c}" for n, c in V.coverage_log if c != 0]
        if counted:
            failures.append(
                f"{name} counted a non-zero traversal on {given} ({', '.join(counted)}), "
                f"so those coverage() calls are not counting what the check traverses"
            )
            continue
        unguarded = [n for n in empty if not any(
            f.startswith(f"{n}: nothing to check") for f in V.failures)]
        if unguarded:
            failures.append(
                f"{name} traversed nothing in {unguarded} without failing, so it "
                f"proves nothing when that traversal is empty"
            )
        else:
            print(f"  ok   [{name}] fails with nothing to check ({len(empty)} traversal(s))")

    failures.extend(coverage_guard_direction())

    # A stale or misspelled key is inert, and the dangerous direction is the one
    # the docstring names: a data-dependent check filed under SCHEMA_READING gets
    # an empty graph, empties trivially, and passes vacuously.
    for label, names_set in (("SCHEMA_READING", SCHEMA_READING), ("NOT_SWEEPABLE", NOT_SWEEPABLE)):
        for stale in sorted(set(names_set) - set(names)):
            failures.append(f"{label} names {stale}, which is not a check in validate.py")

    # A smoke alarm, not a proof: a mention is not a test, and check_lead_times
    # was mentioned here while its zero-coverage hole went unnoticed for a
    # release. It catches only a check nobody wrote anything about at all.
    suite = (ROOT / "scripts" / "test_validate.py").read_text(encoding="utf-8")
    for name in names:
        if name not in suite:
            failures.append(f"{name} is named nowhere in test_validate.py")

    print(f"\n{len(names)} check(s) examined")
    if failures:
        print(f"\nFAILED ({len(failures)}):", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
