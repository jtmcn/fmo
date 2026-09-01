#!/usr/bin/env python3
"""The set arithmetic every checked-in ledger needs, in one place.

A ledger records, per item, why something is not proved the usual way. Three
exist -- queries/axiom-expectations.json, queries/class-coverage-expectations.json
and queries/production-expectations.json -- and each grew its own copy of the same
invariants. The copies drifted: production-expectations checked that every query
had an entry and never that every entry had a query, so a stale exemption sat
there reading as a decision about today's query set.

CONTEXT.md already stated the rule for all three, and the third was written
without it. A rule enforced by memory is enforced wherever someone remembered,
which is this repo's argument for a check over a paragraph.

The three files do NOT share a shape, and this does not pretend otherwise:

    axiom-expectations           category -> name -> string
    class-coverage-expectations  category -> name -> object
    production-expectations      name -> object, the category implicit in
                                 which key the entry sets

Each caller flattens its own file into Entry rows. That normaliser is the adapter,
a few lines apiece, and it is where the shape differences belong.

audit() returns FINDINGS, not messages. Wording is domain knowledge and this repo
spends it deliberately -- "unexercised and not classified" says something
"item in no category" does not, and a shared kernel that owned the text would make
every message worse to make one function tidier. The arithmetic is what was
duplicated; the sentences were not.

What also stays at the call site is per-entry verification: check_axioms deletes
the axiom and re-runs the reasoner, check_class_coverage reads a skos:scopeNote
and parses a date, run_competency type-checks min_rows. ADR-0001 makes that
asymmetry deliberate -- "the four reasons are not equally verifiable" -- so
nothing here tries to unify it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, NamedTuple

# Every way a ledger can be wrong about its population. Each call site renders the
# kinds it can produce; KINDS is what the ledger cases in test_validate.py assert
# they have all exercised, so a new kind arrives with a test rather than silently.
EMPTY_POPULATION = "empty-population"
DUPLICATE = "duplicate"
UNCOVERED = "uncovered"
STALE_UNKNOWN = "stale-unknown"
STALE_LEFT = "stale-left"
BLANK_REASON = "blank-reason"

KINDS = (EMPTY_POPULATION, DUPLICATE, UNCOVERED, STALE_UNKNOWN, STALE_LEFT, BLANK_REASON)


class Entry(NamedTuple):
    """One ledger row, flattened out of whatever shape its file happens to have.

    `value` is whatever the file puts beside the name, and it is NOT always a
    reason: axiom-expectations' `pinned` values are case names, so a blank one
    means "pinned by a case that does not exist" rather than "no reason given".
    Calling this field `reason` is what let BLANK_REASON be rendered as
    "exempt with no reason given" for an entry that is pinned. audit() is
    category-blind on purpose, so the caller decides what a blank value means for
    each of its categories.
    """

    name: str
    category: str
    value: str


class Finding(NamedTuple):
    """One thing wrong with a ledger. What the last two fields hold depends on kind:

      kind      what is wrong, from KINDS
      name      the item, blank only for EMPTY_POPULATION
      category  the row's category; for DUPLICATE, the SECOND one seen
      other     the FIRST category seen, and only for DUPLICATE

    The order matters where it is rendered -- "in {other} and {category}" reads as
    the order the file lists them -- and a caller that swapped them would produce a
    sentence that is wrong in a way no test would catch.
    """

    kind: str
    name: str = ""
    category: str = ""
    other: str = ""


class LedgerError(Exception):
    """A ledger that cannot be read. An Exception, not SystemExit, so validate.py's
    per-check handler records it as one check's failure and the rest still run."""


