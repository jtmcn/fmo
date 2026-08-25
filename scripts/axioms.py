#!/usr/bin/env python3
"""Enumerate the ontology's axiom sites, and remove one on request.

An axiom that nothing would miss is the ontology's version of prose that no check
enforces: it reads as a guarantee and holds nothing. Two of those shipped in one
afternoon -- a disjointness block whose deletion left every test green, and a union
axiom whose test named a mistake it does not catch -- so the enumeration exists to
make the set of axioms something a check can iterate rather than something a reader
is trusted to remember.

A site is keyed by module and shape, never by blank node id: `kalshi.ttl:
ksh:Market subClassOf [exactly 1 ksh:expressesProposition]`. Blank nodes get new ids
on every parse, so a key built from them would churn on reserialization and the
ledger would be noise. The key is also the diagnostic -- it says where to look.

remove_site() deletes a site's triples, blank-node closure included, so a caller can
ask what breaks without that axiom. That is how a guard proves it is pinned to the
axiom it claims: delete the axiom, and the guard must stop firing.
"""

from __future__ import annotations

from rdflib import BNode, Graph, RDF, RDFS, OWL, URIRef
from rdflib.term import Node

from registry import MODULES, SRC

# The modules whose axioms this repo mints, derived from MODULES rather than typed
# again. Excluded: imports/ -- bfo-core.ttl is vendored unmodified and qudt-subset.ttl
# is generated, so neither is ours to pin and requiring a reason for each of BFO's
# 54 axioms would be noise that teaches readers to skim the ledger. fmo.ttl is an
# import shell with no axioms of its own.
MINTED = [m for m in MODULES if "/" not in m and m != "fmo.ttl"]

PREFIXES = {
    "https://w3id.org/forecast-market-ontology/core#": "fm",
    "https://w3id.org/forecast-market-ontology/weather#": "wx",
    "https://w3id.org/forecast-market-ontology/kalshi#": "ksh",
    "http://qudt.org/schema/qudt/": "qudt",
    "http://qudt.org/vocab/unit/": "unit",
    "http://qudt.org/vocab/quantitykind/": "quantitykind",
    "http://purl.obolibrary.org/obo/": "bfo",
}

# (label, predicate) for the restriction filler, in the order a key reports them.
FILLERS = (
    ("exactly", OWL.cardinality),
    ("min", OWL.minCardinality),
    ("max", OWL.maxCardinality),
    ("exactly", OWL.qualifiedCardinality),
    ("max", OWL.maxQualifiedCardinality),
    ("min", OWL.minQualifiedCardinality),
    ("some", OWL.someValuesFrom),
    ("only", OWL.allValuesFrom),
    ("value", OWL.hasValue),
)

CHARACTERISTICS = (
    ("Functional", OWL.FunctionalProperty),
    ("InverseFunctional", OWL.InverseFunctionalProperty),
    ("Transitive", OWL.TransitiveProperty),
    ("Symmetric", OWL.SymmetricProperty),
    ("Asymmetric", OWL.AsymmetricProperty),
    ("Reflexive", OWL.ReflexiveProperty),
    ("Irreflexive", OWL.IrreflexiveProperty),
)


def curie(g: Graph, node: Node) -> str:
    """A readable name for a node, or a shape sketch for a blank one."""
    if isinstance(node, BNode):
        if (node, OWL.unionOf, None) in g:
            return "or(" + ", ".join(curie(g, m) for m in members(g, node, OWL.unionOf)) + ")"
        if (node, OWL.intersectionOf, None) in g:
            return "and(" + ", ".join(
                curie(g, m) for m in members(g, node, OWL.intersectionOf)) + ")"
        if (node, RDF.type, OWL.Restriction) in g:
            return f"[{restriction(g, node)}]"
        if (node, OWL.onDatatype, None) in g:
            return f"{curie(g, next(g.objects(node, OWL.onDatatype)))}[faceted]"
        return "_:"
    text = str(node)
    for iri, prefix in PREFIXES.items():
        if text.startswith(iri):
            return f"{prefix}:{text[len(iri):]}"
    return text.rsplit("/", 1)[-1].rsplit("#", 1)[-1]


