#!/usr/bin/env python3
"""Run the competency questions in queries/ and compare against checked-in results.

A competency question is a requirement, so it needs a pass/fail, not a printout.
Each queries/cqNN-*.rq is executed against the modules plus the example data and
its result compared to the matching .expected file.

Two rules that keep this honest:

  * An empty result set FAILS. A query that matches nothing is the most common way
    for a broken competency check to look like a passing one.
  * Expected files are compared exactly, after canonicalising IRIs to prefixed
    names and sorting rows. Changing an answer means changing the checked-in
    expectation, visibly, in a diff.

Usage:
    python3 scripts/run_competency.py            # check against examples/
    python3 scripts/run_competency.py --update   # regenerate .expected files
    python3 scripts/run_competency.py --data <file.ttl>  # production mode: check
        one export against queries/production-expectations.json instead of
        examples/ + .expected
    python3 scripts/run_competency.py --exports    # production mode over every
        examples/export/ fixture; all must pass
    python3 scripts/run_competency.py --negatives  # production mode over every
        examples/negative/ fixture; each must be rejected by some query
"""

from __future__ import annotations

import sys
from pathlib import Path

from rdflib import Graph, Literal, URIRef

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger as L  # noqa: E402
from registry import IRI_TO_PREFIX, MODULES, QUERIES, SRC, examples, exports, negatives  # noqa: E402


def shorten(term) -> str:
    """Canonical, diff-friendly rendering of one binding."""
    if term is None:
        return "-"
    if isinstance(term, URIRef):
        s = str(term)
        for full, short in IRI_TO_PREFIX.items():
            if s.startswith(full):
                return short + s[len(full):]
        return f"<{s}>"
    if isinstance(term, Literal):
        # Drop the datatype for readability but keep the lexical form exactly,
        # so 0.60 and 0.6 do not silently compare equal.
        return str(term)
    return str(term)


def load_graph(data: Path | None = None) -> Graph:
    """Modules plus instance data: the checked-in examples, or one export."""
    g = Graph()
    for rel in MODULES:
        g.parse(SRC / rel, format="turtle")
    if data is not None:
        g.parse(data, format="turtle")
        return g
    paths = examples()
    if not paths:
        print("no example files found; competency questions need instance data", file=sys.stderr)
        raise SystemExit(1)
    for path in paths:
        g.parse(path, format="turtle")
    return g


def load_production_expectations() -> dict:
    return L.load(QUERIES / "production-expectations.json")


def expectation_rows(expectations: dict) -> list[L.Entry]:
    """Flatten into ledger rows. The category is implicit in which key is set --
    this file is the one of the three that is not shaped category -> name."""
    # A non-dict entry keeps its row rather than raising here: the per-query chain
    # below is what reports a malformed entry, and with the message that names it.
    return [
        L.Entry(stem,
                "may_be_empty" if isinstance(rule, dict) and rule.get("may_be_empty")
                else "min_rows",
                rule.get("why", "") if isinstance(rule, dict) else "")
        for stem, rule in expectations.items()
    ]


def render(results) -> str:
    """Serialize a SPARQL result as sorted TSV with a header row."""
    cols = [str(v) for v in results.vars]
    rows = ["\t".join(cols)]
    body = ["\t".join(shorten(row[v]) for v in results.vars) for row in results]
    rows.extend(sorted(body))
    return "\n".join(rows) + "\n"


