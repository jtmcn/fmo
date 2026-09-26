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
from collections.abc import Callable
from pathlib import Path

from rdflib import Graph, Literal, RDF, RDFS, OWL, URIRef
from rdflib.term import Node
from rdflib.namespace import SKOS

sys.path.insert(0, str(Path(__file__).resolve().parent))

import axioms  # noqa: E402
from registry import ONTOLOGY_PREFIXES, OUR_NS, SRC  # noqa: E402

CF_CELL_METHODS = URIRef(ONTOLOGY_PREFIXES["wx"] + "cfCellMethods")

DECLARED_AS = (OWL.Class, OWL.ObjectProperty, OWL.DatatypeProperty, OWL.NamedIndividual,
               RDFS.Datatype)


def digest(text: str) -> str:
    """Sixteen hex chars, matching what ThermalEdge's pin file already stores."""
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def minted_graph() -> Graph:
    g = Graph()
    for rel in axioms.MINTED:
        g.parse(SRC / rel, format="turtle")
    return g


def signatures(g: Graph | None = None) -> dict[str, dict]:
    g = minted_graph() if g is None else g
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
            # An API code is what ingest looks the term up by, so remapping one moves
            # the semantics a consumer relies on even though no axiom changed.
            notations = sorted(
                f"{n}^^{axioms.curie(g, n.datatype)}" if isinstance(n, Literal) and n.datatype
                else str(n)
                for n in g.objects(subject, SKOS.notation)
            )
            # Likewise the CF name forecast ingest resolves a variable by, and the
            # statistic that says which aggregate of it the term is.
            matches = sorted(str(m) for m in g.objects(subject, SKOS.closeMatch))
            methods = sorted(str(m) for m in g.objects(subject, CF_CELL_METHODS))
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
                *(f"notation: {n}" for n in notations),
                *(f"match: {m}" for m in matches),
                *(f"cell methods: {m}" for m in methods),
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


def _remap_mutant(sigs: dict[str, dict], predicate: URIRef, what: str,
                  remap: Callable[[Node], Node],
                  keep: Callable[[Graph, Node], bool] = lambda g, s: True,
                  moves: bool = True) -> str | None:
    """Remap the first `predicate` value; exactly that term's semantics_sha256 must move,
    or with `moves=False`, no digest may.

    Returns a failure message, or None. A digest that ignored the lookup key would
    pass the reproducibility check and still let a remapped key reach a consumer
    with every pin matching.
    """
    g = minted_graph()
    keyed = sorted((s, o) for s, o in g.subject_objects(predicate)
                   if isinstance(s, URIRef) and str(s).startswith(OUR_NS) and keep(g, s))
    if not keyed:
        return f"no term carries a {what}, so the {what} mutant tested nothing"
    subject, value = keyed[0]
    g.remove((subject, predicate, value))
    g.add((subject, predicate, remap(value)))
    mutated = signatures(g)
    moved = sorted(k for k in sigs if sigs[k]["semantics_sha256"] != mutated[k]["semantics_sha256"])
    prose = sorted(k for k in sigs if sigs[k]["definition_sha256"] != mutated[k]["definition_sha256"])
    expected = axioms.curie(g, subject)
    if moved != ([expected] if moves else []) or prose:
        return (f"remapping {expected}'s {what} moved semantics_sha256 for {moved} "
                f"and definition_sha256 for {prose}; expected "
                + (f"only {expected}'s semantics" if moves else "no digest to move"))
    return None


def notation_mutant(sigs: dict[str, dict]) -> str | None:
    """Remap one API code."""
    return _remap_mutant(sigs, SKOS.notation, "skos:notation",
                         lambda n: Literal(f"{n}-remapped", datatype=getattr(n, "datatype", None)))


def field_name_mutant(sigs: dict[str, dict]) -> str | None:
    """Remap one API field name. The first notation overall is a designation's code, so
    without this nothing proved a property's field name reaches its digest (FM-0015)."""
    return _remap_mutant(sigs, SKOS.notation, "field name",
                         lambda n: Literal(f"{n}-remapped", datatype=getattr(n, "datatype", None)),
                         lambda g, s: any((s, RDF.type, t) in g
                                          for t in (OWL.ObjectProperty, OWL.DatatypeProperty)))


def scope_note_mutant(sigs: dict[str, dict]) -> str | None:
    """Reword one scope note; that term's semantics must move (FM-0017)."""
    return _remap_mutant(sigs, SKOS.scopeNote, "scope note",
                         lambda n: Literal(f"{n} Reworded."))


def editorial_note_mutant(sigs: dict[str, dict]) -> str | None:
    """Reword one editorial note; no digest may move. Repo pointers live there so that
    renaming a check does not tell a consumer a term's meaning changed (FM-0017)."""
    return _remap_mutant(sigs, SKOS.editorialNote, "editorial note",
                         lambda n: Literal(f"{n} Reworded."), moves=False)


def cf_name_mutant(sigs: dict[str, dict]) -> str | None:
    """Remap one CF standard name."""
    return _remap_mutant(sigs, SKOS.closeMatch, "CF mapping",
                         lambda o: URIRef(f"{str(o).rstrip('/')}_remapped/"))


def cell_methods_mutant(sigs: dict[str, dict]) -> str | None:
    """Change one CF statistic."""
    return _remap_mutant(sigs, CF_CELL_METHODS, "cell methods",
                         lambda m: Literal(f"{m}_remapped"))


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
        for mutant in (notation_mutant, field_name_mutant, scope_note_mutant,
                       editorial_note_mutant, cf_name_mutant, cell_methods_mutant):
            moved = mutant(sigs)
            if moved is not None:
                print(f"FAIL: {moved}", file=sys.stderr)
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
