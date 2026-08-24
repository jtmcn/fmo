#!/usr/bin/env python3
"""Validate a data file against FMO's SHACL shapes.

Separate from validate.py, which checks the ontology's own integrity and takes
no data. This one answers a different question: does THIS export conform?

Usage:
    python3 scripts/validate_shapes.py <data.ttl> [...] [--shapes <file>]
    python3 scripts/validate_shapes.py --examples          # the examples union
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

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
MODULES = [
    "imports/bfo-core.ttl", "imports/qudt-subset.ttl",
    "core.ttl", "weather.ttl", "kalshi.ttl", "fmo.ttl",
]
DEFAULT_SHAPES = ROOT / "shapes" / "thermaledge-export.ttl"


def main(argv: list[str]) -> int:
    shapes_path = DEFAULT_SHAPES
    if "--shapes" in argv:
        i = argv.index("--shapes")
        shapes_path = Path(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]

    if "--examples" in argv:
        data_paths = sorted((ROOT / "examples").glob("*.ttl"))
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
