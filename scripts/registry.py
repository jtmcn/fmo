#!/usr/bin/env python3
"""One definition of every path, glob and namespace the checkers share.

Written after rex: was added to validate.py's prefix map and not to
run_competency.py's, which holds the same namespaces inverted. Two maps over one
set of facts drift; one source with derived views cannot.

Data only. Nothing here imports a checker, so every checker can import this.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
QUERIES = ROOT / "queries"
SHAPES = ROOT / "shapes" / "thermaledge-export.ttl"

MODULES = [
    "imports/bfo-core.ttl", "imports/qudt-subset.ttl",
    "core.ttl", "weather.ttl", "kalshi.ttl", "fmo.ttl",
]

ONTOLOGY_PREFIXES = {
    "fm": "https://w3id.org/forecast-market-ontology/core#",
    "wx": "https://w3id.org/forecast-market-ontology/weather#",
    "ksh": "https://w3id.org/forecast-market-ontology/kalshi#",
}

EXAMPLE_PREFIXES = {
    "ex": "https://w3id.org/forecast-market-ontology/examples/kxhighny-2026-08-15#",
    "tex": "https://w3id.org/forecast-market-ontology/examples/kxhighny-2026-08-15-trading#",
    "vex": "https://w3id.org/forecast-market-ontology/examples/verification#",
    "rex": "https://w3id.org/forecast-market-ontology/examples/kxrainnyc-2026-07-15#",
}

EXTERNAL_PREFIXES = {
    "bfo": "http://purl.obolibrary.org/obo/",
    "unit": "http://qudt.org/vocab/unit/",
    "quantitykind": "http://qudt.org/vocab/quantitykind/",
    "qudt": "http://qudt.org/schema/qudt/",
}

OUR_NS = tuple(ONTOLOGY_PREFIXES.values())
CONTEXT_PREFIXES = {**ONTOLOGY_PREFIXES, **EXAMPLE_PREFIXES}

# The inverse view run_competency.py renders with. Derived, never typed twice.
IRI_TO_PREFIX = {
    iri: f"{name}:"
    for name, iri in {
        **ONTOLOGY_PREFIXES, **EXAMPLE_PREFIXES, **EXTERNAL_PREFIXES,
    }.items()
}

# Prose that describes the CURRENT graph. Excluded: docs/superpowers/** (a plan
# names terms that do not exist yet) and docs/fmo-in-thermaledge.md (pinned to
# FMO 0.7.0). Checking either against today's graph fails on correct content.
PROSE_FILES = [
    ROOT / "CONTEXT.md",
    ROOT / "README.md",
    ROOT / "docs" / "design-notes.md",
    # ADRs accumulate load-bearing claims and were unchecked prose. This brings
    # their term, path and target references under the same checks; the behavioural
    # claims an ADR makes still answer to nothing but review.
    *sorted((ROOT / "docs" / "adr").glob("*.md")),
]


# Globs as functions, not module-level lists: the negative-test harness copies the
# tree and runs the checkers there, so these must resolve against the copy at call
# time rather than snapshot the source tree at import.
def examples() -> list[Path]:
    """Worked data. Loaded together -- the files cross-reference."""
    return sorted((ROOT / "examples").glob("*.ttl"))


def exports() -> list[Path]:
    """Conformant export fixtures. Each is an independent graph; never merged."""
    return sorted((ROOT / "examples" / "export").glob("*.ttl"))


def negatives() -> list[Path]:
    """Fixtures that must be rejected. A negative fixture nothing rejects is not one."""
    return sorted((ROOT / "examples" / "negative").glob("*.ttl"))
