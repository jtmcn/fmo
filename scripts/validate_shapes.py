#!/usr/bin/env python3
"""Validate a data file against FMO's SHACL shapes.

Separate from validate.py, which checks the ontology's own integrity and takes
no data. This one answers a different question: does THIS export conform?

Usage:
    python3 scripts/validate_shapes.py <data.ttl> [...] [--shapes <file>]
    python3 scripts/validate_shapes.py --examples          # the examples union
    python3 scripts/validate_shapes.py --exports           # each export fixture,
                                                           # separately
Exit:
    0 conforms, 1 violations found, 2 could not run.

Several data files are loaded as ONE graph, which is what --examples does and
what `make shapes` runs. The example files import each other -- the correction
and bracketset files reference a target and propositions the base file defines
-- so validating one alone reports absences that are not real: a target with no
protocol, a proposition whose subject has no type. validate.py checks the union
for the same reason.
"""

from __future__ import annotations

import sys
from pathlib import Path

from pyshacl import validate
from rdflib import Graph

sys.path.insert(0, str(Path(__file__).resolve().parent))
from registry import MODULES, SRC, SHAPES, examples, exports  # noqa: E402


def main(argv: list[str]) -> int:
    shapes_path = SHAPES
    if "--shapes" in argv:
        i = argv.index("--shapes")
        if i + 1 >= len(argv):
            print("--shapes needs a file", file=sys.stderr)
            return 2
        shapes_path = Path(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]

    if "--exports" in argv:
        rest = [a for a in argv if a != "--exports"]
        if rest:
            print(f"--exports takes no other files; got {' '.join(rest)}", file=sys.stderr)
            return 2
        paths = exports()
        if not paths:
            print("--exports matched no files", file=sys.stderr)
            return 2
        worst = 0
        for path in paths:
            worst = max(worst, main([str(path), "--shapes", str(shapes_path)]))
        return worst

    if "--examples" in argv:
        rest = [a for a in argv if a != "--examples"]
        if rest:
            # Silently dropping them printed "6 file(s) conform" while the file the
            # caller named was never loaded -- a pass report for an unread file.
            print(f"--examples takes no other files; got {' '.join(rest)}", file=sys.stderr)
            return 2
        data_paths = examples()
        if not data_paths:
            print("--examples matched no files", file=sys.stderr)
            return 2
    else:
        data_paths = [Path(a) for a in argv]
    if not data_paths:
        print("usage: validate_shapes.py <data.ttl> [...] | --examples", file=sys.stderr)
        return 2
    for path in (*data_paths, shapes_path):
        if not path.exists():
            print(f"missing {path}", file=sys.stderr)
            return 2

    # Modules are loaded alongside the data so sh:class constraints can see the
    # class hierarchy; rdfs inferencing gives subclass reasoning, which SPARQL
    # and SHACL both lack by default (the same trap CQ2 hit).
    data = Graph()
    for rel in MODULES:
        data.parse(SRC / rel, format="turtle")
    for path in data_paths:
        data.parse(path, format="turtle")

    conforms, _results_graph, report = validate(
        data,
        shacl_graph=Graph().parse(shapes_path, format="turtle"),
        inference="rdfs",
        advanced=True,
    )
    if conforms:
        names = ", ".join(p.name for p in data_paths)
        print(f"OK: {len(data_paths)} file(s) conform to {shapes_path.name} ({names})")
        return 0
    print(report)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
