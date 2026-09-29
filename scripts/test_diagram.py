#!/usr/bin/env python3
"""Negative tests for the extraction checks in `make diagram-check`.

Each case builds the map's data, damages one thing the panel or search depends
on, and asserts check() fails naming it. Nothing is written to disk.

Run: python3 scripts/test_diagram.py
"""

from __future__ import annotations

import copy
import sys
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_diagram as gd  # noqa: E402


def node(data: dict, cid: str) -> dict:
    return next(n for n in data["nodes"] if n["id"] == cid)


def drop_history(d: dict) -> None:
    node(d, "wx:SnowDepth")["history"] = []


def drop_field(d: dict) -> None:
    d["datatypes"]["ksh:yesBidDollars"]["fields"] = []


def drop_tombstone(d: dict) -> None:
    del d["retired"]["ksh:yesBidCents"]


def strand_tombstone(d: dict) -> None:
    d["retired"]["ksh:yesBidCents"]["to"] = ["ksh:noSuchProperty"]


def lose_declaration(d: dict) -> None:
    # What the stanza reader did before it joined blocks: kept only the last one.
    ttl = d["datatypes"]["ksh:yesBidDollars"]["ttl"]
    d["datatypes"]["ksh:yesBidDollars"]["ttl"] = ttl.split("\n\n")[-1]


def drop_row(d: dict) -> None:
    d["tree"] = [r for r in d["tree"] if r["id"] != "wx:SnowDepth"]


def drop_second_listing(d: dict) -> None:
    d["tree"] = [r for r in d["tree"] if not r["dup"]]


def misdepth(d: dict) -> None:
    next(r for r in d["tree"] if r["id"] == "wx:SnowDepth")["d"] += 1


def second_root(d: dict) -> None:
    next(r for r in d["tree"] if r["id"] == "wx:SnowDepth")["via"] = None


def question_without_lens(d: dict) -> None:
    d["lenses"] = [ln for ln in d["lenses"] if ln["id"] != "cq02-probability-gap"]


def stale_question(d: dict) -> None:
    next(ln for ln in d["lenses"] if ln["id"].startswith("cq"))["stale"] = ["ksh:yesBidCents"]


def unplaced_class(d: dict) -> None:
    node(d, "wx:AirMotion")["coverage"] = {"state": None}


def coverage_disagrees(d: dict) -> None:
    next(ln for ln in d["lenses"] if ln["id"] == "coverage")["named"].append("wx:AirMotion")


def drop_disjoint(d: dict) -> None:
    for cid in ("ksh:YesContract", "ksh:NoContract"):
        node(d, cid)["disjoint"] = [x for x in node(d, cid)["disjoint"]
                                    if x not in ("ksh:YesContract", "ksh:NoContract")]


def no_orphans(d: dict) -> None:
    # The goal state for this lens, and so a pass rather than "lights nothing".
    next(ln for ln in d["lenses"] if ln["id"] == "unrelated")["named"] = []


def off_its_row(d: dict) -> None:
    node(d, "ksh:Market")["py"] += 40


def reverse_family(d: dict) -> None:
    # fm:Agent's two children in the other order: the smallest reordering that
    # breaches the ceiling, through place() rather than by moving dots by hand.
    rows = d["tree"]
    i = next(k for k, r in enumerate(rows) if r["id"] == "fm:Agent" and not r["dup"])

    def end(k: int) -> int:
        j = k + 1
        while j < len(rows) and rows[j]["d"] > rows[k]["d"]:
            j += 1
        return j

    stop, blocks, k = end(i), [], i + 1
    while k < stop:
        blocks.append(rows[k:end(k)])
        k = end(k)
    d["tree"] = rows[:i + 1] + [r for b in reversed(blocks) for r in b] + rows[stop:]
    gd.place(d["tree"], {n["id"]: n for n in d["nodes"]})


def drift(d: dict) -> None:
    # Along its row and past no edge: only a comparison with a fresh build sees it.
    node(d, "ksh:Market")["px"] += 0.5


def drop_unwalked(d: dict) -> None:
    next(ln for ln in d["lenses"] if ln["id"] == "no-question")["unwalked"].pop()


def name_like_a_module(d: dict) -> None:
    d["outline"] = d.pop("tree")


def drop_bridge(d: dict) -> None:
    d["edges"] = [e for e in d["edges"] if (e["s"], e["t"]) != ("prov:Entity", "bfo:BFO_0000002")]


