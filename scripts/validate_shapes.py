#!/usr/bin/env python3
"""Validate a data file against FMO's SHACL shapes.

Separate from validate.py, which checks the ontology's own integrity and takes
no data. This one answers a different question: does THIS export conform?

Usage:
    python3 scripts/validate_shapes.py <data.ttl> [--shapes shapes/thermaledge-export.ttl]
Exit:
    0 conforms, 1 violations found, 2 could not run.
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
    if not argv:
        print("usage: validate_shapes.py <data.ttl> [--shapes <file>]", file=sys.stderr)
        return 2
    data_path = Path(argv[0])
    shapes_path = DEFAULT_SHAPES
    if "--shapes" in argv:
        shapes_path = Path(argv[argv.index("--shapes") + 1])
    for path in (data_path, shapes_path):
        if not path.exists():
            print(f"missing {path}", file=sys.stderr)
            return 2

    # Modules are loaded alongside the data so sh:class constraints can see the
    # class hierarchy; rdfs inferencing gives subclass reasoning, which SPARQL
    # and SHACL both lack by default (the same trap CQ2 hit).
    data = Graph()
    for rel in MODULES:
        data.parse(SRC / rel, format="turtle")
    data.parse(data_path, format="turtle")

    conforms, _results_graph, report = validate(
        data,
        shacl_graph=Graph().parse(shapes_path, format="turtle"),
        inference="rdfs",
        advanced=True,
    )
    if conforms:
        print(f"✅ {data_path.name} conforms to {shapes_path.name}")
        return 0
    print(report)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
