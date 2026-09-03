#!/usr/bin/env python3
"""CQ3's verdict: did the reasoner re-derive the type the fixture had weakened?

Lifted out of the `competency` recipe, where it was six backslash-continued lines
of Python inside a Makefile. Two reasons, and the second is the sharper one:

  1. The recipe now resolves its reasoner in one shell so it can stop quietly when
     there is none, and nesting a continued Python string inside a continued shell
     block is a quoting accident waiting to happen.
  2. `make typecheck` runs ty over scripts/*.py. Python embedded in the Makefile
     was the one piece of Python in this repo that no checker ever read.

Skips for the same reason the recipe does, and asks the same module: without a
reasoner there is no reasoned file, and a verdict on a file that was never written
is not a pass. Absence is a skip; a named reasoner that does not run is a failure.

Run: python3 scripts/check_inferred_type.py <reasoned.ttl> <iri> <expected-local-name>
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rdflib import Graph, RDF, URIRef  # noqa: E402

import reasoner  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(f"usage: {Path(__file__).name} <reasoned.ttl> <iri> <expected-local-name>",
              file=sys.stderr)
        return 2
    path, iri, expected = argv

    try:
        command, why = reasoner.robot_command()
    except reasoner.ReasonerBroken as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    if command is None:
        print(f"SKIP competency: {why}", file=sys.stderr)
        return 0

    # A reasoner exists, so the file should. Its absence is a broken recipe, not a
    # machine without Java, and the two must not print the same thing.
    if not Path(path).exists():
        print(f"FAIL: {path} was not written, so nothing was re-derived to check",
              file=sys.stderr)
        return 1

    g = Graph()
    g.parse(path)
    types = [str(t) for t in g.objects(URIRef(iri), RDF.type)]
    if not any(expected in t for t in types):
        print(f"FAIL: {expected} not inferred for {iri}; got {types}", file=sys.stderr)
        return 1
    print(f"PASS: {expected} inferred from the proposition-subject chain")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
