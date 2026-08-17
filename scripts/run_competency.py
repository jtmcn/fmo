#!/usr/bin/env python3
"""Run the competency questions in queries/ and compare against checked-in results.

A competency question is a requirement, so it needs a pass/fail, not a printout.
Each queries/cqNN-*.rq is executed against the modules plus the example data and
its result compared to the matching .expected file.

Two rules that keep this honest:

  * An empty result set FAILS. A query that matches nothing is the most common way
    for a broken competency check to look like a passing one.
  * Expected files are compared exactly, after canonicalising IRIs to prefixed
    names and sorting rows. Changing an answer means changing the checked-in
    expectation, visibly, in a diff.

Usage:
    python3 scripts/run_competency.py            # check
    python3 scripts/run_competency.py --update   # regenerate .expected files
"""

from __future__ import annotations

import sys
from pathlib import Path

from rdflib import Graph, Literal, URIRef

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
QUERIES = ROOT / "queries"

MODULES = [
    "imports/bfo-core.ttl", "imports/qudt-subset.ttl",
    "core.ttl", "weather.ttl", "kalshi.ttl", "wantology.ttl",
]

PREFIXES = {
    "https://w3id.org/wantology/core#": "wtl:",
    "https://w3id.org/wantology/weather#": "wx:",
    "https://w3id.org/wantology/kalshi#": "ksh:",
    "https://w3id.org/wantology/examples/kxhighny-2026-08-15#": "ex:",
    "https://w3id.org/wantology/examples/verification#": "vex:",
    "http://purl.obolibrary.org/obo/": "bfo:",
    "http://qudt.org/vocab/unit/": "unit:",
    "http://qudt.org/vocab/quantitykind/": "quantitykind:",
    "http://qudt.org/schema/qudt/": "qudt:",
}


def shorten(term) -> str:
    """Canonical, diff-friendly rendering of one binding."""
    if term is None:
        return "-"
    if isinstance(term, URIRef):
        s = str(term)
        for full, short in PREFIXES.items():
            if s.startswith(full):
                return short + s[len(full):]
        return f"<{s}>"
    if isinstance(term, Literal):
        # Drop the datatype for readability but keep the lexical form exactly,
        # so 0.60 and 0.6 do not silently compare equal.
        return str(term)
    return str(term)


def load_graph() -> Graph:
    g = Graph()
    for rel in MODULES:
        g.parse(SRC / rel, format="turtle")
    examples = sorted((ROOT / "examples").glob("*.ttl"))
    if not examples:
        print("no example files found; competency questions need instance data", file=sys.stderr)
        raise SystemExit(1)
    for path in examples:
        g.parse(path, format="turtle")
    return g


def render(results) -> str:
    """Serialize a SPARQL result as sorted TSV with a header row."""
    cols = [str(v) for v in results.vars]
    rows = ["\t".join(cols)]
    body = ["\t".join(shorten(row[v]) for v in results.vars) for row in results]
    rows.extend(sorted(body))
    return "\n".join(rows) + "\n"


def main() -> int:
    update = "--update" in sys.argv
    prefixes = (QUERIES / "prefixes.txt").read_text()
    graph = load_graph()

    query_files = sorted(QUERIES.glob("cq*.rq"))
    if not query_files:
        print("no queries found in queries/", file=sys.stderr)
        return 1

    failures = 0
    for qf in query_files:
        expected_file = qf.with_suffix(".expected")
        try:
            results = graph.query(prefixes + "\n" + qf.read_text())
        except Exception as exc:  # noqa: BLE001
            print(f"  FAIL [{qf.name}]: query error: {exc}")
            failures += 1
            continue

        actual = render(results)
        row_count = len(actual.strip().splitlines()) - 1

        # An empty result is a failure, not a pass. This is the trap that makes
        # unverified competency claims look fine.
        if row_count == 0:
            print(f"  FAIL [{qf.name}]: returned 0 rows; the question is not answerable")
            failures += 1
            continue

        if update:
            expected_file.write_text(actual)
            print(f"  updated [{qf.name}]: {row_count} row(s)")
            continue

        if not expected_file.exists():
            print(f"  FAIL [{qf.name}]: no {expected_file.name}; run with --update and review it")
            failures += 1
            continue

        expected = expected_file.read_text()
        if actual != expected:
            print(f"  FAIL [{qf.name}]: result differs from {expected_file.name}")
            for line in _diff(expected, actual):
                print(f"         {line}")
            failures += 1
        else:
            print(f"  ok   [{qf.name}]: {row_count} row(s)")

    if update:
        print("\nexpected files regenerated -- review the diff before committing")
        return 0

    total = len(query_files)
    print(f"\n{total - failures}/{total} competency questions answered as expected")
    return 1 if failures else 0


def _diff(expected: str, actual: str) -> list[str]:
    import difflib
    return list(difflib.unified_diff(
        expected.splitlines(), actual.splitlines(),
        fromfile="expected", tofile="actual", lineterm="", n=1,
    ))[:20]


if __name__ == "__main__":
    raise SystemExit(main())
