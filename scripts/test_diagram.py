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
]


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
    print(f"\n{len(CASES) + 1 - failed}/{len(CASES) + 1} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
