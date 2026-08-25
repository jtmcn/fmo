#!/usr/bin/env python3
"""A semantic signature per minted term, for downstream consumers to pin against.

ThermalEdge borrows FMO's terms and pins them in docs/fmo-term-pins.json by the
sha256 of `skos:definition`. That catches a reworded definition. It does not catch
a changed axiom, because the definition text does not move when the axioms do --
verified by deleting both cardinality restrictions from ksh:Market, leaving its
definition untouched, and watching `make validate-fmo-pins` report all 27 terms
matching. The restriction that README.md cites as the reason SHACL is needed can
be removed without the consumer relying on it noticing.

A pin over prose is the same failure as prose over a check: it reports a guarantee
it is not holding. So this emits a digest over what a term actually MEANS -- its
label, its definition, its scope notes, and every axiom that mentions it -- which
moves whenever any of those move.

Two digests per term, not one, because they answer different questions:

  definition_sha256  the prose moved; a reader's understanding may be stale
  semantics_sha256   the axioms moved; a consumer's inferences may be wrong

A consumer wanting the current behaviour keeps pinning the first. One that needs to
know when the ontology's commitments change pins the second.

    poetry run python3 scripts/term_signatures.py                # all minted terms
    poetry run python3 scripts/term_signatures.py fm:Proposition ksh:Market
    poetry run python3 scripts/term_signatures.py --check        # deterministic?
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from rdflib import Graph, RDF, RDFS, OWL, URIRef
from rdflib.namespace import SKOS

sys.path.insert(0, str(Path(__file__).resolve().parent))

import axioms  # noqa: E402
from registry import ONTOLOGY_PREFIXES, SRC  # noqa: E402

DECLARED_AS = (OWL.Class, OWL.ObjectProperty, OWL.DatatypeProperty, OWL.NamedIndividual)


def digest(text: str) -> str:
    """Sixteen hex chars, matching what ThermalEdge's pin file already stores."""
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def minted_graph() -> Graph:
    g = Graph()
    for rel in axioms.MINTED:
        g.parse(SRC / rel, format="turtle")
    return g


def signatures() -> dict[str, dict]:
    g = minted_graph()
    sites = axioms.all_sites()

    # Axioms are attributed by the curie the key opens with, which is the subject
    # of the axiom. A term's signature therefore moves when an axiom ABOUT it moves,
    # not when an unrelated axiom happens to mention it in a filler -- that would
    # couple every term to every other and make each digest churn on any edit.
    by_subject: dict[str, list[str]] = {}
    for key in sites:
        body = key.split(": ", 1)[1] if ": " in key else key
        subject = body.split(" ", 1)[0]
        by_subject.setdefault(subject, []).append(body)

    out: dict[str, dict] = {}
    for prefix, namespace in ONTOLOGY_PREFIXES.items():
        for subject in set(g.subjects(RDF.type, None)):
            if not isinstance(subject, URIRef) or not str(subject).startswith(namespace):
                continue
            if not any((subject, RDF.type, kind) in g for kind in DECLARED_AS):
                continue
            curie = f"{prefix}:{str(subject)[len(namespace):]}"
            label = str(next(g.objects(subject, RDFS.label), ""))
            definition = str(next(g.objects(subject, SKOS.definition), ""))
            notes = sorted(str(n) for n in g.objects(subject, SKOS.scopeNote))
            parents = sorted(
                axioms.curie(g, p) for p in g.objects(subject, RDFS.subClassOf)
                if isinstance(p, URIRef)
            )
            axiom_lines = sorted(by_subject.get(curie, []))

            # The rendering is the contract: sorted, newline-joined, no blank nodes.
            # Anything unstable here -- a bnode id, a set iteration order -- would make
            # the digest churn on reserialisation and train readers to ignore it.
            semantic = "\n".join([
                f"label: {label}",
                f"definition: {definition}",
                *(f"note: {n}" for n in notes),
                *(f"parent: {p}" for p in parents),
                *(f"axiom: {a}" for a in axiom_lines),
            ])
            out[curie] = {
                "label": label,
                "definition_sha256": digest(definition),
                "semantics_sha256": digest(semantic),
                "axioms": len(axiom_lines),
            }
    return dict(sorted(out.items()))


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    sigs = signatures()

    if "--check" in sys.argv:
        # A signature that is not reproducible is not a pin. Recomputing from a
        # second parse catches an unstable rendering -- set iteration, a blank node
        # id -- which would otherwise surface downstream as phantom drift.
        again = signatures()
        drift = sorted(k for k in sigs if sigs[k] != again.get(k))
        if drift or len(sigs) != len(again):
            print(f"FAIL: signatures are not reproducible: {drift[:5]}", file=sys.stderr)
            return 1
        if not sigs:
            print("FAIL: no terms signed, so this check verified nothing", file=sys.stderr)
            return 1
        with_axioms = sum(1 for v in sigs.values() if v["axioms"])
        print(f"OK: {len(sigs)} term signatures reproducible, {with_axioms} carry axioms")
        return 0

    if args:
        missing = [a for a in args if a not in sigs]
        if missing:
            print(f"FAIL: no such minted term: {', '.join(missing)}", file=sys.stderr)
            return 1
        sigs = {k: sigs[k] for k in args}

    print(json.dumps(sigs, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