def members(g: Graph, node: Node, predicate: URIRef) -> list[Node]:
    listing = next(g.objects(node, predicate), None)
    return list(g.items(listing)) if listing is not None else []


def restriction(g: Graph, node: Node) -> str:
    prop = curie(g, next(g.objects(node, OWL.onProperty), None))
    for label, predicate in FILLERS:
        filler = next(g.objects(node, predicate), None)
        if filler is not None:
            shown = str(filler) if label in ("exactly", "min", "max") else curie(g, filler)
            on_class = next(g.objects(node, OWL.onClass), None)
            qualifier = f" {curie(g, on_class)}" if on_class is not None else ""
            return f"{label} {shown} {prop}{qualifier}"
    return f"unrecognised {prop}"


def closure(g: Graph, node: Node, seen: set | None = None) -> set:
    """Every triple reachable from a blank node, so a site deletes cleanly.

    Restrictions, union lists and AllDisjointClasses members are all blank-node
    structures; removing the anchoring triple alone would strand the rest as
    orphaned triples that still parse and still say nothing.
    """
    seen = set() if seen is None else seen
    found: set = set()
    if not isinstance(node, BNode) or node in seen:
        return found
    seen.add(node)
    for pred, obj in g.predicate_objects(node):
        found.add((node, pred, obj))
        found |= closure(g, obj, seen)
    return found


def sites(module: str, g: Graph) -> dict[str, set]:
    """Every axiom site in one module: key -> the triples that constitute it."""
    found: dict[str, set] = {}

    def record(key: str, triples: set) -> None:
        # Two structurally identical axioms in one module would collide. Number
        # them rather than silently keeping one, or the ledger undercounts.
        unique, n = key, 2
        while unique in found:
            unique, n = f"{key} #{n}", n + 1
        found[unique] = triples

    for subject, obj in g.subject_objects(RDFS.subClassOf):
        if isinstance(obj, BNode):
            record(f"{module}: {curie(g, subject)} subClassOf {curie(g, obj)}",
                   {(subject, RDFS.subClassOf, obj)} | closure(g, obj))

    for predicate, label in ((OWL.disjointWith, "disjointWith"),
                             (OWL.equivalentClass, "equivalentClass"),
                             (OWL.propertyDisjointWith, "propertyDisjointWith")):
        for subject, obj in g.subject_objects(predicate):
            record(f"{module}: {curie(g, subject)} {label} {curie(g, obj)}",
                   {(subject, predicate, obj)} | closure(g, obj))

    for label, kind, predicate in (("AllDifferent", OWL.AllDifferent, OWL.distinctMembers),
                                   ("AllDisjointClasses", OWL.AllDisjointClasses, OWL.members)):
        for node in g.subjects(RDF.type, kind):
            listed = ", ".join(curie(g, m) for m in members(g, node, predicate))
            record(f"{module}: {label}({listed})", closure(g, node))

    for label, kind in CHARACTERISTICS:
        for subject in g.subjects(RDF.type, kind):
            record(f"{module}: {curie(g, subject)} a {label}Property",
                   {(subject, RDF.type, kind)})

    return found


def all_sites() -> dict[str, set]:
    """Every axiom site in the minted modules, keyed uniquely."""
    if not MINTED:
        raise RuntimeError(
            "no minted modules derived from MODULES, so the ledger would cover nothing"
        )
    found: dict[str, set] = {}
    for rel in MINTED:
        g = Graph()
        g.parse(SRC / rel, format="turtle")
        found.update(sites(rel, g))
    return found


def remove_site(key: str, source: str) -> str:
    """Return `source` Turtle with one axiom site deleted.

    Text in, text out: the caller writes it back over the module so that ROBOT
    reasons over a tree missing exactly this axiom and nothing else.
    """
    g = Graph()
    g.parse(data=source, format="turtle")
    module = key.split(":", 1)[0]
    found = sites(module, g)
    if key not in found:
        raise KeyError(key)
    for triple in found[key]:
        g.remove(triple)
    return g.serialize(format="turtle")


if __name__ == "__main__":
    found = all_sites()
    print(f"{len(found)} axiom sites")
    for key in sorted(found):
        print(f"  {key}")
