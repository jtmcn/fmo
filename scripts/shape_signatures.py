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
    poetry run python3 scripts/shape_signatures.py --audit PIN.json     # FMO's own
    poetry run python3 scripts/shape_signatures.py --update PIN.json    # re-pin
    poetry run python3 scripts/shape_signatures.py --compare BASELINE.json

--audit and --compare run the same comparison and differ only in what a verdict
costs. FMO's pin is audited, so a verdict fails the build; --compare reports and
exits 0, because a consumer's policy is the consumer's. See
docs/adr/0002-pin-the-export-contract.md.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from rdflib import BNode, Graph, Namespace, RDF, RDFS, URIRef

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


def _body_digest(body: dict) -> str:
    """Recompute the digest facts() would assign this body, ignoring any
    'sha256' key it already carries -- see compare()'s equal-digest check."""
    stripped = {k: v for k, v in body.items() if k != "sha256"}
    return digest(json.dumps(stripped, sort_keys=True))


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


def _single(g: Graph, subject, predicate, where: str):
    """The one object for a predicate, refusing a repeat.

    SHACL reads a repeated constraint conjunctively -- sh:class A, B requires
    both -- so an arbitrary pick drops the rest, and removing one of two later
    signs as no change at all. Same defect class as the two guards in facts().
    """
    values = list(g.objects(subject, predicate))
    if len(values) > 1:
        raise SystemExit(
            f"FAIL: {where} has {len(values)} {curie(predicate)} values: "
            f"{', '.join(sorted(curie(v) for v in values))}. SHACL applies all "
            f"of them; a signature holds one, so dropping the rest would hide a "
            f"weakening."
        )
    return values[0] if values else None


