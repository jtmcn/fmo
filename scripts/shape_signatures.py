#!/usr/bin/env python3
"""A structured signature per export shape, for downstream consumers to pin.

shapes/thermaledge-export.ttl IS the definition of a valid ThermalEdge export,
and nothing pinned it. A shape that gets STRICTER already fails ThermalEdge's
nightly run, loudly, with a SHACL report naming the constraint. A shape that gets
WEAKER, or is deleted, passes in silence -- and a weaker contract passing is
indistinguishable from a strong one passing.

A file digest would catch both, and would also fire on a reformat, a comment and
a tightening. The benign cases are the common ones, so the reader learns to
re-pin without looking, and the alarm is muted. So this publishes facts per
shape: the target class, and per path the constraints that bear on strength.

sh:message is deliberately excluded. Rewording a message is not a change in
strength, and including it would make the digest churn on prose.

    poetry run python3 scripts/shape_signatures.py            # emit facts
    poetry run python3 scripts/shape_signatures.py --check     # reproducible?
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from rdflib import BNode, Graph, Namespace, RDF

sys.path.insert(0, str(Path(__file__).resolve().parent))

from registry import ONTOLOGY_PREFIXES, SHAPES  # noqa: E402

SH = Namespace("http://www.w3.org/ns/shacl#")

PREFIXES = {
    **{v: k for k, v in ONTOLOGY_PREFIXES.items()},
    "http://www.w3.org/ns/shacl#": "sh",
    "http://www.w3.org/2001/XMLSchema#": "xsd",
    "https://w3id.org/forecast-market-ontology/shapes/thermaledge#": "teh",
}

# The constraints that bear on how strong a shape is. sh:message is absent by
# design; so is sh:name and any other annotation.
SCALAR_CONSTRAINTS = {
    "minCount": SH.minCount,
    "maxCount": SH.maxCount,
    "class": SH["class"],
    "datatype": SH.datatype,
    "nodeKind": SH.nodeKind,
    "pattern": SH.pattern,
    "minInclusive": SH.minInclusive,
    "maxInclusive": SH.maxInclusive,
}

# Everything above, plus the shape-level and bookkeeping predicates, is what this
# signer understands. Anything else in the shapes file is refused rather than
# ignored -- the rule FMO already applies to its own diagram, where a shape using
# a targeting construct the reader cannot handle fails diagram-check instead of
# quietly shrinking the profile. sh:deactivated was missed by the first draft of
# this design precisely because an unmodelled predicate cost nothing to ignore.
UNDERSTOOD = {
    SH.targetClass, SH.deactivated, SH.property, SH.path, SH.message, SH.name,
    SH.description, SH.severity, SH["in"], RDF.type,
    *SCALAR_CONSTRAINTS.values(),
}


def digest(text: str) -> str:
    """Sixteen hex chars, matching term_signatures.py and ThermalEdge's pins."""
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def curie(node) -> str:
    text = str(node)
    for iri, prefix in PREFIXES.items():
        if text.startswith(iri):
            return f"{prefix}:{text[len(iri):]}"
    return text


def shapes_graph(path: Path = SHAPES) -> Graph:
    g = Graph()
    g.parse(path, format="turtle")
    return g


def _constraints(g: Graph, prop: BNode) -> dict:
    out: dict = {}
    for name, predicate in SCALAR_CONSTRAINTS.items():
        value = next(g.objects(prop, predicate), None)
        if value is None:
            continue
        out[name] = int(value) if name in ("minCount", "maxCount") else curie(value)
    listed = next(g.objects(prop, SH["in"]), None)
    if listed is not None:
        out["in"] = sorted(curie(v) for v in g.items(listed))
    # Recorded explicitly rather than left absent: sh:Violation is the SHACL
    # default, and comparing an absent value against an explicit one would read a
    # default as a removal -- reporting a weakening that did not happen.
    severity = next(g.objects(prop, SH.severity), None)
    out["severity"] = curie(severity) if severity is not None else "sh:Violation"
    return out


def _refuse_unmodelled(g: Graph) -> None:
    """Fail on any SHACL predicate this signer does not reason about.

    A predicate it ignores is a hole in the contract that signs identically to a
    contract without one. sh:deactivated is the proof: one triple turns a shape
    off completely -- an export missing its protocol goes from a violation to
    conformant -- and a signer that reads only targetClass and property reports
    no change at all.
    """
    unmodelled = sorted(
        curie(p) for p in set(g.predicates())
        if str(p).startswith(str(SH)) and p not in UNDERSTOOD
    )
    if unmodelled:
        raise SystemExit(
            f"FAIL: {SHAPES.name} uses SHACL constructs this signer does not model: "
            f"{', '.join(unmodelled)}\n"
            f"      Teach shape_signatures.py to classify them, or the contract can "
            f"change in a way the pin cannot see."
        )


def facts(path: Path = SHAPES) -> dict[str, dict]:
    """Signatures for a shapes file; defaults to the one FMO ships.

    The path is a parameter so the mutants can run the real parser over mutated
    Turtle. Mutating the parsed dicts instead would take both sides of a
    comparison from one facts() call, leaving the signer/classifier seam untested
    and letting a bug in facts() cancel itself out.
    """
    g = shapes_graph(path)
    _refuse_unmodelled(g)
    out: dict[str, dict] = {}
    for shape in g.subjects(RDF.type, SH.NodeShape):
        target = next(g.objects(shape, SH.targetClass), None)
        paths: dict[str, dict] = {}
        for prop in g.objects(shape, SH.property):
            path = next(g.objects(prop, SH.path), None)
            if path is None:
                continue
            key = curie(path)
            if key in paths:
                raise SystemExit(
                    f"FAIL: {curie(shape)} has two property shapes on {key}. "
                    f"They would collapse onto one key and one would vanish from "
                    f"the signature."
                )
            paths[key] = _constraints(g, prop)
        deactivated = next(g.objects(shape, SH.deactivated), None)
        body = {
            "targetClass": curie(target) if target is not None else None,
            "deactivated": bool(deactivated) and str(deactivated).lower() == "true",
            "paths": dict(sorted(paths.items())),
        }
        # The digest is over the canonical JSON of the facts themselves, so it
        # cannot disagree with them -- two renderings of one thing is how the
        # digest and the diff come to tell different stories.
        body["sha256"] = digest(json.dumps(body, sort_keys=True))
        out[curie(shape)] = body
    return dict(sorted(out.items()))


def main() -> int:
    if "--check" in sys.argv:
        first, second = facts(), facts()
        if first != second:
            print("FAIL: shape signatures are not reproducible", file=sys.stderr)
            return 1
        if not first:
            print("FAIL: no shapes signed, so this check verified nothing", file=sys.stderr)
            return 1
        paths = sum(len(s["paths"]) for s in first.values())
        print(f"OK: {len(first)} shape signatures reproducible, {paths} constrained path(s)")
        return 0
    print(json.dumps(facts(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