def load(path: Path, categories: Iterable[str] | None = None) -> dict:
    """Read a ledger, dropping exactly the `_comment` header.

    Exactly `_comment`, not every key starting with an underscore. Stripping the
    whole prefix looks like tidier de-duplication and is a widening: it hides an
    unrecognised category from the `categories` guard below, and that guard exists
    because entries parked under a key nothing reads escape both staleness checks
    while reading as authoritative. A block named `_schema-instantiated` would have
    been invisible, one underscore wide.

    `categories`, when given, is every top-level key the caller will actually read.
    A key outside it is refused here rather than ignored. This lives in the kernel
    and not at one call site because it is the same hole the underscore widening
    opened: check_class_coverage had the guard and check_axioms did not, so an
    entry parked under `deferred` in axiom-expectations.json passed with OK. A
    caller whose file is not category-keyed -- production-expectations, whose
    categories are implicit in which key an entry sets -- passes nothing.
    """
    if not path.is_file():
        raise LedgerError(f"no ledger at {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LedgerError(f"ledger at {path} is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise LedgerError(f"ledger at {path} is not a JSON object")
    out = {k: v for k, v in raw.items() if k != "_comment"}
    if categories is not None:
        unknown = sorted(set(out) - set(categories))
        if unknown:
            raise LedgerError(
                f"ledger at {path.name} has categories nothing reads: "
                f"{', '.join(unknown)} -- entries parked under one escape both "
                f"staleness guards while reading as authoritative")
    return out


def audit(
    population: Iterable[str],
    entries: Iterable[Entry],
    *,
    handles: Iterable[str],
    universe: Iterable[str] | None = None,
) -> list[Finding]:
    """Check a ledger's rows against the population they claim to classify.

      EMPTY_POPULATION  nothing to classify, so the check verified nothing
      DUPLICATE         one item in two categories; only one reason is the real one
      UNCOVERED         an item in the population that no row classifies
      STALE_UNKNOWN     a row naming something that does not exist at all
      STALE_LEFT        a row naming something that has left the population
      BLANK_REASON      a row whose reason is empty

    `entries` is a sequence, never a mapping: a dict keyed by name would collapse
    the duplicate DUPLICATE exists to find.

    `universe` splits staleness in two where the population is itself filtered.
    check_class_coverage's population is the UNEXERCISED minted classes, so a row
    goes stale two ways -- naming a class that no longer exists, or naming one an
    example has since started exercising -- and the second is the ledger shrinking
    as intended, which is a different sentence. Callers whose population is the
    whole set pass nothing and get STALE_UNKNOWN for both.

    `handles` names every kind the caller has DECIDED about -- rendered here, or
    rendered elsewhere, or deliberately ignored. Producing one outside it raises,
    because the alternative is an `elif` that is simply absent: the finding is
    computed, dropped, and the run reports OK. That is the shape of the defect
    this kernel was extracted to stop, so it must not be reachable through the
    kernel itself, and it is how a seventh KIND forces every call site to look.
    """
    unknown = sorted(set(handles) - set(KINDS))
    if unknown:
        raise LedgerError(f"audit() asked to handle unknown kind(s): {', '.join(unknown)}")
    rows = list(entries)
    pop = set(population)
    out: list[Finding] = []
    # Reported, not returned early: with an empty population every row is stale, and
    # that is worth saying too. No site renders it as a failure, and that is a
    # decision rather than an oversight: check_axioms and run_competency refuse an
    # empty population first, with sentences of their own that say more than this
    # kind can; check_class_coverage reaches it in its GOAL state -- no unexercised
    # class left -- and lists it in `handles` to say so. That listing is the only
    # thing keeping this kind honest, so if it is ever dropped from `handles`
    # everywhere, drop it from KINDS too rather than leaving a finding nothing reads.
    if not pop:
        out.append(Finding(EMPTY_POPULATION))

    seen: dict[str, str] = {}
    for row in rows:
        if row.name in seen and seen[row.name] != row.category:
            out.append(Finding(DUPLICATE, row.name, row.category, seen[row.name]))
        seen.setdefault(row.name, row.category)

    out += [Finding(UNCOVERED, name) for name in sorted(pop - set(seen))]

    known = set(universe) if universe is not None else None
    for name in sorted(set(seen) - pop):
        left = known is not None and name in known
        out.append(Finding(STALE_LEFT if left else STALE_UNKNOWN, name, seen[name]))

    # Only for rows that are still live. A stale row's reason is beside the point,
    # and reporting both would say twice that one entry is wrong.
    out += [Finding(BLANK_REASON, row.name, row.category)
            for row in rows
            if row.name in pop and not str(row.value).strip()]

    undecided = sorted({f.kind for f in out} - set(handles))
    if undecided:
        raise LedgerError(
            f"audit() produced {', '.join(undecided)} and the caller says nothing "
            f"about that kind, so the finding would be computed and dropped")
    return out