def _constraints(g: Graph, prop: BNode, where: str) -> dict:
    out: dict = {}
    for name, predicate in SCALAR_CONSTRAINTS.items():
        value = _single(g, prop, predicate, where)
        if value is None:
            continue
        out[name] = int(value) if name in ("minCount", "maxCount") else curie(value)
    listed = _single(g, prop, SH["in"], where)
    if listed is not None:
        out["in"] = sorted(curie(v) for v in g.items(listed))
    # Recorded explicitly rather than left absent: sh:Violation is the SHACL
    # default, and comparing an absent value against an explicit one would read a
    # default as a removal -- reporting a weakening that did not happen.
    severity = _single(g, prop, SH.severity, where)
    out["severity"] = curie(severity) if severity is not None else "sh:Violation"
    # Recorded explicitly, same reasoning as node-level deactivated below: an
    # unmodelled property-level sh:deactivated used to switch a constraint off
    # while facts() only read the predicate at the shape's own subject.
    deactivated = _single(g, prop, SH.deactivated, where)
    out["deactivated"] = bool(deactivated) and str(deactivated).lower() == "true"
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

    # UNDERSTOOD is a set of predicates, so it says nothing about WHERE one sits.
    # SHACL allows a constraint component directly on a node shape, facts() reads
    # constraints only under sh:property, and the predicate sweep above waves it
    # through as understood -- sh:nodeKind on a NodeShape signed identically to
    # its absence. Position, not just predicate.
    shapes = set(g.subjects(RDF.type, SH.NodeShape))
    node_level = sorted(
        f"{curie(s)} {curie(p)}"
        for s in shapes
        for p in (*SCALAR_CONSTRAINTS.values(), SH["in"])
        if (s, p, None) in g
    )
    if node_level:
        raise SystemExit(
            f"FAIL: {SHAPES.name} puts constraints directly on a node shape, where "
            f"this signer does not read them: {', '.join(node_level)}\n"
            f"      Move them under sh:property, or teach facts() to sign the node "
            f"level; ignoring them signs a constrained shape as an unconstrained one."
        )

    # A node shape needs no rdf:type: SHACL calls any subject of sh:targetClass a
    # shape, and pyshacl enforces one written that way. facts() collects by type,
    # so such a shape is signed by nobody and its later deletion is invisible.
    untyped = sorted(curie(s) for s in set(g.subjects(SH.targetClass, None)) - shapes)
    if untyped:
        raise SystemExit(
            f"FAIL: {SHAPES.name} has sh:targetClass on a subject that is not typed "
            f"sh:NodeShape: {', '.join(untyped)}\n"
            f"      SHACL still enforces it and this signer would not sign it. Add "
            f"`a sh:NodeShape`."
        )

    # sh:inversePath and friends are caught above as sh:-namespace predicates, but
    # a sequence path is a plain RDF list: it introduces no sh: predicate, and its
    # blank-node id becomes the signature's path key -- a fresh id per parse, so
    # --check fails on non-reproducibility naming no construct at all.
    complex_paths = sorted(
        curie(s) for s, o in g.subject_objects(SH.path) if not isinstance(o, URIRef)
    )
    if complex_paths:
        raise SystemExit(
            f"FAIL: {SHAPES.name} uses a non-IRI sh:path (a sequence, inverse or "
            f"alternative path) on {len(complex_paths)} property shape(s)\n"
            f"      The signature keys paths by IRI, and a path with no IRI keys by "
            f"blank node -- a different key on every parse."
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
        targets = list(g.objects(shape, SH.targetClass))
        if len(targets) > 1:
            # Same defect class as two property shapes on one sh:path below: an
            # arbitrary pick drops the rest, and removing one of several targets
            # would then read as no change at all.
            raise SystemExit(
                f"FAIL: {curie(shape)} has more than one sh:targetClass: "
                f"{', '.join(sorted(curie(t) for t in targets))}. "
                f"Only one can be represented in the signature, and dropping "
                f"the rest would hide a weakening from the digest."
            )
        target = targets[0] if targets else None
        paths: dict[str, dict] = {}
        for prop in g.objects(shape, SH.property):
            sh_path = _single(g, prop, SH.path, curie(shape))
            if sh_path is None:
                continue
            key = curie(sh_path)
            if key in paths:
                raise SystemExit(
                    f"FAIL: {curie(shape)} has two property shapes on {key}. "
                    f"They would collapse onto one key and one would vanish from "
                    f"the signature."
                )
            paths[key] = _constraints(g, prop, f"{curie(shape)} {key}")
        deactivated = _single(g, shape, SH.deactivated, curie(shape))
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

    Every declared class is a key, a leaf mapping to the empty set, so membership
    doubles as "is this class declared anywhere" for the target-undeclared rule.
    """
    from rdflib import OWL

    g = Graph()
    for rel in MODULES:
        g.parse(SRC / rel, format="turtle")
    direct: dict[str, set[str]] = {}
    declared = {curie(c) for c in g.subjects(RDF.type, OWL.Class) if isinstance(c, URIRef)}
    for child, parent in g.subject_objects(RDFS.subClassOf):
        if isinstance(child, URIRef) and isinstance(parent, URIRef):
            direct.setdefault(curie(parent), set()).add(curie(child))
            declared |= {curie(child), curie(parent)}

    below: dict[str, set[str]] = {}
    for parent in declared:
        seen, stack = set(), [parent]
        while stack:
            for child in direct.get(stack.pop(), set()):
                if child not in seen:
                    seen.add(child)
                    stack.append(child)
        below[parent] = seen
    # The one traversal here, guarded like every traversal in validate.py. An
    # empty map does not fail: it silently reclassifies every target-changed as
    # target-undeclared WEAKENED, so a real failure reports the wrong reason.
    if not below:
        raise SystemExit(
            "FAIL: no classes declared in the modules, so target narrowing "
            "cannot be judged and every target change would report as undeclared")
    return below


# Every branch that can emit a verdict, named. The suite asserts each is claimed
# by at least one mutant: review ablated the rules by hand and found three that no
# case exercised, while the plan claimed one case per row.
RULES = (
    "shape-removed", "shape-added", "deactivated-set", "deactivated-cleared",
    "target-removed", "target-narrowed", "target-undeclared", "target-changed",
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
    # Same rule names as the node-level check in compare(): switched off is
    # switched off, whether the predicate sits on the shape or on one property.
    if new.get("deactivated") and not old.get("deactivated"):
        out.append(_verdict(
            shape, "WEAKENED",
            f"{path}: sh:deactivated true: the property is switched off and enforces nothing",
            "deactivated-set"))
    elif old.get("deactivated") and not new.get("deactivated"):
        out.append(_verdict(shape, "CHANGED", f"{path}: sh:deactivated cleared", "deactivated-cleared"))

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

    # Absent means sh:Violation, the SHACL default: a baseline pinned before this
    # signer recorded severity meant Violation, and raising on its None aborted
    # the whole report -- suppressing the weakenings the run existed to surface.
    # An explicit unrecognised value still fails, which is what _severity_rank
    # guards against.
    old_sev, new_sev = old.get("severity", "sh:Violation"), new.get("severity", "sh:Violation")
    if _severity_rank(new_sev) < _severity_rank(old_sev):
        out.append(_verdict(shape, "WEAKENED",
                            f"{path}: severity {old_sev} -> {new_sev}",
                            "severity-weakened"))
    elif new_sev != old_sev:
        # The spec's table says every non-weakening is CHANGED. Without this the
        # weakening direction had a branch and the other did not, so a raised
        # severity was silent -- found by review, not by the eleven cases.
        out.append(_verdict(shape, "CHANGED",
                            f"{path}: severity {old_sev} -> {new_sev}",
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


def _check_baseline(base: dict, label: str = "baseline") -> None:
    """Refuse a malformed pin with the message every other failure here uses.

    --compare reads a caller-supplied path, the one genuinely external input to
    this tool, and compare() indexes it directly -- a missing key surfaced as a
    bare KeyError traceback rather than a FAIL line naming the file's problem.
    """
    if not isinstance(base, dict):
        raise SystemExit(f"FAIL: {label} must be a JSON object of shape name -> facts")
    for name, body in base.items():
        if not isinstance(body, dict):
            raise SystemExit(f"FAIL: {label} entry {name} is not an object")
        missing = sorted({"targetClass", "paths"} - set(body))
        if missing:
            raise SystemExit(
                f"FAIL: {label} entry {name} is missing {', '.join(missing)}")
        if not isinstance(body["paths"], dict):
            raise SystemExit(f"FAIL: {label} entry {name} has a non-object 'paths'")
        for path, constraints in body["paths"].items():
            if not isinstance(constraints, dict):
                raise SystemExit(
                    f"FAIL: {label} entry {name} path {path} is not an object")


def compare(base: dict, current: dict, below: dict[str, set[str]]) -> list[dict]:
    """Classify current against a pinned baseline.

    Full SHACL subsumption is undecidable. These rules cover the weakening that
    actually happens; everything else is reported as CHANGED rather than guessed
    at, and CHANGED means "a human decides", not "probably fine".
    """
    _check_baseline(base)
    out: list[dict] = []
    for name in sorted(set(base) | set(current)):
        # Skip the per-field rules when the two bodies are identical -- an
        # optimization, not a cross-check: recomputed here rather than trusted
        # from the stored 'sha256', so a baseline hand-edited to weaken a body
        # while its old digest was left in place is not skipped by mistake.
        if (
            name in base and name in current
            and _body_digest(base[name]) == _body_digest(current[name])
        ):
            continue
        in_base = name in base
        in_current = name in current
        if in_current and not in_base:
            out.append(_verdict(name, "CHANGED",
                                "shape added to the contract", "shape-added"))
            continue
        if in_base and not in_current:
            out.append(_verdict(name, "WEAKENED",
                                "shape removed from the contract", "shape-removed"))
            continue

        # Both present from here on -- membership established above, so the
        # dict indexing below is non-optional.
        old, new = base[name], current[name]

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
            elif new_target not in below:
                # No ontology declares it, so nothing is ever typed with it and
                # the shape matches no focus nodes -- target-removed's failure
                # mode reached by a typo, or by the class leaving src/.
                out.append(_verdict(
                    name, "WEAKENED",
                    f"targetClass {old_target} -> {new_target}, which no module "
                    f"declares: the shape matches no focus nodes, and a shape "
                    f"matching none conforms", "target-undeclared"))
            elif new_target in below.get(old_target, set()):
                out.append(_verdict(
                    name, "WEAKENED",
                    f"targetClass narrowed {old_target} -> {new_target}: fewer focus "
                    f"nodes, and a shape matching none conforms", "target-narrowed"))
            else:
                out.append(_verdict(
                    name, "CHANGED", f"targetClass {old_target} -> {new_target}", "target-changed"))

        for path in sorted(set(old["paths"]) | set(new["paths"])):
            was_in = path in old["paths"]
            now_in = path in new["paths"]
            if now_in and not was_in:
                out.append(_verdict(name, "CHANGED",
                                    f"{path}: path newly constrained", "path-added"))
            elif was_in and not now_in:
                out.append(_verdict(name, "WEAKENED",
                                    f"{path}: path no longer constrained", "path-removed"))
            else:
                out.extend(_compare_path(name, path,
                                         old["paths"][path], new["paths"][path]))
    return out


PIN_COMMENT = (
    "GENERATED by scripts/shape_signatures.py -- DO NOT HAND-EDIT. FMO's own pin "
    "on shapes/thermaledge-export.ttl, audited by `make shape-signatures`. "
    "Regenerate with `make shape-signatures-update` and review the diff. A "
    "consumer's pin is a different file, held by the consumer."
)


def load_pin(path: Path, label: str = "pin") -> dict:
    """Read a pin, dropping the `_comment` header before compare() indexes it.

    Underscore keys are this repo's JSON-comment idiom: production-expectations
    and class-coverage-expectations both carry one and both strip it the same
    way. Stripping here rather than in compare() keeps the classifier's input a
    map of shape name -> facts and nothing else.

    `label` is the word the caller's flag uses -- README documents --compare's
    argument as a BASELINE, and its messages should keep saying so.
    """
    if not path.is_file():
        raise SystemExit(f"FAIL: no {label} at {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"FAIL: {label} at {path} is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise SystemExit(f"FAIL: {label} must be a JSON object of shape name -> facts")
    stripped = {k: v for k, v in raw.items() if not k.startswith("_")}
    # Validated here as well as in compare(), so the message says whose file it is:
    # --audit reads FMO's pin and must not report it as "the baseline". compare()
    # keeps its own call for callers that build a baseline without going through here.
    _check_baseline(stripped, label)
    return stripped


def _pin_path(flag: str, arg: str = "PIN.json") -> Path | None:
    """The path argument for one flag, or None with the message already printed.

    `arg` names the file in that message: README documents --compare's argument
    as a BASELINE, and a consumer reading that should not be told about PIN.json.
    """
    idx = sys.argv.index(flag) + 1
    # A following flag is a missing path, not a path named "--check": taking it
    # literally reports "no pin at --check", which describes the wrong mistake.
    if idx >= len(sys.argv) or sys.argv[idx].startswith("--"):
        print(f"FAIL: {flag} requires a {arg} path", file=sys.stderr)
        return None
    return Path(sys.argv[idx])


def main() -> int:
    if "--update" in sys.argv:
        pin = _pin_path("--update")
        if pin is None:
            return 1
        # Reproducibility first: pinning a signature that churns pins noise, and
        # the next run then fails for a reason nobody can act on.
        first, second = facts(), facts()
        if first != second:
            print("FAIL: shape signatures are not reproducible; refusing to pin",
                  file=sys.stderr)
            return 1
        if not first:
            print("FAIL: no shapes signed, so the pin would assert nothing",
                  file=sys.stderr)
            return 1
        try:
            pin.write_text(
                json.dumps({"_comment": PIN_COMMENT, **first}, indent=2) + "\n",
                encoding="utf-8")
        except OSError as exc:
            print(f"FAIL: cannot write the pin to {pin}: {exc}", file=sys.stderr)
            return 1
        print(f"OK: pinned {len(first)} shape signature(s) to {pin}")
        return 0

    if "--audit" in sys.argv:
        pin = _pin_path("--audit")
        if pin is None:
            return 1
        base = load_pin(pin)
        current = facts()
        # Neither side may be empty. Comparing nothing to nothing prints OK having
        # asserted nothing, which is the vacuity `make meta` exists to reject -- and
        # --check running first in the Makefile is a guard living somewhere else.
        if not base:
            print(f"FAIL: {pin} holds no shape signatures, so the audit asserted nothing",
                  file=sys.stderr)
            return 1
        if not current:
            print("FAIL: no shapes signed, so the audit compared nothing",
                  file=sys.stderr)
            return 1
        # Any verdict fails, not only a WEAKENED one: a loosened numeric range
        # classifies as value-changed, and that is the weakening this pin exists
        # to catch. See docs/adr/0002-pin-the-export-contract.md.
        verdicts = compare(base, current, subclass_map())
        if verdicts:
            print(f"FAIL: the export contract moved ({len(verdicts)} verdict(s)):",
                  file=sys.stderr)
            for v in verdicts:
                print(f"  {v['verdict']} [{v['rule']}] {v['shape']}: {v['detail']}",
                      file=sys.stderr)
            print("If the change is intended, run `make shape-signatures-update` "
                  "and review the diff.", file=sys.stderr)
            return 1
        print(f"OK: {len(base)} shape signature(s) match the pin")
        return 0

    if "--compare" in sys.argv:
        baseline = _pin_path("--compare", "BASELINE.json")
        if baseline is None:
            return 1
        base = load_pin(baseline, "baseline")
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
