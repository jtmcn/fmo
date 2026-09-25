#!/usr/bin/env python3
"""Negative tests for scripts/lineage.py: each defect it claims to catch, caught.

Each case mutates a copy of the current modules (or the scanned texts) and asserts
audit() reports the expected finding. The guards are tested too: an audit with no
released terms or no files to scan must raise, not report a clean pass.

Run: python3 scripts/test_lineage.py
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS, SKOS, XSD

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lineage  # noqa: E402

KSH = "https://w3id.org/forecast-market-ontology/kalshi#"
PAYOUT = URIRef(KSH + "Payout")
EXPIRATION = URIRef(KSH + "expirationTime")
KALSHI_ONTO = URIRef(lineage.BASE + "kalshi")


def copy(g: Graph) -> Graph:
    out = Graph()
    out += g
    return out


def drop_subject(term: URIRef) -> Callable[[Graph], object]:
    def mutate(g: Graph) -> None:
        g.remove((term, None, None))
    return mutate


def retire(term: URIRef) -> Callable[[Graph], object]:
    def mutate(g: Graph) -> None:
        g.remove((term, None, None))
        g.add((term, OWL.deprecated, Literal(True)))
    return mutate


def main() -> int:
    head = lineage.modules_at(None)
    prior_version = "0.17.0"
    prior = copy(head)
    for onto in (URIRef(lineage.BASE + m.removesuffix(".ttl")) for m in lineage.OURS):
        head.set((onto, OWL.priorVersion, URIRef(f"{onto}/{prior_version}")))
    texts = lineage.scanned_texts()

    baseline = lineage.audit(prior, head, prior_version, texts)
    if baseline:
        print("BASELINE FAIL: the unmutated audit reports findings", *baseline, sep="\n  ")
        return 1
    print("  ok   [baseline: the current modules audit clean against themselves]")

    # (name, mutation of head, mutation of texts, expected substring)
    cases: list[tuple[str, Callable[[Graph], object], Callable[[dict[str, str]], object], str]] = [
        ("a module header with no owl:priorVersion",
         lambda g: g.remove((KALSHI_ONTO, OWL.priorVersion, None)), lambda t: None,
         "kalshi owl:priorVersion is absent, expected"),
        ("an owl:priorVersion naming the wrong version",
         lambda g: g.set((KALSHI_ONTO, OWL.priorVersion, URIRef(f"{KALSHI_ONTO}/0.9.0"))),
         lambda t: None, "kalshi owl:priorVersion is ['"),
        ("a released term deleted without a tombstone",
         drop_subject(PAYOUT), lambda t: None,
         "ksh:Payout was released in 0.17.0 and is gone without a tombstone"),
        ("a tombstone that keeps its declaration",
         lambda g: g.add((EXPIRATION, RDF.type, OWL.DatatypeProperty)), lambda t: None,
         "ksh:expirationTime is a tombstone but keeps rdf:type"),
        ("a tombstone that keeps its range",
         lambda g: g.add((EXPIRATION, RDFS.range, XSD.dateTimeStamp)), lambda t: None,
         "ksh:expirationTime is a tombstone but keeps rdfs:range"),
        ("a tombstone with no history note",
         lambda g: g.remove((EXPIRATION, SKOS.historyNote, None)), lambda t: None,
         "ksh:expirationTime is a tombstone without a skos:historyNote"),
        ("a tombstone with no label",
         lambda g: g.remove((EXPIRATION, RDFS.label, None)), lambda t: None,
         "ksh:expirationTime is a tombstone without its rdfs:label"),
        ("a replacement that is not declared",
         lambda g: g.add((EXPIRATION, DCTERMS.isReplacedBy, URIRef(KSH + "noSuchTime"))),
         lambda t: None, f"ksh:expirationTime is replaced by {KSH}noSuchTime, which is not declared"),
        ("a released term retired properly still passes continuity, but its use in a query fails",
         retire(PAYOUT),
         lambda t: None, "uses retired term ksh:Payout"),
        ("a retired term named by full IRI in a shape",
         lambda g: None,
         lambda t: t.__setitem__("shapes/x.ttl", f"sh:path <{EXPIRATION}> ."),
         "shapes/x.ttl uses retired term ksh:expirationTime"),
    ]

    failed = 0
    for name, mutate_graph, mutate_texts, expect in cases:
        g, t = copy(head), dict(texts)
        mutate_graph(g)
        mutate_texts(t)
        found = lineage.audit(prior, g, prior_version, t)
        if any(expect in f for f in found):
            print(f"  ok   [{name}]")
        else:
            failed += 1
            print(f"  FAIL [{name}]: expected {expect!r}, got {found}")

    # A prefix of a retired CURIE is a different term, and must not match.
    t = dict(texts)
    t["queries/y.rq"] = "?m ksh:expirationTimeZone ?z ."
    if any("queries/y.rq" in f for f in lineage.audit(prior, copy(head), prior_version, t)):
        failed += 1
        print("  FAIL [a longer name that starts with a retired one]: matched")
    else:
        print("  ok   [a longer name that starts with a retired one is not a use]")

    for name, args, expect in (
        ("an audit with no released terms", (Graph(), head, prior_version, texts), "no term declared"),
        ("an audit with no files to scan", (prior, head, prior_version, {}), "no example, shape or query"),
    ):
        try:
            lineage.audit(*args)
        except lineage.LineageError as exc:
            if expect in str(exc):
                print(f"  ok   [{name} raises rather than passing]")
                continue
            print(f"  FAIL [{name}]: raised {exc}")
        else:
            print(f"  FAIL [{name}]: returned instead of raising")
        failed += 1

    if failed:
        print(f"\n{failed} lineage negative test(s) failed")
        return 1
    print("\nall lineage negative tests pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
