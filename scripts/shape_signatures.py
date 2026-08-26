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

from registry import MODULES, ONTOLOGY_PREFIXES, SHAPES, SRC  # noqa: E402

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


SEVERITY_ORDER = {"sh:Violation": 3, "sh:Warning": 2, "sh:Info": 1}


def _severity_rank(value: str | None) -> int:
    """Rank a severity, refusing one this classifier does not know.

    Defaulting an unrecognised IRI to 0 would sort it below sh:Info, so a typo in
    the baseline would make every later comparison look fine and a typo in the
    current file would read as a weakening that did not happen.
    """
    if value not in SEVERITY_ORDER:
        raise SystemExit(f"FAIL: unknown sh:severity {value!r}")
    return SEVERITY_ORDER[value]


def subclass_map() -> dict[str, set[str]]:
    """class curie -> every class curie beneath it, transitively.

    Needed for one rule only, and that rule is why this classifier lives in FMO
    rather than in the consumer: narrowing a target class is a weakening, and
    deciding whether the new target is narrower requires the subsumption
    hierarchy. FMO's README records being bitten by exactly this -- MarketShape
    once targeted ksh:WeatherMarket, matched no focus node on an export typing
    markets as ksh:Market, and conformed with a probability of 7.41.
    """
    from rdflib import RDFS, URIRef

    g = Graph()
    for rel in MODULES:
        g.parse(SRC / rel, format="turtle")
    direct: dict[str, set[str]] = {}
    for child, parent in g.subject_objects(RDFS.subClassOf):
        if isinstance(child, URIRef) and isinstance(parent, URIRef):
            direct.setdefault(curie(parent), set()).add(curie(child))

    below: dict[str, set[str]] = {}
    for parent in direct:
        seen, stack = set(), [parent]
        while stack:
            for child in direct.get(stack.pop(), set()):
                if child not in seen:
                    seen.add(child)
                    stack.append(child)
        below[parent] = seen
    return below


# Every branch that can emit a verdict, named. The suite asserts each is claimed
# by at least one mutant: review ablated the rules by hand and found three that no
# case exercised, while the plan claimed one case per row.
RULES = (
    "shape-removed", "shape-added", "deactivated-set", "deactivated-cleared",
    "target-removed", "target-narrowed", "target-changed",
    "path-removed", "path-added",
    "min-weakened", "min-changed", "max-weakened", "max-changed",
    "severity-weakened", "severity-changed",
    "value-removed", "value-changed",
)


def _verdict(shape: str, verdict: str, detail: str, rule: str) -> dict:
    assert rule in RULES, rule
    return {"shape": shape, "verdict": verdict, "detail": detail, "rule": rule}


def _compare_path(shape: str, path: str, old: dict, new: dict) -> list[dict]:
    out = []
    old_min, new_min = old.get("minCount"), new.get("minCount")
    if old_min is not None and (new_min is None or new_min < old_min):
        out.append(_verdict(shape, "WEAKENED",
                            f"{path}: minCount {old_min} -> {new_min}", "min-weakened"))
    elif new_min != old_min:
        out.append(_verdict(shape, "CHANGED", f"{path}: minCount {old_min} -> {new_min}",
                            "min-changed"))

    old_max, new_max = old.get("maxCount"), new.get("maxCount")
    if old_max is not None and (new_max is None or new_max > old_max):
        out.append(_verdict(shape, "WEAKENED",
                            f"{path}: maxCount {old_max} -> {new_max}", "max-weakened"))
    elif new_max != old_max:
        out.append(_verdict(shape, "CHANGED", f"{path}: maxCount {old_max} -> {new_max}",
                            "max-changed"))

    if _severity_rank(new.get("severity")) < _severity_rank(old.get("severity")):
        out.append(_verdict(shape, "WEAKENED",
                            f"{path}: severity {old.get('severity')} -> {new.get('severity')}",
                            "severity-weakened"))
    elif new.get("severity") != old.get("severity"):
        # The spec's table says every non-weakening is CHANGED. Without this the
        # weakening direction had a branch and the other did not, so a raised
        # severity was silent -- found by review, not by the eleven cases.
        out.append(_verdict(shape, "CHANGED",
                            f"{path}: severity {old.get('severity')} -> {new.get('severity')}",
                            "severity-changed"))

    for key in ("class", "datatype", "nodeKind", "pattern",
                "minInclusive", "maxInclusive", "in"):
        was, now = old.get(key), new.get(key)
        if was is not None and now is None:
            out.append(_verdict(shape, "WEAKENED", f"{path}: {key} constraint removed",
                                "value-removed"))
        elif was != now:
            out.append(_verdict(shape, "CHANGED", f"{path}: {key} {was} -> {now}", "value-changed"))
    return out


