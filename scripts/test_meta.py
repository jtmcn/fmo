#!/usr/bin/env python3
"""Tests about the checks themselves, rather than about the ontology.

A check with nothing to check must not pass. Those guards were written by hand,
one per traversal, until one was missed -- which is what a hand-maintained rule
earns over time. Calling every check with an empty graph enforces the rule for
all of them, including checks nobody has written yet.

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


# The one check that reads no graph. It walks PROSE_FILES and compares what they
# name against the schema, so "nothing to check" is not a state it can be in.
# Exempting it by name, in code, beats exempting it by judgement at review time.
NOT_DATA_DEPENDENT = {
    "check_context_terms": "reads PROSE_FILES, not the example graph",
}


def check_names() -> list[str]:
    return sorted(n for n in dir(V) if n.startswith("check_"))


def main() -> int:
    failures: list[str] = []
    names = check_names()
    if not names:
        print("FAIL: found no check_* functions in validate.py")
        return 1

    g = schema_only()
    for name in names:
        fn = getattr(V, name)
        V.failures.clear()
        V.notes.clear()
        V.coverage_log.clear()
        if name in NOT_DATA_DEPENDENT:
            print(f"  --   [{name}] exempt: {NOT_DATA_DEPENDENT[name]}")
            continue
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
        empty = [n for n, count in V.coverage_log if count == 0]
        if not empty:
            failures.append(
                f"{name} counted a non-zero traversal on a graph with no example "
                f"data, so its coverage() calls are not counting example data"
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
