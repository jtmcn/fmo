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


def name_like_a_module(d: dict) -> None:
    d["outline"] = d.pop("tree")


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
    ("a data key named like a viz module", name_like_a_module,
     "data key shares a name with a viz module: ['outline']"),
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
    for name, damage, expect in CASES:
        data = copy.deepcopy(base)
        damage(data)
        try:
            gd.check(data, html)
            why: str | None = f"expected {expect!r}, got a pass"
        except AssertionError as e:
            why = None if expect in str(e) else f"expected {expect!r}, got {e}"
        print(("FAIL  " if why else "ok    ") + name + (f": {why}" if why else ""))
        failed += bool(why)
    hit_failed = hit_cases()
    total = len(CASES) + 1 + 3
    failed += hit_failed
    print(f"\n{total - failed}/{total} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
