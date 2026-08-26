#!/usr/bin/env python3
"""Tests about the checks themselves, rather than about the ontology.

A check with nothing to check must not pass. Those guards were written by hand,
one per traversal, until one was missed -- which is what a hand-maintained rule
earns over time. Calling every check with a graph that empties its traversal
enforces the rule for all of them, including checks nobody has written yet.

Which graph empties a traversal depends on what the check reads: data-dependent
checks get the schema with no example data, schema-reading checks get an empty
graph, and a check that re-reads the example files off disk gets an example file
with no triples. Getting this wrong reads as a pass, so the sets are named in
code -- and the schema-reading claim is then run rather than trusted.

The assertion is on coverage_log, not on failures: "the check failed somehow" is
satisfied by any unrelated guard inside it, so a check could lose its coverage()
call entirely and this file would stay green.

Run: python3 scripts/test_meta.py
"""

from __future__ import annotations

import inspect
import sys
import tempfile
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

# Reads the example files off disk rather than the graph it is handed, so no graph
# empties its traversal. EXAMPLES is the lever instead -- pointed at a file with no
# triples, not emptied, since coverage() disarms its own guard when there are no
# example files at all and that would read as a pass for the check being swept.
EXAMPLE_READING = {
    "check_declared_properties": "re-parses the example files itself, not the graph handed to it",
}

# Its population is the prose files: no graph empties it, and EXAMPLES is not a lever
# either, because its guards pass always=True. Exempting by name, in code, beats
# exempting by judgement at review time.
NOT_SWEEPABLE = {
    "check_context_terms": "reads PROSE_FILES, not the example graph",
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
    # An example file that exists and holds nothing. Held for the process: the
    # TemporaryDirectory cleans itself up at exit.
    tmp = tempfile.TemporaryDirectory()
    empty_example = Path(tmp.name) / "empty.ttl"
    empty_example.write_text("", encoding="utf-8")

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
        example_reading = name in EXAMPLE_READING
        g = Graph() if schema_reading else schema
        given = ("an empty graph and no example files" if schema_reading else
                 "an example file with no triples" if example_reading else
                 "a graph with no example data")
        # Checks take one graph or two (schema, examples); pass the same one for
        # each parameter, so a two-argument check is tested rather than TypeError-ing
        # and reading as a coverage failure.
        arity = len(inspect.signature(fn).parameters)
        saved_examples = V.EXAMPLES
        if example_reading:
            V.EXAMPLES = [empty_example]
        elif schema_reading:
            # Swept with no example files at all, which is what always=True is for:
            # a schema population cannot be emptied by removing examples, so a guard
            # that goes dark with EXAMPLES empty depends on something it never reads.
            V.EXAMPLES = []
        try:
            fn(*[g] * arity)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{name} raised {type(exc).__name__}: {exc} on {given}")
            continue
        finally:
            V.EXAMPLES = saved_examples

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

    # The classification is run, not trusted. A data-dependent check filed under
    # SCHEMA_READING gets an empty graph, empties trivially and passes the sweep
    # vacuously -- which is also the obvious way to silence a real failure. The
    # claim is that the schema is its population, so on the schema with no example
    # data every one of its traversals must still count something.
    for name in sorted(set(SCHEMA_READING) & set(names)):
        fn = getattr(V, name)
        V.failures.clear()
        V.notes.clear()
        V.coverage_log.clear()
        try:
            fn(*[schema] * len(inspect.signature(fn).parameters))
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{name} raised {type(exc).__name__}: {exc} on the schema")
            continue
        empty = [n for n, count in V.coverage_log if count == 0]
        if empty:
            failures.append(
                f"{name} is filed under SCHEMA_READING but {empty} empties on a graph with "
                f"no example data, so it is data-dependent and the sweep hands it the "
                f"empty graph its guard needs to be tested with"
            )
    print(f"  ok   [SCHEMA_READING] {len(SCHEMA_READING)} check(s) still count "
          f"with no example data")

    # A stale or misspelled key is inert rather than dangerous -- the misfiling that
    # would matter is caught above -- but it means a check nobody classified is being
    # swept as data-dependent by default.
    for label, names_set in (("SCHEMA_READING", SCHEMA_READING),
                             ("EXAMPLE_READING", EXAMPLE_READING),
                             ("NOT_SWEEPABLE", NOT_SWEEPABLE)):
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
