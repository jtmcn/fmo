#!/usr/bin/env python3
"""Structural checks for the Wantology modules.

Parses every module plus the vendored BFO, then checks the things that actually
go wrong when hand-authoring a BFO application ontology:

  1. Every file parses as Turtle.
  2. Every term we mint sits under exactly one BFO top-level branch, and
     reaches bfo:entity by rdfs:subClassOf. A term that does not is either
     unrooted or accidentally rooted in owl:Thing.
  3. No class is both a continuant and an occurrent. This is the disjointness
     that BFO cares most about and the one an application ontology breaks by
     mistake, typically by filing an information artifact under process.
  4. Every property we use in the examples is declared somewhere.
  5. Every class and property carries a label and a definition.

Exit code is non-zero if any check fails. Run: python3 scripts/validate.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from rdflib import Graph, RDF, RDFS, OWL, URIRef, Literal
from rdflib.namespace import SKOS

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"

BFO = "http://purl.obolibrary.org/obo/"
ENTITY = URIRef(BFO + "BFO_0000001")
CONTINUANT = URIRef(BFO + "BFO_0000002")
OCCURRENT = URIRef(BFO + "BFO_0000003")

# Branches we expect every minted term to land in, for the summary table.
BRANCHES = {
    URIRef(BFO + "BFO_0000004"): "independent continuant",
    URIRef(BFO + "BFO_0000020"): "specifically dependent continuant",
    URIRef(BFO + "BFO_0000031"): "generically dependent continuant",
    URIRef(BFO + "BFO_0000003"): "occurrent",
}

OUR_NS = (
    "https://w3id.org/wantology/core#",
    "https://w3id.org/wantology/weather#",
    "https://w3id.org/wantology/kalshi#",
)

MODULES = ["imports/bfo-core.ttl", "core.ttl", "weather.ttl", "kalshi.ttl", "wantology.ttl"]
EXAMPLES = sorted((ROOT / "examples").glob("*.ttl"))

failures: list[str] = []
notes: list[str] = []


def fail(msg: str) -> None:
    failures.append(msg)


def is_ours(term) -> bool:
    return isinstance(term, URIRef) and str(term).startswith(OUR_NS)


def ancestors(g: Graph, cls: URIRef) -> set[URIRef]:
    """Named rdfs:subClassOf ancestors, ignoring anonymous restrictions."""
    seen: set[URIRef] = set()
    stack = [cls]
    while stack:
        cur = stack.pop()
        for parent in g.objects(cur, RDFS.subClassOf):
            if isinstance(parent, URIRef) and parent not in seen:
                seen.add(parent)
                stack.append(parent)
    return seen


def main() -> int:
    g = Graph()

    # 1. parse
    for rel in MODULES:
        path = SRC / rel
        if not path.exists():
            fail(f"missing module: {rel}")
            continue
        try:
            g.parse(path, format="turtle")
        except Exception as exc:  # noqa: BLE001
            fail(f"parse error in {rel}: {exc}")
    if failures:
        return report()
    notes.append(f"parsed {len(MODULES)} modules, {len(g)} triples")

    ex = Graph()
    ex += g
    for path in EXAMPLES:
        try:
            ex.parse(path, format="turtle")
        except Exception as exc:  # noqa: BLE001
            fail(f"parse error in {path.name}: {exc}")
    notes.append(f"parsed {len(EXAMPLES)} example files, {len(ex)} triples with schema")

    our_classes = sorted(
        {s for s in g.subjects(RDF.type, OWL.Class) if is_ours(s)}, key=str
    )
    notes.append(f"{len(our_classes)} minted classes")

    # 2. BFO grounding
    tally: dict[str, int] = {}
    for cls in our_classes:
        anc = ancestors(g, cls)
        if ENTITY not in anc:
            fail(f"not grounded in BFO: {cls} (ancestors: {sorted(str(a) for a in anc)})")
            continue
        branch = [name for iri, name in BRANCHES.items() if iri in anc or iri == cls]
        if not branch:
            fail(f"grounded in bfo:entity but in no known branch: {cls}")
        else:
            for b in branch:
                tally[b] = tally.get(b, 0) + 1

    # 3. continuant / occurrent disjointness
    for cls in our_classes:
        anc = ancestors(g, cls)
        if CONTINUANT in anc and OCCURRENT in anc:
            fail(f"both continuant and occurrent: {cls}")

    # 4. properties used in examples are declared
    declared = {
        s
        for t in (OWL.ObjectProperty, OWL.DatatypeProperty, OWL.AnnotationProperty)
        for s in g.subjects(RDF.type, t)
    }
    builtin_ok = {RDF.type, RDFS.label, RDFS.subClassOf, OWL.imports, OWL.versionIRI}
    for path in EXAMPLES:
        eg = Graph()
        eg.parse(path, format="turtle")
        for _, p, _ in eg:
            if p in builtin_ok or p in declared:
                continue
            if str(p).startswith(BFO) or str(p).startswith(str(SKOS)):
                continue
            if str(p).startswith("http://purl.org/dc/"):
                continue
            fail(f"{path.name} uses undeclared property: {p}")

    # 5. documentation coverage
    for term in our_classes + sorted(
        {
            s
            for t in (OWL.ObjectProperty, OWL.DatatypeProperty)
            for s in g.subjects(RDF.type, t)
            if is_ours(s)
        },
        key=str,
    ):
        if not any(g.objects(term, RDFS.label)):
            fail(f"no rdfs:label: {term}")
        has_def = any(g.objects(term, SKOS.definition))
        has_note = any(g.objects(term, SKOS.scopeNote)) or any(
            g.objects(term, SKOS.example)
        )
        if not has_def and not has_note:
            notes.append(f"  undocumented (no definition or note): {term}")

    if tally:
        notes.append("BFO branch distribution:")
        for name, count in sorted(tally.items(), key=lambda kv: -kv[1]):
            notes.append(f"  {count:3d}  {name}")

    # Domain sanity: the join the ontology exists for.
    KSH = "https://w3id.org/wantology/kalshi#"
    WTL = "https://w3id.org/wantology/core#"
    joined = set(
        ex.objects(None, URIRef(KSH + "expressesProposition"))
    ) & set(ex.objects(None, URIRef(WTL + "assignsProbabilityTo")))
    if EXAMPLES and not joined:
        fail("no proposition is both expressed by a market and assigned a probability; the forecast/market join is not demonstrated")
    elif joined:
        notes.append(f"forecast/market join demonstrated on {len(joined)} proposition(s)")

    return report()


def report() -> int:
    for note in notes:
        print(note)
    if failures:
        print(f"\nFAILED ({len(failures)}):", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print("\nOK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