def forget_prov(d: dict) -> None:
    # Rebuilt without it, so the IRI leaves the page data too; main() restores NS.
    del gd.NS["http://www.w3.org/ns/prov#"]
    d.clear()
    d.update(gd.build())


def unmentioned_import(d: dict) -> None:
    # Imported and asserted under prov:Agent there, but no minted file mentions it.
    d["nodes"].append({**node(d, "prov:Agent"), "id": "prov:SoftwareAgent", "label": "SoftwareAgent"})
    d["edges"].append({"s": "prov:SoftwareAgent", "t": "prov:Agent", "k": "sub"})


def unnamed_source(d: dict) -> None:
    del d["external"]["prov"]


def drop_super(d: dict) -> None:
    d["properties"]["fm:hasInput"]["supers"] = []


def export(d: dict) -> dict:
    return next(ln for ln in d["lenses"] if ln["id"] == "export")


def emptied(key: str) -> Callable[[dict], None]:
    def damage(d: dict) -> None:
        ln = next(x for x in d["lenses"] if x["id"] == key)
        ln.update(named=[], reached=[], paths=[])
    return damage


def lens_off_the_map(d: dict) -> None:
    export(d)["named"].append("fm:NoSuchClass")


def lens_reach_drift(d: dict) -> None:
    export(d)["reached"] = []


def lens_named_and_reached(d: dict) -> None:
    export(d)["reached"].append(export(d)["named"][0])


def lens_path_not_a_property(d: dict) -> None:
    export(d)["paths"].append("ksh:Market")


CASES: list[tuple[str, Callable[[dict], None], str]] = [
    ("a change note dropped on the way to the panel", drop_history,
     "change/history notes not carried to the panel"),
    ("an API field name dropped", drop_field, "API field names on the map's terms"),
    ("a tombstone missing from the search index", drop_tombstone,
     "tombstones not indexed for search"),
    ("a tombstone whose replacement is not on the map", strand_tombstone,
     "retired term resolves to nothing on the map"),
    ("a stanza holding only its field-name block", lose_declaration,
     "stanza lost its declaration"),
    ("a class missing from the outline", drop_row, "not in the outline: ['wx:SnowDepth']"),
    ("a second parent's listing dropped", drop_second_listing, "subClassOf with no outline row"),
    ("an outline row at the wrong depth", misdepth, "wx:SnowDepth under"),
    ("an outline with a second root", second_root, "outline roots are"),
    ("a lens naming a class the map lacks", lens_off_the_map,
     "ThermalEdge export term absent from the map: ['fm:NoSuchClass']"),
    ("a lens whose reached classes drift from its paths", lens_reach_drift,
     "reached classes are not the ends of the paths it walks"),
    ("a lens class both named and reached", lens_named_and_reached,
     "tagged as named and reached at once"),
    ("a lens path that is a class", lens_path_not_a_property,
     "path is neither an object nor a datatype property"),
    ("a competency question with no lens", question_without_lens,
     "competency questions without a lens: ['cq02-probability-gap']"),
    ("a question lens flagged stale", stale_question,
     "matches on a retired or undeclared term"),
    ("a minted class with no coverage state", unplaced_class,
     "minted class with no example-coverage state: ['wx:AirMotion']"),
    ("the coverage lens lighting an unexercised class", coverage_disagrees,
     "the coverage lens and the panel's coverage states disagree"),
    ("a disjointness pair dropped from the panel", drop_disjoint,
     "disjoint pairs not carried to the panel"),
    ("an ontology with no unrelated classes", no_orphans, ""),
    ("a class drawn off its depth's row", off_its_row, "not on its depth's row: ['ksh:Market']"),
    ("one family's children in reverse order", reverse_family,
     "subClassOf crossings, over the pinned"),
    ("a layout that differs from a fresh build", drift, "layout differs from a build"),
    ("a property no question walks left unlisted", drop_unwalked,
     "properties no question walks not listed"),
    ("a data key named like a viz module", name_like_a_module,
     "data key shares a name with a viz module: ['outline']"),
    ("a bridge edge dropped", drop_bridge,
     "subClassOf asserted in a minted file but not drawn: ['http://www.w3.org/ns/prov#Entity"),
    ("prov missing from the namespaces the map names", forget_prov,
     "no prefix the map can name: ['http://www.w3.org/ns/prov#"),
    ("an imported class no minted file mentions, drawn", unmentioned_import,
     "node set is not the minted classes"),
    ("a borrowed prefix with no display name", unnamed_source,
     "borrowed prefix with no display name in the page data: ['prov']"),
    ("a borrowed super-property dropped from the panel", drop_super,
     "super-properties outside FMO not carried to the panel"),
]