def main() -> int:
    update = "--update" in sys.argv
    data = None
    if "--data" in sys.argv:
        i = sys.argv.index("--data")
        if i + 1 >= len(sys.argv):
            sys.exit("--data needs a file")
        data = Path(sys.argv[i + 1])
        if update:
            print("--update and --data are mutually exclusive", file=sys.stderr)
            return 1

    prefixes = (QUERIES / "prefixes.txt").read_text()
    graph = load_graph(data)
    # LedgerError is typed so this can be a verdict. check_axioms catches it and
    # check_class_coverage gets it through validate.py's per-check handler; this was
    # the one site still answering a missing or malformed ledger with a traceback.
    try:
        expectations = load_production_expectations() if data else {}
    except L.LedgerError as exc:
        print(f"  FAIL [production-expectations.json]: {exc}", file=sys.stderr)
        return 1

    query_files = sorted(QUERIES.glob("cq*.rq"))
    if not query_files:
        print("no queries found in queries/", file=sys.stderr)
        return 1

    failures = 0
    # Counted apart from query failures: a stale ledger entry is not a question
    # answering wrongly, and folding it in made the summary say "7/8 competency
    # questions answered as expected" when all 8 were and the JSON file was the
    # problem. Same confusion the message below is worded to avoid.
    config_failures = 0
    # UNCOVERED is rendered per query below, where the row count is in hand, so only
    # staleness is read here. That direction is the one this ledger did not have.
    if data is not None:
        # UNCOVERED and BLANK_REASON are decided about, not ignored: the per-query
        # chain below renders both, where the row count and the entry's shape are in
        # hand. Naming them here is what stops a kind being dropped by a missing elif.
        for f in L.audit({qf.stem for qf in query_files}, expectation_rows(expectations),
                         handles=(L.STALE_UNKNOWN, L.UNCOVERED, L.BLANK_REASON)):
            if f.kind == L.STALE_UNKNOWN:
                # Named for the file, not the query: there IS no such query, and a
                # "FAIL [cq...]" line would be counted as a rejection by the
                # --negatives sweep, which reads config breakage as a fixture verdict.
                print(f"  FAIL [production-expectations.json]: names a query that "
                      f"does not exist: {f.name}")
                config_failures += 1
            # BLANK_REASON is deliberately not rendered here: the per-query chain
            # below reports it after the shape checks, so a malformed entry names
            # its real problem rather than a missing 'why' it also has.
    for qf in query_files:
        expected_file = qf.with_suffix(".expected")
        try:
            results = graph.query(prefixes + "\n" + qf.read_text())
        except Exception as exc:  # noqa: BLE001
            print(f"  FAIL [{qf.name}]: query error: {exc}")
            failures += 1
            continue

        actual = render(results)
        row_count = len(actual.strip().splitlines()) - 1

        if data is not None:
            rule = expectations.get(qf.stem)
            if rule is None:
                # No declared expectation is a failure, not a skip. Relaxing
                # this globally is how the check stops working while still
                # appearing to run.
                print(f"  FAIL [{qf.name}]: no entry in production-expectations.json")
                failures += 1
                continue
            # A malformed entry is a failure, not a crash and not a silent pass.
            # Checking key PRESENCE was not enough: {"may_be_empty": false} has the
            # key, passes an XOR on presence, then falls through to rule["min_rows"]
            # and raises KeyError mid-run with the remaining queries never executed.
            # A string "1" got a TypeError the same way. Check the values.
            exempt = rule.get("may_be_empty")
            floor = rule.get("min_rows")
            if exempt is not None and not isinstance(exempt, bool):
                bad = f"may_be_empty must be true or false, got {exempt!r}"
            elif floor is not None and not isinstance(floor, int) or isinstance(floor, bool):
                bad = f"min_rows must be an integer, got {floor!r}"
            elif bool(exempt) == (floor is not None):
                bad = "entry must set exactly one of may_be_empty: true or min_rows"
            elif not rule.get("why"):
                bad = "entry has no 'why'"
            else:
                bad = ""
            if bad:
                print(f"  FAIL [{qf.name}]: {bad}")
                failures += 1
                continue
            if rule.get("may_be_empty"):
                print(f"  ok   [{qf.name}]: {row_count} row(s), may be empty ({rule['why']})")
                continue
            minimum = rule["min_rows"]
            if row_count < minimum:
                print(f"  FAIL [{qf.name}]: {row_count} row(s), expected at least {minimum} — {rule['why']}")
                failures += 1
                continue
            print(f"  ok   [{qf.name}]: {row_count} row(s)")
            continue

        # An empty result is a failure, not a pass. This is the trap that makes
        # unverified competency claims look fine.
        if row_count == 0:
            print(f"  FAIL [{qf.name}]: returned 0 rows; the question is not answerable")
            failures += 1
            continue

        if update:
            expected_file.write_text(actual)
            print(f"  updated [{qf.name}]: {row_count} row(s)")
            continue

        if not expected_file.exists():
            print(f"  FAIL [{qf.name}]: no {expected_file.name}; run with --update and review it")
            failures += 1
            continue

        expected = expected_file.read_text()
        if actual != expected:
            print(f"  FAIL [{qf.name}]: result differs from {expected_file.name}")
            for line in _diff(expected, actual):
                print(f"         {line}")
            failures += 1
        else:
            print(f"  ok   [{qf.name}]: {row_count} row(s)")

    if update:
        print("\nexpected files regenerated -- review the diff before committing")
        # Non-zero when a query errored or returned nothing: those skip the write
        # above, so their old .expected survives and `make cq-update` would
        # otherwise report success and produce no diff for the one broken query.
        if failures:
            print(f"{failures} quer(y/ies) not regenerated -- see the failures above",
                  file=sys.stderr)
        return 1 if failures or config_failures else 0

    total = len(query_files)
    print(f"\n{total - failures}/{total} competency questions answered as expected")
    if config_failures:
        print(f"{config_failures} stale production-expectations entr(y/ies) -- "
              f"a ledger problem, not a query one", file=sys.stderr)
    return 1 if failures or config_failures else 0


