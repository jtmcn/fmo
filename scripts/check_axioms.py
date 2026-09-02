#!/usr/bin/env python3
"""Every axiom is pinned by a reasoner case, or exempt with a stated reason.

The ontology asserts axioms; the prose says what they guarantee; the tests prove
some of them. Nothing tied those three together, and the gap showed twice in one
afternoon: an AllDisjointClasses block whose deletion left the whole suite green,
and a union axiom whose test named a mistake the axiom does not catch. Both read
as guarantees. Neither was one.

So the axioms get the treatment MODULES gets in registry.py, and shapes get in
test_shapes.py: enumerate the real set, compare it against a checked-in ledger,
and fail on anything the ledger does not account for. Adding an axiom now fails
the build until someone either writes a case for it or records why it has none.

Two properties are checked, and the second is the one that matters:

1. Completeness -- every site in scripts/axioms.py is in the ledger, and every
   ledger entry names a site that still exists. A stale exemption is as bad as a
   missing one: it reads as a decision someone made about today's ontology.
2. Pinning -- for each axiom the ledger claims a case proves, delete that axiom
   and confirm the case stops firing. Without this the ledger is prose again,
   asserting a relationship nothing verifies. That is the whole failure being
   fixed, so the fix does not get to repeat it.

    poetry run python3 scripts/check_axioms.py             # verify
    poetry run python3 scripts/check_axioms.py --discover  # re-derive the ledger

--discover removes each axiom in turn and runs every case against the result, so
it reports which axioms are load-bearing rather than which ones someone believed
were. It is slow (a reasoner run per trial) and writes nothing; the ledger is
edited by hand from what it prints, because the reasons are the point.

Skips with a notice when ROBOT or Java is missing or does not run -- unlike
`make reason`, whose detection is still presence-based, so a stub java makes it
fail rather than skip.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import axioms  # noqa: E402
import ledger as L  # noqa: E402
import test_reason as T  # noqa: E402
from registry import ROOT, SRC  # noqa: E402

LEDGER = ROOT / "queries" / "axiom-expectations.json"


# The two blocks verify() reads. Anything else in the file is refused by load():
# an entry parked under a third key escaped both staleness guards and passed with
# OK, which is the check_class_coverage guard this file never had.
CATEGORIES = ("pinned", "exempt")


def case_by_name(name: str) -> tuple | None:
    return next((c for c in T.CASES if c[0] == name), None)


class ReasonerSilent(RuntimeError):
    """The reasoner returned no verdict, so nothing follows about the axiom."""


def fires_without(robot: list[str], key: str, case: tuple) -> bool:
    """Does `case` still fire when `key` is deleted? False means it was pinned.

    The deletion happens inside run_case, after the case's own text mutation, so a
    reserialised module cannot strand the anchor. run_case raises on a setup failure
    rather than returning False, which keeps "the case broke" out of the answer to
    "the case stopped firing" -- conflating those was what made the first version of
    this probe report 53 of 68 axioms load-bearing, nearly all of them spuriously.

    A run that returned no verdict is the same conflation one layer down, and it was
    still here: T.UNREADABLE used to arrive as False, i.e. as "the case stopped
    firing", i.e. as a verified pin. With no JVM every case was unreadable and every
    pin "held" -- 9 of 9 verified, exit 0, output identical to a real run. It raises
    now, because the honest answer to "did the case fire?" is that we do not know.
    """
    outcome = T.run_case(robot, *case, drop_axiom=key, quiet=True)
    if outcome == T.UNREADABLE:
        raise ReasonerSilent(
            f"the reasoner gave no verdict on {case[0]!r} with {key} deleted, so "
            f"whether that axiom is load-bearing is unknown and nothing here is "
            f"verified. Check that ROBOT and the JVM work: `make reason`.")
    return outcome == T.FIRED


def _probe(args: tuple) -> tuple[str, str | None]:
    """One axiom against every case; returns the first case it turns out to pin."""
    key, robot = args
    for case in T.CASES:
        if not fires_without(robot, key, case):
            return key, case[0]
    return key, None


def discover(robot: list[str]) -> int:
    sites = sorted(axioms.all_sites())
    print(f"probing {len(sites)} axiom sites against {len(T.CASES)} cases "
          f"({len(sites) * len(T.CASES)} trials, worst case)\n")
    pinned: dict[str, str] = {}
    with ProcessPoolExecutor() as pool:
        for key, case_name in pool.map(_probe, [(k, robot) for k in sites]):
            if case_name:
                pinned[key] = case_name
                print(f"  PINNED   {key}\n           by: {case_name}")
    print(f"\n{len(pinned)} of {len(sites)} axioms are load-bearing for the suite; "
          f"{len(sites) - len(pinned)} are asserted but untested.")
    print("\nSuggested ledger 'pinned' block:")
    print(json.dumps(pinned, indent=2, sort_keys=True))
    return 0


def verify(robot: list[str]) -> int:
    try:
        ledger = L.load(LEDGER, CATEGORIES)
    except L.LedgerError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    pinned, exempt = ledger.get("pinned", {}), ledger.get("exempt", {})
    sites = axioms.all_sites()
    failures: list[str] = []

    if not sites:
        print("FAIL: enumerated no axiom sites, so this check verified nothing",
              file=sys.stderr)
        return 1
    if not pinned:
        # A ledger that exempts everything passes every other assertion here while
        # proving nothing about any axiom, which is the failure this file exists for
        # wearing the file's own clothes.
        print("FAIL: no axiom is pinned, so the ledger asserts nothing about any of them",
              file=sys.stderr)
        return 1

    # The shared set arithmetic; only the sentences are ours. audit() is
    # category-blind and these two categories are not symmetric: `pinned` values are
    # case names, so a blank one is "pinned by a case that does not exist", reported
    # below. Rendering BLANK_REASON only for `exempt` keeps that, as at base.
    rows = ([L.Entry(key, "pinned", str(name)) for key, name in pinned.items()]
            + [L.Entry(key, "exempt", str(reason)) for key, reason in exempt.items()])
    # No universe, so staleness is one kind here; EMPTY_POPULATION cannot arrive,
    # since an empty `sites` is refused above with its own sentence.
    for f in L.audit(sites, rows,
                     handles=(L.DUPLICATE, L.UNCOVERED, L.STALE_UNKNOWN, L.BLANK_REASON)):
        if f.kind == L.DUPLICATE:
            failures.append(
                f"in both pinned and exempt, so the ledger does not say which: {f.name}")
        elif f.kind == L.UNCOVERED:
            failures.append(
                f"axiom in neither pinned nor exempt: {f.name}\n"
                f"      write a case for it, or record in {LEDGER.name} why it has none"
            )
        elif f.kind == L.STALE_UNKNOWN:
            failures.append(
                f"ledger names an axiom that no longer exists: {f.name}\n"
                f"      it reads as a decision about today's ontology, and is not one"
            )
        elif f.kind == L.BLANK_REASON and f.category == "exempt":
            failures.append(f"exempt with no reason given: {f.name}")

    # The claim that a case proves an axiom is itself checked, or the ledger is
    # prose asserting a relationship nothing verifies -- the bug this file exists for.
    verified = 0
    for key, name in sorted(pinned.items()):
        case = case_by_name(name)
        if case is None:
            failures.append(f"pinned by a case that does not exist: {key}\n      names: {name}")
            continue
        if key not in sites:
            continue
        try:
            still_fires = fires_without(robot, key, case)
        except ReasonerSilent as exc:
            # Fatal rather than one more failure line: a reasoner that cannot answer
            # for one axiom is not answering for any of them, and every remaining
            # `verified` would be the same false green in miniature. The ledger
            # findings already in hand are reasoner-independent, so they go out too
            # rather than waiting for a second run after the JVM is fixed.
            for f in failures:
                print(f"  {f}", file=sys.stderr)
            print(f"FAIL: {exc}", file=sys.stderr)
            return 1
        if still_fires:
            failures.append(
                f"claims to be pinned but is not: {key}\n"
                f"      deleting it leaves '{name}' still firing, so nothing here "
                f"proves the axiom does anything"
            )
        else:
            verified += 1
            print(f"  ok   {key}\n       pinned by: {name}")

    print(f"\n{len(sites)} axiom sites: {len(pinned)} pinned ({verified} verified), "
          f"{len(exempt)} exempt")
    if failures:
        print(f"\nFAILED ({len(failures)}):", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print("OK")
    return 0


def main() -> int:
    try:
        robot, why = T.robot_command()
    except T.ReasonerBroken as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    if robot is None:
        print(f"SKIP check_axioms: {why}")
        return 0
    if "--discover" in sys.argv:
        return discover(robot)
    return verify(robot)


if __name__ == "__main__":
    raise SystemExit(main())