def hit_cases() -> int:
    """hit_px() reads what the check compares; prove it reads a shrink and an absence."""
    js = (gd.VIZ / "src" / "graph.js").read_text(encoding="utf-8")
    failed = 0
    for name, text, ok in [
        ("graph.js's hit reach as shipped", js, True),
        ("a hit reach shrunk to the dot", js.replace("var HIT_PX = 12;", "var HIT_PX = 4;"), False),
        ("a hit test with no declared reach", js.replace("var HIT_PX", "var REACH"), False),
    ]:
        v = gd.hit_px(text)
        passes = v is not None and v >= gd.MIN_HIT_PX
        bad = passes != ok
        print(("FAIL  " if bad else "ok    ") + name + (f": read {v}" if bad else ""))
        failed += bad
    return failed


def question_cases() -> int:
    """question_lenses() reads queries off disk, so these run it on a copied set:
    a query matching on a retired term is stale; one only *mentioning* it in a
    comment is not, because terms come from the parsed algebra, not the text."""
    import shutil
    import tempfile
    from rdflib import Graph

    g = Graph()
    for m in gd.MODULES:
        g.parse(gd.SRC / m, format="turtle")
    base = gd.build()
    classes = {n["id"] for n in base["nodes"]}
    props = set(base["properties"]) | set(base["datatypes"])
    head = "# CQ99. A question for the test.\n#\n"
    failed = 0
    real = gd.QUERIES
    for name, body, expect in [
        ("a query matching on a retired term", head +
         "SELECT ?q WHERE { ?q ksh:yesBidCents ?v }\n", ["ksh:yesBidCents"]),
        ("a retired term named only in a comment", head +
         "# was ksh:yesBidCents before 0.19.0\nSELECT ?q WHERE { ?q ksh:yesBidDollars ?v }\n", []),
    ]:
        with tempfile.TemporaryDirectory() as tmp:
            q = Path(tmp)
            shutil.copy(real / "prefixes.txt", q / "prefixes.txt")
            (q / "cq99-test.rq").write_text(body, encoding="utf-8")
            gd.QUERIES = q
            try:
                ln = gd.question_lenses(g, classes, props, base["edges"])[0]
            finally:
                gd.QUERIES = real
        bad = ln.get("stale") != expect
        print(("FAIL  " if bad else "ok    ") + name + (f": stale {ln.get('stale')}" if bad else ""))
        failed += bad
    return failed


def lens_cases(base: dict) -> list[tuple[str, Callable[[dict], None], str]]:
    """Every lens that is not goal-empty, emptied: each must fail on its own."""
    return [(f"the {ln['label']} lens emptied", emptied(ln["id"]),
             f"the {ln['label']} lens lights nothing")
            for ln in base["lenses"] if not ln.get("goal_empty")]


def main() -> int:
    base = gd.build()
    html = gd.inline((gd.VIZ / "index.html").read_text(encoding="utf-8"))
    failed = 0
    try:
        gd.check(copy.deepcopy(base), html)
        print("ok    unmodified data passes")
    except AssertionError as e:
        print(f"FAIL  the unmodified data does not pass: {e}")
        failed += 1
    cases = CASES + lens_cases(base)
    ns = dict(gd.NS)
    for name, damage, expect in cases:
        data = copy.deepcopy(base)
        damage(data)
        # An empty expectation is a case that must pass: a goal state, not a defect.
        try:
            gd.check(data, html)
            why: str | None = f"expected {expect!r}, got a pass" if expect else None
        except AssertionError as e:
            why = None if expect and expect in str(e) else f"expected {expect or 'a pass'!r}, got {e}"
        finally:
            gd.NS.clear()
            gd.NS.update(ns)
        print(("FAIL  " if why else "ok    ") + name + (f": {why}" if why else ""))
        failed += bool(why)
    hit_failed = hit_cases() + question_cases()
    total = len(cases) + 1 + 3 + 2
    failed += hit_failed
    print(f"\n{total - failed}/{total} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