def _diff(expected: str, actual: str) -> list[str]:
    import difflib
    return list(difflib.unified_diff(
        expected.splitlines(), actual.splitlines(),
        fromfile="expected", tofile="actual", lineterm="", n=1,
    ))[:20]


if __name__ == "__main__":
    # Every negative fixture must make production mode reject SOMETHING. A fixture
    # nothing rejects is not a negative fixture, and one added but silently never
    # run is how examples/negative/ went unexercised for a release. WHICH query
    # must fail is asserted in the Makefile, since a generic rejection would hide
    # a lost cq02 floor behind the mismatch fixture's unrelated cq04 failure.
    if "--exports" in sys.argv or "--negatives" in sys.argv:
        import io
        from contextlib import redirect_stdout
        want_pass = "--exports" in sys.argv
        fixtures = exports() if want_pass else negatives()
        if not fixtures:
            raise SystemExit("no fixtures matched")
        worst = 0
        for path in fixtures:
            print(f"== {path.name}")
            sys.argv = [sys.argv[0], "--data", str(path)]
            # A crash is this fixture's failure, not the sweep's: an unparseable
            # fixture used to abort the whole run with a traceback where a verdict
            # belonged, and every fixture sorting after it went unchecked.
            buf = io.StringIO()
            try:
                with redirect_stdout(buf):
                    code = main()
            except Exception as exc:  # noqa: BLE001
                print(buf.getvalue(), end="")
                print(f"  FAIL [{path.name}]: raised {type(exc).__name__}: {exc}")
                worst = 1
                continue
            out = buf.getvalue()
            print(out, end="")
            # A non-zero exit is not proof of rejection: "no queries found", an
            # unreadable fixture or a renamed script all exit non-zero too. Config
            # breakage is excluded for the same reason -- a missing expectations
            # entry rejects every fixture alike and says nothing about this one.
            rejections = [
                line for line in out.splitlines()
                if "FAIL [cq" in line
                and ": query error:" not in line and ": no entry in" not in line
            ]
            if not want_pass and not rejections:
                print(f"  FAIL [{path.name}]: exited {code} but no query reported a failure")
                worst = 1
                continue
            if want_pass:
                worst = max(worst, code)
            elif code == 0:
                print(f"  FAIL [{path.name}]: production mode accepted a negative fixture")
                worst = 1
            else:
                print(f"  ok   [{path.name}]: rejected")
        raise SystemExit(worst)
    raise SystemExit(main())