def compare(base: dict, current: dict, below: dict[str, set[str]]) -> list[dict]:
    """Classify current against a pinned baseline.

    Full SHACL subsumption is undecidable. These rules cover the weakening that
    actually happens; everything else is reported as CHANGED rather than guessed
    at, and CHANGED means "a human decides", not "probably fine".
    """
    out: list[dict] = []
    for name in sorted(set(base) | set(current)):
        # Equal digests must mean no verdicts. The digest is over the same facts
        # the rules read, so a disagreement means facts() and compare() have
        # drifted apart -- cheap to assert, and otherwise sha256 is dead weight
        # that nothing reads.
        if (
            name in base and name in current
            and base[name].get("sha256") == current[name].get("sha256")
        ):
            continue
        old, new = base.get(name), current.get(name)
        if old is not None and new is None:
            out.append(_verdict(name, "WEAKENED", "shape removed from the contract",
                                "shape-removed"))
            continue
        if new is not None and old is None:
            out.append(_verdict(name, "CHANGED", "shape added to the contract", "shape-added"))
            continue

        if new.get("deactivated") and not old.get("deactivated"):
            out.append(_verdict(
                name, "WEAKENED",
                "sh:deactivated true: the shape is switched off and enforces nothing",
                "deactivated-set"))
        elif old.get("deactivated") and not new.get("deactivated"):
            out.append(_verdict(name, "CHANGED", "sh:deactivated cleared", "deactivated-cleared"))

        old_target, new_target = old["targetClass"], new["targetClass"]
        if old_target != new_target:
            if new_target is None:
                # The extreme of the narrowing rule below: no target class means no
                # focus nodes at all, and a shape matching none conforms. An absent
                # class has no subclasses, so the narrowing test cannot see it.
                out.append(_verdict(
                    name, "WEAKENED",
                    f"targetClass removed (was {old_target}): the shape matches "
                    f"no focus nodes, and a shape matching none conforms", "target-removed"))
            elif new_target in below.get(old_target, set()):
                out.append(_verdict(
                    name, "WEAKENED",
                    f"targetClass narrowed {old_target} -> {new_target}: fewer focus "
                    f"nodes, and a shape matching none conforms", "target-narrowed"))
            else:
                out.append(_verdict(
                    name, "CHANGED", f"targetClass {old_target} -> {new_target}", "target-changed"))

        for path in sorted(set(old["paths"]) | set(new["paths"])):
            was, now = old["paths"].get(path), new["paths"].get(path)
            if was is not None and now is None:
                out.append(_verdict(name, "WEAKENED", f"{path}: path no longer constrained",
                                    "path-removed"))
            elif now is not None and was is None:
                out.append(_verdict(name, "CHANGED", f"{path}: path newly constrained", "path-added"))
            else:
                out.extend(_compare_path(name, path, was, now))
    return out


def main() -> int:
    if "--compare" in sys.argv:
        baseline = Path(sys.argv[sys.argv.index("--compare") + 1])
        if not baseline.is_file():
            print(f"FAIL: no baseline at {baseline}", file=sys.stderr)
            return 1
        base = json.loads(baseline.read_text(encoding="utf-8"))
        # Exit 0 whenever a report was produced: what a verdict is worth is the
        # caller's policy, and returning non-zero here would make FMO decide it.
        print(json.dumps({"verdicts": compare(base, facts(), subclass_map())}, indent=2))
        return 0
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
