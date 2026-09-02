#!/usr/bin/env python3
"""Tests for the shapes-drift signer and classifier.

Pure rdflib, no ROBOT: these are questions about the shapes file, not about
what a reasoner derives from the ontology.

Run: python3 scripts/test_shape_drift.py
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import shape_signatures as S  # noqa: E402
from registry import SHAPES  # noqa: E402


def with_edit(find: str, replace: str) -> Path:
    """A scratch copy of the shapes file with one textual edit applied.

    Through the file and the real parser, never through the parsed dicts: both
    sides of a comparison would otherwise come from one facts() call, the
    signer/classifier seam would go untested, and a bug in facts() would cancel
    itself out.
    """
    text = SHAPES.read_text(encoding="utf-8")
    if text.count(find) != 1:
        raise LookupError(f"anchor appears {text.count(find)} times: {find!r}")
    tmp = Path(tempfile.mkdtemp()) / SHAPES.name
    tmp.write_text(text.replace(find, replace), encoding="utf-8")
    return tmp


# (name, rule exercised, find, replace, {(shape, verdict, rule)}, detail fragment)
CASES = [
    ("a node shape switched off", "deactivated-set",
     "teh:TargetShape a sh:NodeShape ;",
     "teh:TargetShape a sh:NodeShape ;\n    sh:deactivated true ;",
     {("teh:TargetShape", "WEAKENED", "deactivated-set")}, "switched off"),

    ("a property shape switched off", "deactivated-set",
     "        sh:path wx:underProtocol ;", "        sh:path wx:underProtocol ;\n        sh:deactivated true ;",
     {("teh:TargetShape", "WEAKENED", "deactivated-set")}, "switched off"),

    ("a node shape removed", "shape-removed",
     "teh:ProtocolShape a sh:NodeShape ;", "teh:Unused a sh:NodeShape ;",
     {("teh:ProtocolShape", "WEAKENED", "shape-removed"), ("teh:Unused", "CHANGED", "shape-added")}, "removed"),

    ("a node shape added", "shape-added",
     "teh:ProtocolShape a sh:NodeShape ;",
     "teh:Extra a sh:NodeShape ; sh:targetClass fm:Document .\n\nteh:ProtocolShape a sh:NodeShape ;",
     {("teh:Extra", "CHANGED", "shape-added")}, "added"),

    ("targetClass removed", "target-removed",
     "    sh:targetClass ksh:Market ;", "",
     {("teh:MarketShape", "WEAKENED", "target-removed")}, "matches no focus nodes"),

    ("targetClass narrowed to a subclass", "target-narrowed",
     "    sh:targetClass ksh:Market ;", "    sh:targetClass ksh:WeatherMarket ;",
     {("teh:MarketShape", "WEAKENED", "target-narrowed")}, "narrowed"),

    ("targetClass widened to a superclass", "target-changed",
     "    sh:targetClass fm:ProbabilityAssignment ;",
     "    sh:targetClass fm:InformationContentEntity ;",
     {("teh:ProbabilityShape", "CHANGED", "target-changed")}, "targetClass"),

    ("a required path removed", "path-removed",
     "        sh:path ksh:marketTicker ;", "        sh:path ksh:ignoredTicker ;",
     {("teh:MarketShape", "WEAKENED", "path-removed"), ("teh:MarketShape", "CHANGED", "path-added")},
     "ksh:marketTicker"),

    ("minCount lowered", "min-weakened",
     "        sh:path fm:statedAs ;\n        sh:minCount 1 ;",
     "        sh:path fm:statedAs ;\n        sh:minCount 0 ;",
     {("teh:ProtocolShape", "WEAKENED", "min-weakened")}, "minCount 1 -> 0"),

    ("minCount removed", "min-weakened",
     "        sh:path fm:statedAs ;\n        sh:minCount 1 ;",
     "        sh:path fm:statedAs ;",
     {("teh:ProtocolShape", "WEAKENED", "min-weakened")}, "minCount 1 -> None"),

    ("minCount raised", "min-changed",
     "        sh:path fm:statedAs ;\n        sh:minCount 1 ;",
     "        sh:path fm:statedAs ;\n        sh:minCount 2 ;",
     {("teh:ProtocolShape", "CHANGED", "min-changed")}, "minCount 1 -> 2"),

    ("maxCount raised", "max-weakened",
     "        sh:path ksh:expressesProposition ;\n        sh:minCount 1 ; sh:maxCount 1 ;",
     "        sh:path ksh:expressesProposition ;\n        sh:minCount 1 ; sh:maxCount 2 ;",
     {("teh:MarketShape", "WEAKENED", "max-weakened")}, "maxCount 1 -> 2"),

    ("maxCount removed", "max-weakened",
     "        sh:path ksh:expressesProposition ;\n        sh:minCount 1 ; sh:maxCount 1 ;",
     "        sh:path ksh:expressesProposition ;\n        sh:minCount 1 ;",
     {("teh:MarketShape", "WEAKENED", "max-weakened")}, "maxCount 1 -> None"),

    ("maxCount lowered", "max-changed",
     "        sh:path fm:hasComparator ;\n        sh:minCount 1 ; sh:maxCount 1 ;",
     "        sh:path fm:hasComparator ;\n        sh:minCount 1 ; sh:maxCount 0 ;",
     {("teh:PropositionShape", "CHANGED", "max-changed")}, "maxCount 1 -> 0"),

    ("a value constraint removed", "value-removed",
     "        sh:class wx:WeatherObservationTarget ;", "",
     {("teh:PropositionShape", "WEAKENED", "value-removed")}, "class constraint removed"),

    ("a value constraint changed", "value-changed",
     "        sh:class wx:WeatherObservationTarget ;", "        sh:class fm:ObservationTarget ;",
     {("teh:PropositionShape", "CHANGED", "value-changed")}, "class"),

    ("severity lowered", "severity-weakened",
     "        sh:path wx:underProtocol ;", "        sh:path wx:underProtocol ;\n        sh:severity sh:Warning ;",
     {("teh:TargetShape", "WEAKENED", "severity-weakened")}, "severity"),

    ("targetClass changed to a class no module declares", "target-undeclared",
     "    sh:targetClass ksh:Market ;", "    sh:targetClass ksh:Merket ;",
     {("teh:MarketShape", "WEAKENED", "target-undeclared")}, "no module declares"),
]

# severity-changed, deactivated-cleared and path-added need a mutated BASELINE
# rather than a mutated current file: they are the reverse of a case above.
REVERSE_CASES = [
    ("severity raised", "severity-changed",
     "        sh:path wx:underProtocol ;", "        sh:path wx:underProtocol ;\n        sh:severity sh:Warning ;",
     {("teh:TargetShape", "CHANGED", "severity-changed")}, "severity"),
    ("a shape switched back on", "deactivated-cleared",
     "teh:TargetShape a sh:NodeShape ;", "teh:TargetShape a sh:NodeShape ;\n    sh:deactivated true ;",
     {("teh:TargetShape", "CHANGED", "deactivated-cleared")}, "cleared"),
    ("a property shape switched back on", "deactivated-cleared",
     "        sh:path wx:underProtocol ;", "        sh:path wx:underProtocol ;\n        sh:deactivated true ;",
     {("teh:TargetShape", "CHANGED", "deactivated-cleared")}, "cleared"),
    ("a path added", "path-added",
     "        sh:path ksh:marketTicker ;", "        sh:path ksh:ignoredTicker ;",
     {("teh:MarketShape", "CHANGED", "path-added"), ("teh:MarketShape", "WEAKENED", "path-removed")},
     "ksh:marketTicker"),
]


def _check(name, rule, got, expected, fragment) -> list[str]:
    seen = {(v["shape"], v["verdict"], v["rule"]) for v in got}
    if seen != expected:
        return [f"[{name}] verdicts {sorted(seen)} != expected {sorted(expected)}"]
    if not any(fragment in v["detail"] for v in got):
        return [f"[{name}] no detail contains {fragment!r}: {[v['detail'] for v in got]}"]
    if rule not in {v["rule"] for v in got}:
        return [f"[{name}] no verdict came from rule {rule!r}: {[v['rule'] for v in got]}"]
    print(f"  ok   [{name}] {rule}")
    return []


def test_classifier() -> list[str]:
    problems, below = [], S.subclass_map()
    base = S.facts()
    for name, rule, find, replace, expected, fragment in CASES:
        got = S.compare(base, S.facts(with_edit(find, replace)), below)
        problems += _check(name, rule, got, expected, fragment)
    # Reversed: the edited file is the BASELINE and today's file is current.
    for name, rule, find, replace, expected, fragment in REVERSE_CASES:
        got = S.compare(S.facts(with_edit(find, replace)), base, below)
        problems += _check(name, rule, got, expected, fragment)
    return problems


def test_every_rule_is_claimed() -> list[str]:
    """The assertion the plan's first draft only claimed in prose.

    Review ablated each rule by hand and found three that no case exercised --
    including a row of the spec's own table -- while the plan asserted "one case
    per row". A coverage claim nothing checks is the defect this phase is about.
    """
    claimed = {rule for _, rule, *_ in CASES} | {rule for _, rule, *_ in REVERSE_CASES}
    missing = sorted(set(S.RULES) - claimed)
    return [f"rules no mutant exercises: {missing}"] if missing else []


def test_no_false_positives() -> list[str]:
    """The case that keeps the alarm worth reading.

    Not compare(facts(), facts()) -- identical inputs are a tautology that cannot
    fail. This reformats the Turtle, rewrites a message and adds a comment, all
    through the real parser.
    """
    edited = with_edit(
        "        sh:minCount 1 ; sh:maxCount 1 ;\n        sh:datatype",
        "# an added comment\n        sh:minCount 1 ;\n        sh:maxCount 1 ;\n        sh:datatype",
    )
    text = edited.read_text(encoding="utf-8").replace(
        "every market expresses exactly one proposition", "reworded entirely")
    edited.write_text(text, encoding="utf-8")
    got = S.compare(S.facts(), S.facts(edited), S.subclass_map())
    return [] if not got else [f"a reformat and a message edit produced verdicts: {got}"]


def test_facts_shape() -> list[str]:
    problems = []
    facts = S.facts()
    if set(facts) != {
        "teh:MarketShape", "teh:PropositionShape", "teh:TargetShape",
        "teh:ProtocolShape", "teh:ProbabilityShape",
    }:
        problems.append(f"unexpected shape set: {sorted(facts)}")
        return problems

    market = facts["teh:MarketShape"]
    if market["targetClass"] != "ksh:Market":
        problems.append(f"MarketShape targetClass: {market['targetClass']}")
    ticker = market["paths"].get("ksh:marketTicker", {})
    if ticker.get("minCount") != 1 or ticker.get("maxCount") != 1:
        problems.append(f"marketTicker counts: {ticker}")
    if ticker.get("datatype") != "xsd:string":
        problems.append(f"marketTicker datatype: {ticker}")
    if ticker.get("severity") != "sh:Violation":
        problems.append(f"severity must default to Violation, got {ticker}")
    if "message" in ticker:
        problems.append("sh:message must not be captured")
    if market.get("deactivated") is not False:
        problems.append(f"deactivated must be recorded and False here: {market.get('deactivated')}")
    return problems


# (name, find, replace, fragment the refusal must name). Every one of these is a
# construct SHACL enforces and this signer does not read: signing it as though it
# were absent is the sh:deactivated hole, and each of the last four was one.
REFUSALS = [
    ("sh:closed", "teh:ProtocolShape a sh:NodeShape ;",
     "teh:ProtocolShape a sh:NodeShape ;\n    sh:closed true ;", "sh:closed"),

    ("duplicate sh:path", "        sh:path fm:hasComparator ;",
     "        sh:path fm:hasSubject ;", "two property shapes"),

    ("duplicate sh:targetClass", "    sh:targetClass ksh:Market ;",
     "    sh:targetClass ksh:Market ;\n    sh:targetClass fm:Proposition ;", "sh:targetClass"),

    # facts() reads constraints only under sh:property, while UNDERSTOOD matches
    # on predicate alone -- so this signed identically to its absence.
    ("a constraint on the node shape itself", "teh:ProtocolShape a sh:NodeShape ;",
     "teh:ProtocolShape a sh:NodeShape ;\n    sh:nodeKind sh:IRI ;",
     "directly on a node shape"),

    # SHACL calls any subject of sh:targetClass a shape and pyshacl enforces it;
    # facts() collects by rdf:type, so nobody signed it.
    ("a node shape with no rdf:type", "teh:ProtocolShape a sh:NodeShape ;",
     "teh:ProtocolShape", "not typed"),

    # No sh: predicate to catch: an RDF list whose blank-node id would become the
    # path key, fresh on every parse.
    ("a sequence path", "        sh:path ksh:expressesProposition ;",
     "        sh:path ( ksh:expressesProposition fm:hasSubject ) ;", "non-IRI sh:path"),

    # sh:class A, B requires both; keeping one made removing the other invisible.
    ("a repeated constraint predicate", "        sh:class wx:WeatherObservationTarget ;",
     "        sh:class wx:WeatherObservationTarget ;\n        sh:class fm:ObservationTarget ;",
     "sh:class values"),
]


def test_refuses_unmodelled() -> list[str]:
    """An unmodelled construct must fail the signer, not be ignored.

    This is the guard that would have caught sh:deactivated during design instead
    of during review.
    """
    problems = []
    for name, find, replace, fragment in REFUSALS:
        try:
            S.facts(with_edit(find, replace))
            problems.append(f"[{name}] was signed rather than refused")
        except SystemExit as exc:
            if fragment not in str(exc):
                problems.append(f"[{name}] refusal does not name {fragment!r}: {exc}")
            else:
                print(f"  ok   [refuses unmodelled] {name}")
    return problems


def test_baseline_is_not_trusted() -> list[str]:
    """Two ways a caller-supplied pin took the whole report down with it.

    --compare's baseline is the one input this tool does not produce itself, so
    an old or hand-edited one must degrade to a verdict, never to a traceback or
    to silence.
    """
    problems, below = [], S.subclass_map()
    base = S.facts()

    # A pin written before this signer recorded severity. Absent is the SHACL
    # default, not an unknown value: raising on it emitted no verdicts at all,
    # including the weakening the run existed to find.
    stale = json.loads(json.dumps(base))
    for body in stale.values():
        for constraints in body["paths"].values():
            constraints.pop("severity", None)
    weakened = S.facts(with_edit(
        "        sh:path fm:statedAs ;\n        sh:minCount 1 ;",
        "        sh:path fm:statedAs ;\n        sh:minCount 0 ;"))
    try:
        got = S.compare(stale, weakened, below)
        rules = {v["rule"] for v in got}
        if "min-weakened" not in rules:
            problems.append(f"a baseline predating severity lost the weakening: {rules}")
        else:
            print("  ok   [baseline] one predating severity still reports the weakening")
    except SystemExit as exc:
        problems.append(f"a baseline predating severity aborted the report: {exc}")

    malformed = json.loads(json.dumps(base))
    malformed["teh:MarketShape"].pop("targetClass")
    try:
        S.compare(malformed, base, below)
        problems.append("a baseline missing targetClass was accepted")
    except SystemExit as exc:
        if "missing targetClass" not in str(exc):
            problems.append(f"malformed-baseline refusal is the wrong error: {exc}")
        else:
            print("  ok   [baseline] a missing key fails with a message, not a traceback")
    except Exception as exc:  # noqa: BLE001 - the traceback this guard exists to stop
        problems.append(f"a baseline missing targetClass raised {type(exc).__name__}: {exc}")
    return problems


def test_subclass_map_refuses_an_empty_hierarchy() -> list[str]:
    """subclass_map's traversal, guarded like every traversal in validate.py.

    An empty hierarchy does not fail on its own: membership doubles as "is this
    class declared", so every target-changed silently becomes target-undeclared
    WEAKENED -- a wrong reason on a real failure. Now that `make shape-signatures`
    audits FMO's own pin, that reason reaches a build. Run it empty rather than
    reading the guard.
    """
    problems: list[str] = []
    saved = S.MODULES
    try:
        S.MODULES = []
        try:
            S.subclass_map()
            problems.append("subclass_map accepted a hierarchy with no classes")
        except SystemExit as exc:
            if "no classes declared" not in str(exc):
                problems.append(f"the empty-hierarchy refusal is the wrong error: {exc}")
            else:
                print("  ok   [subclass_map] an empty hierarchy fails, not misclassifies")
    finally:
        S.MODULES = saved
    return problems


def _pin_file(body: object) -> Path:
    """A scratch pin holding exactly `body`, written the way --update writes one."""
    tmp = Path(tempfile.mkdtemp()) / "pin.json"
    tmp.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    return tmp


def _cli(argv: list[str], facts=None) -> tuple[int, str]:
    """One shape_signatures CLI branch, run in process, with its output captured.

    In process rather than by subprocess because the guards under test are about
    inputs the CLI reads, and half of them need facts() to return nothing --
    which through a subprocess would mean copying the tree to empty the shapes
    file. `facts` replaces it directly instead.
    """
    out, err = io.StringIO(), io.StringIO()
    saved_argv, saved_facts = sys.argv, S.facts
    try:
        sys.argv = ["shape_signatures.py", *argv]
        if facts is not None:
            S.facts = facts
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                rc = S.main()
            except SystemExit as exc:
                # load_pin and shapes_graph refuse with SystemExit; the CLI branches
                # return 1. Both are failures, and this suite judges the message.
                return 1, str(exc)
    finally:
        sys.argv, S.facts = saved_argv, saved_facts
    return rc, out.getvalue() + err.getvalue()


def test_cli_guards() -> list[str]:
    """Every refusal the pin side can produce, each with nothing else guarding it.

    These were added in review, which makes them exactly the code most likely to
    be silently inverted later: a guard nothing runs is a guard nothing keeps.
    `make meta` sweeps validate.py's checks and does not reach this file, so the
    equivalent discipline is written out here.
    """
    problems: list[str] = []
    real = S.facts()
    good = {"_comment": S.PIN_COMMENT, **json.loads(json.dumps(real))}
    missing = Path(tempfile.mkdtemp()) / "absent.json"
    not_json = _pin_file({})
    not_json.write_text("{ this is not json", encoding="utf-8")

    hand_edited = json.loads(json.dumps(good))
    body = hand_edited["teh:ProbabilityShape"]
    # The exact attack the digest guard exists to stop: weaken the pinned bound so
    # it matches a weakened shapes file, and leave the generated sha256 in place.
    body["paths"]["fm:probabilityValue"]["minInclusive"] = "-1"

    wrong_header = json.loads(json.dumps(good))
    wrong_header["_comment"] = "hand-written, and nothing noticed"

    cases = [
        ("a flag taken as the pin path", ["--audit", "--check"], None,
         "requires a PIN.json path"),
        ("a pin that is not there", ["--audit", str(missing)], None, "no pin at"),
        ("a pin that is not valid JSON", ["--audit", str(not_json)], None,
         "is not valid JSON"),
        ("a pin that is not an object", ["--audit", str(_pin_file([]))], None,
         "must be a JSON object"),
        ("a pin holding no signatures", ["--audit", str(_pin_file({"_comment": S.PIN_COMMENT}))],
         None, "holds no shape signatures"),
        ("an audit with no shapes to compare", ["--audit", str(_pin_file(good))],
         dict, "the audit compared nothing"),
        ("a pin edited by hand to match a weakened shapes file",
         ["--audit", str(_pin_file(hand_edited))], None, "was hand-edited"),
        ("a pin whose generated header drifted",
         ["--audit", str(_pin_file(wrong_header))], None,
         "does not carry the generated header"),
        ("an update with no shapes to sign", ["--update", str(_pin_file({}))],
         dict, "the pin would assert nothing"),
        ("an update the filesystem refuses",
         ["--update", str(missing.parent / "no-such-dir" / "pin.json")], None,
         "cannot write the pin"),
    ]
    for name, argv, facts, expect in cases:
        rc, output = _cli(argv, facts=facts)
        if rc == 0:
            problems.append(f"[{name}] exited 0; the guard did not fire")
        elif expect not in output:
            problems.append(f"[{name}] failed with the wrong message: {output.strip()!r}")
        else:
            print(f"  ok   [guard] {name}")

    # Reproducibility has to vary between two calls, so it cannot ride the table.
    seq = iter([real, {k: v for k, v in list(real.items())[:1]}])
    rc, output = _cli(["--update", str(_pin_file({}))], facts=lambda *a, **k: next(seq))
    if rc == 0 or "not reproducible" not in output:
        problems.append(f"[a signature that churns] rc={rc}, output={output.strip()!r}")
    else:
        print("  ok   [guard] a signature that churns is refused rather than pinned")

    rc, output = _cli(["--check"], facts=lambda *a, **k: {})
    if rc == 0 or "verified nothing" not in output:
        problems.append(f"[--check with nothing signed] rc={rc}, output={output.strip()!r}")
    else:
        print("  ok   [guard] --check with nothing signed verifies nothing, and says so")

    try:
        S.shapes_graph(missing)
        problems.append("shapes_graph accepted a path that is not there")
    except SystemExit as exc:
        if "no shapes file at" not in str(exc):
            problems.append(f"the missing-shapes refusal is the wrong error: {exc}")
        else:
            print("  ok   [guard] a missing shapes file fails with a message, not a traceback")
    return problems


def main() -> int:
    problems = (
        test_facts_shape() + test_refuses_unmodelled() + test_classifier()
        + test_baseline_is_not_trusted()
        + test_subclass_map_refuses_an_empty_hierarchy()
        + test_cli_guards()
        + test_every_rule_is_claimed() + test_no_false_positives()
    )
    for p in problems:
        print(f"  FAIL {p}")
    if problems:
        print(f"\n{len(problems)} problem(s)")
        return 1
    total = len(CASES) + len(REVERSE_CASES)
    print(f"\nOK: {total} mutants over {len(S.RULES)} rules, no false positives")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
