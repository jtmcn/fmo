# Checking-Apparatus Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the repo's checking discipline from prose and hand-written cases into mechanism, so a check that cannot fail is caught by the suite rather than by a human building an adversarial fixture.

**Architecture:** Three stacked PRs. PR 1 is mechanical: one registry module everything imports, prose stops stating apparatus counts, and a crashing check becomes a named failure instead of aborting the run. PR 2 makes each check's coverage count an assertion and adds a meta-test that calls every check with an empty graph. PR 3 adds an in-process shape tester that generates supertype mutants from the class hierarchy.

**Tech Stack:** Python 3.12 + rdflib + pySHACL via poetry, GNU make, Turtle/SHACL. Graphite (`gt`) for the stack.

**Spec:** `docs/superpowers/specs/2026-08-24-checking-apparatus-design.md`

## Global Constraints

- Everything runs through `poetry run`; run commands from the repo root.
- **`make test` must be green at the end of every task**, not just every PR. Each PR in the stack must stand alone.
- **Do NOT touch `src/*.ttl`, `examples/`, or `queries/*.expected`.** This work changes the apparatus, never the ontology or its data. If a change makes an expectation move, stop and report — that means behaviour changed when it should not have.
- **Do NOT bump any version string.** No release in this stack.
- `src/imports/bfo-core.ttl` is vendored, `src/imports/qudt-subset.ttl` is generated — never edit either.
- Inline comments terse, non-obvious "why" only. This repo treats a screenful of prose above a small change as a defect.
- Terminology follows `CONTEXT.md`: "event grouping" never bare "event"; "check" is one assertion in `validate.py`; "negative test" is the injected-defect proof.
- **Never weaken a test to make it pass.** If a new mechanism makes an existing case fail, the case is telling you something.

## Stack mechanics

Three branches, each stacked on the last with graphite:

```bash
gt create joel/checks-foundation      # PR 1, from main
gt create joel/checks-enforcement     # PR 2, on top of PR 1
gt create joel/shape-mutants          # PR 3, on top of PR 2
```

Tasks 1–3 are PR 1, tasks 4–5 are PR 2, task 6 is PR 3. Do not start a later PR's tasks before its parent's are committed.

## One refinement to the spec

The spec places `coverage()` in the registry. Put it in `scripts/validate.py` instead: it must append to that module's `failures` and `notes` lists, and importing those into the registry would make a data module depend on a checker. **The registry stays data-only.** The meta-test in Task 5 reads the log by importing `validate`.

---

# PR 1 — `joel/checks-foundation`

### Task 1: The registry

**Files:**
- Create: `scripts/registry.py`
- Modify: `scripts/validate.py:96-141`, `scripts/run_competency.py:36-56`, `scripts/validate_shapes.py:30`, `scripts/generate_diagram.py:28`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: module `scripts/registry.py` exporting `ROOT: Path`, `SRC: Path`, `QUERIES: Path`, `SHAPES: Path`, `MODULES: list[str]`, `ONTOLOGY_PREFIXES: dict[str,str]`, `EXAMPLE_PREFIXES: dict[str,str]`, `EXTERNAL_PREFIXES: dict[str,str]`, `OUR_NS: tuple[str,...]`, `CONTEXT_PREFIXES: dict[str,str]`, `IRI_TO_PREFIX: dict[str,str]`, `PROSE_FILES: list[Path]`, and the callables `examples() -> list[Path]`, `exports() -> list[Path]`, `negatives() -> list[Path]`.

- [ ] **Step 1: Write the registry**

Create `scripts/registry.py`:

```python
#!/usr/bin/env python3
"""One definition of every path, glob and namespace the checkers share.

Written after rex: was added to validate.py's prefix map and not to
run_competency.py's, which holds the same namespaces inverted. Two maps over one
set of facts drift; one source with derived views cannot.

Data only. Nothing here imports a checker, so every checker can import this.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
QUERIES = ROOT / "queries"
SHAPES = ROOT / "shapes" / "thermaledge-export.ttl"

MODULES = [
    "imports/bfo-core.ttl", "imports/qudt-subset.ttl",
    "core.ttl", "weather.ttl", "kalshi.ttl", "fmo.ttl",
]

ONTOLOGY_PREFIXES = {
    "fm": "https://w3id.org/forecast-market-ontology/core#",
    "wx": "https://w3id.org/forecast-market-ontology/weather#",
    "ksh": "https://w3id.org/forecast-market-ontology/kalshi#",
}

EXAMPLE_PREFIXES = {
    "ex": "https://w3id.org/forecast-market-ontology/examples/kxhighny-2026-08-15#",
    "tex": "https://w3id.org/forecast-market-ontology/examples/kxhighny-2026-08-15-trading#",
    "vex": "https://w3id.org/forecast-market-ontology/examples/verification#",
    "rex": "https://w3id.org/forecast-market-ontology/examples/kxrainnyc-2026-07-15#",
}

EXTERNAL_PREFIXES = {
    "bfo": "http://purl.obolibrary.org/obo/",
    "unit": "http://qudt.org/vocab/unit/",
    "quantitykind": "http://qudt.org/vocab/quantitykind/",
    "qudt": "http://qudt.org/schema/qudt/",
}

OUR_NS = tuple(ONTOLOGY_PREFIXES.values())
CONTEXT_PREFIXES = {**ONTOLOGY_PREFIXES, **EXAMPLE_PREFIXES}

# The inverse view run_competency.py renders with. Derived, never typed twice.
IRI_TO_PREFIX = {
    iri: f"{name}:"
    for name, iri in {
        **ONTOLOGY_PREFIXES, **EXAMPLE_PREFIXES, **EXTERNAL_PREFIXES,
    }.items()
}

# Prose that describes the CURRENT graph. Excluded: docs/superpowers/** (a plan
# names terms that do not exist yet) and docs/fmo-in-thermaledge.md (pinned to
# FMO 0.7.0). Checking either against today's graph fails on correct content.
PROSE_FILES = [
    ROOT / "CONTEXT.md",
    ROOT / "README.md",
    ROOT / "docs" / "design-notes.md",
]


# Globs as functions, not module-level lists: the negative-test harness copies the
# tree and runs the checkers there, so these must resolve against the copy at call
# time rather than snapshot the source tree at import.
def examples() -> list[Path]:
    """Worked data. Loaded together -- the files cross-reference."""
    return sorted((ROOT / "examples").glob("*.ttl"))


def exports() -> list[Path]:
    """Conformant export fixtures. Each is an independent graph; never merged."""
    return sorted((ROOT / "examples" / "export").glob("*.ttl"))


def negatives() -> list[Path]:
    """Fixtures that must be rejected. A negative fixture nothing rejects is not one."""
    return sorted((ROOT / "examples" / "negative").glob("*.ttl"))
```

- [ ] **Step 2: Point `validate.py` at it**

In `scripts/validate.py`, replace the block from `# One source of truth: a new module gets one line here, not three edits that can drift.` through `EXAMPLES = sorted((ROOT / "examples").glob("*.ttl"))` with:

```python
from registry import (  # noqa: E402
    CONTEXT_PREFIXES, EXAMPLE_PREFIXES, MODULES, OUR_NS, ONTOLOGY_PREFIXES as PREFIXES,
    PROSE_FILES, ROOT, SRC, examples,
)

# A term is declared when something types it. A retirement that leaves a tombstone behind
# -- owl:deprecated plus the old label -- is not a declaration, and CONTEXT.md must stop
# naming it rather than keep pointing at a term the model no longer has.
DECLARED_AS = (OWL.Class, OWL.ObjectProperty, OWL.DatatypeProperty, OWL.AnnotationProperty, OWL.NamedIndividual)

CONTEXT = ROOT / "CONTEXT.md"
# Backticked only: prose says "the fm: side" and names files, and neither is a term.
# Struck through (~~`ksh:Event`~~) is exempt: that is how the file spells a name the
# project rejected, which by construction is declared nowhere.
CONTEXT_TERM = re.compile(rf"(?<!~)`({'|'.join(CONTEXT_PREFIXES)}):([A-Za-z][A-Za-z0-9_]*)`(?!~)")
# Globs are patterns, not paths (`queries/cqNN-*.rq` names no file), and build/ is generated.
CONTEXT_PATH = re.compile(r"`((?:src|scripts|queries|docs|examples)/[^`*]*)`")
CONTEXT_MAKE = re.compile(r"`make ([a-z][a-z-]*)`")
CONTEXT_CHECK = re.compile(r"`(check_[a-z_]+)`")

EXAMPLES = examples()
```

`validate.py` must already have `sys.path` pointing at its own directory for this import to work. If it does not, add above the import:

```python
sys.path.insert(0, str(Path(__file__).resolve().parent))
```

Delete the now-unused `ROOT = ...` and `SRC = ...` assignments in `validate.py` — they come from the registry.

- [ ] **Step 3: Point `run_competency.py` at it, deriving the inverse map**

In `scripts/run_competency.py`, delete its `MODULES` list and its `PREFIXES` dict (lines 36–56) and replace with:

```python
sys.path.insert(0, str(Path(__file__).resolve().parent))
from registry import IRI_TO_PREFIX, MODULES, QUERIES, ROOT, SRC, examples  # noqa: E402
```

Then replace every use of the old local `PREFIXES` in `shorten()` with `IRI_TO_PREFIX`.

**Do not blind-substitute the glob.** `run_competency.py:81` is `examples = sorted((ROOT / "examples").glob("*.ttl"))` *inside* `load_graph`, and `examples = examples()` binds `examples` as a local for the whole function — an `UnboundLocalError` on the call itself. Rename the local instead, updating its two uses at lines 82 and 85:

```python
    paths = examples()
    if not paths:
        print("no example files found; competency questions need instance data", file=sys.stderr)
        raise SystemExit(1)
    for path in paths:
        g.parse(path, format="turtle")
    return g
```

- [ ] **Step 4: Point the other two scripts at the registry**

In `scripts/validate_shapes.py`, replace:

```python
from validate import MODULES, ROOT, SRC  # noqa: E402  -- one MODULES list, not three
```

with:

```python
from registry import MODULES, ROOT, SRC, examples  # noqa: E402
```

and replace its `sorted((ROOT / "examples").glob("*.ttl"))` with `examples()`.

In `scripts/generate_diagram.py`, replace `from validate import MODULES, ROOT, SRC` with `from registry import MODULES, ROOT, SRC`, and update the comment above it that says validate.py owns the list — it does not any more.

In `scripts/validate_shapes.py`, also delete its local `DEFAULT_SHAPES = ROOT / "shapes" / "thermaledge-export.ttl"` and import `SHAPES` from the registry instead, using it wherever `DEFAULT_SHAPES` was used. Leaving both is the duplication this task exists to remove.

- [ ] **Step 5: Prove there is one definition left**

Run:

```bash
grep -c 'MODULES = \[' scripts/*.py | grep -v ':0'
```

Expected: exactly one line, `scripts/registry.py:1`. Any other hit is a copy that survived.

Run:

```bash
grep -n 'w3id.org/forecast-market-ontology/examples' scripts/validate.py scripts/run_competency.py
```

Expected: one hit only — `validate.py`'s `in_scope` tuple, which is a prefix used for a startswith test, not a namespace map.

Scoped to those two files on purpose. A repo-wide grep also matches
`generate_verification_data.py` (a Turtle template) and `test_validate.py`
(an expected failure message), neither of which is a namespace map, so
"expected: no output" would be wrong and the step would look broken.

- [ ] **Step 6: Run the full suite**

Run: `make test`

Expected: every stage green — validator `OK`, `76/76 checks passed`, both shapes runs conform, `8/8 competency questions`, export-check OK, `consistent`, `6/6 reasoner guards fire`, `PASS: ksh:WeatherMarket inferred`.

If `76/76` is not the number, a negative test broke: report it rather than adjusting the count.

- [ ] **Step 7: Commit**

```bash
git add scripts/registry.py scripts/validate.py scripts/run_competency.py \
        scripts/validate_shapes.py scripts/generate_diagram.py
git commit -m "One registry for the paths and namespaces the checkers share

rex: was added to validate.py's prefix map and not to run_competency.py's,
which held the same namespaces inverted -- two maps over one set of facts.
The registry holds one source and derives both views."
```

---

### Task 2: Globs leave the Makefile; prose stops counting itself

**Files:**
- Modify: `Makefile` (the `shapes` and `export-check` targets, and the `EXPORT_FIXTURES`/`NEGATIVE_FIXTURES` variables), `scripts/validate_shapes.py`, `scripts/run_competency.py`, `README.md`, `CLAUDE.md`

**Interfaces:**
- Consumes: `registry.exports()`, `registry.negatives()` from Task 1.
- Produces: `validate_shapes.py --exports` and `run_competency.py --exports` / `--negatives` flags, so the Makefile names no globs.

- [ ] **Step 1: Add `--exports` to the shapes checker**

In `scripts/validate_shapes.py`, in the argument handling, add a branch alongside `--examples`. Each export is an independent graph and must be validated in its own invocation — merging them lets one export supply a protocol another omits:

```python
    if "--exports" in argv:
        rest = [a for a in argv if a != "--exports"]
        if rest:
            print(f"--exports takes no other files; got {' '.join(rest)}", file=sys.stderr)
            return 2
        paths = exports()
        if not paths:
            print("--exports matched no files", file=sys.stderr)
            return 2
        worst = 0
        for path in paths:
            worst = max(worst, main([str(path), "--shapes", str(shapes_path)]))
        return worst
```

Place this branch before the `--examples` branch, and import `exports` from the registry.

- [ ] **Step 2: Add `--exports` and `--negatives` to the competency runner**

In `scripts/run_competency.py`, before the existing `--data` handling, add:

`main()` takes no arguments and reads `sys.argv`, so drive it per fixture from the entry point rather than refactoring its body. Replace the file's last two lines:

```python
if __name__ == "__main__":
    raise SystemExit(main())
```

with:

```python
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
            # A non-zero exit is not proof of rejection: "no queries found", an
            # unreadable fixture or a renamed script all exit non-zero too. The
            # Makefile target this replaces greps for a FAIL [cq line for exactly
            # that reason, and dropping to an exit code would weaken it.
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = main()
            out = buf.getvalue()
            print(out, end="")
            if not want_pass and "FAIL [cq" not in out:
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
```

Import `exports` and `negatives` from the registry alongside the Task 1 imports.

- [ ] **Step 3: Point the Makefile at the flags**

Replace the `EXPORT_FIXTURES` and `NEGATIVE_FIXTURES` variable definitions and the bodies of `shapes` and `export-check` with:

```make
shapes:
	$(PY) scripts/validate_shapes.py --examples
	$(PY) scripts/validate_shapes.py --exports

## Production CQ mode, both directions. Every export fixture must pass, every
## negative fixture must be rejected, and the target-mismatch fixture must fail
## on CQ2 specifically -- it also fails cq04, so a generic rejection would hide a
## lost cq02 floor.
export-check:
	$(PY) scripts/run_competency.py --exports
	$(PY) scripts/run_competency.py --negatives
	@out=$$($(PY) scripts/run_competency.py --data $(MISMATCH) 2>&1); \
	echo "$$out" | grep -q 'FAIL \[cq02-probability-gap.rq\]' || { \
		echo "FAIL: the mismatch fixture did not fail on cq02 specifically."; \
		echo "$$out" | tail -3; \
		exit 1; }
	@echo "OK: exports pass, negatives are rejected, the mismatch fails on cq02"
```

- [ ] **Step 4: Strip apparatus counts from prose**

The rule, and it is not "delete all numbers":

- **Keep** numbers describing the ontology's state — `43 direct / 62 via subclass / 98`, the 30/27/23 weather-class figures in Open questions. A reader cannot reconstruct these.
- **Remove** numbers counting apparatus artifacts — they change every PR and have caused four findings.

In `README.md`, find:

```
propositions whose subjects have no type, none of which is real. Seven negative tests in
`scripts/test_validate.py` prove the shapes reject a stripped protocol, an out-of-range
probability, a market with two propositions, and four defects on export-shaped data.
```

Replace with:

```
propositions whose subjects have no type, none of which is real. Negative tests in
`scripts/test_validate.py` prove the shapes reject a stripped protocol, an out-of-range
probability, a market with two propositions, and several defects on export-shaped data.
```

Then search `README.md` and `CLAUDE.md` for any remaining count of test cases, negative tests, or checked files (`grep -niE '\b(three|four|five|six|seven|eight|nine|ten|[0-9]+) (negative tests|cases|checks|file\(s\))' README.md CLAUDE.md` — case-insensitive, or it misses the capitalised "Seven" it is looking for) and reword each the same way. Leave every ontology-state figure alone.

- [ ] **Step 5: Run the full suite**

Run: `make test`

Expected: all stages green, including the reworded `shapes` and `export-check` output. The prose check must still pass — if it fails naming a term, a reword dropped or mistyped a backticked name.

- [ ] **Step 6: Commit**

```bash
git add Makefile scripts/validate_shapes.py scripts/run_competency.py README.md CLAUDE.md
git commit -m "Resolve fixture globs in Python, and stop counting tests in prose

The Makefile and the scripts both knew where fixtures live. Now the scripts
do and the Makefile calls them, so examples/negative/ cannot go unglobbed
again. Prose keeps the numbers describing the ontology and drops the ones
counting test cases, which change every PR and caused four review findings."
```

---

### Task 3: A crashing check is a failure, not an abort

**Files:**
- Modify: `scripts/validate.py:1222-1229` and `1310`

**Interfaces:**
- Consumes: nothing new.
- Produces: `run_check(fn, *args) -> None`, which records `FAIL [<name>]: raised <Type>: <msg>` instead of propagating.

**On the spec's other half.** The spec asks for the same wrapping around "each query in `run_competency.py`", citing `KeyError: 'min_rows'`. That case is already handled: `run_competency.py:153-168` validates the expectation entry's value types and prints a FAIL, and the query call itself is already inside a `try/except` that prints `FAIL [<file>]: query error`. No work is needed there, and this note exists so the gap is recorded as closed rather than missed.

- [ ] **Step 1: Write the failing test**

Add to `scripts/test_validate.py`'s `CASES` list:

```python
    (
        # A check that raises used to abort the run, so every check after it was
        # never executed and the output ended in a traceback rather than a verdict.
        # A crash is a failure of that check and nothing more.
        "a check raising an unexpected exception",
        "scripts/validate.py",
        """def check_trades(g: Graph) -> None:""",
        """def check_trades(g: Graph) -> None:
    raise RuntimeError("injected")""",
        "check_trades raised RuntimeError: injected",
    ),
```

- [ ] **Step 2: Run it and watch it fail**

Run: `poetry run python3 scripts/test_validate.py 2>&1 | grep -A2 'raising an unexpected'`

Expected: `FAIL [a check raising an unexpected exception]: exited non-zero but message missing`. The run does exit non-zero — a traceback does that — but the message is a traceback, not a verdict. That gap is the point.

- [ ] **Step 3: Add the wrapper**

In `scripts/validate.py`, above `def main()`, add:

```python
def run_check(fn, *args) -> None:
    """Run one check; a raised exception becomes that check's failure.

    An unhandled exception used to abort main(), so every later check went
    unrun and the operator saw a traceback where a verdict belonged. A crashing
    check has failed; the others still have something to say.
    """
    try:
        fn(*args)
    except Exception as exc:  # noqa: BLE001
        fail(f"{fn.__name__} raised {type(exc).__name__}: {exc}")
```

Then replace the eight calls at `validate.py:1222-1229`:

```python
    for check in (check_dimensions, check_lead_times, check_current_assessments,
                  check_scores, check_grouping_coherence, check_protocols,
                  check_payouts, check_trades):
        run_check(check, ex)
```

and the call at line 1310:

```python
    run_check(check_context_terms, g, ex)
```

- [ ] **Step 4: Run the test and watch it pass**

Run: `poetry run python3 scripts/test_validate.py 2>&1 | grep 'raising an unexpected'`

Expected: `ok   [a check raising an unexpected exception]`

- [ ] **Step 5: Confirm the other checks still run after a crash**

Run:

```bash
cp scripts/validate.py /tmp/v.bak
python3 - <<'PY'
import pathlib
p = pathlib.Path("scripts/validate.py"); t = p.read_text()
t = t.replace("def check_dimensions(g: Graph) -> None:",
              "def check_dimensions(g: Graph) -> None:\n    raise RuntimeError('injected')", 1)
p.write_text(t)
PY
poetry run python3 scripts/validate.py 2>&1 | grep -cE 'lead times|proposition\(s\) checked'
cp /tmp/v.bak scripts/validate.py
```

Expected: a non-zero count — checks after the crashing one still ran and printed their notes. Before this change the run stopped at the traceback.

- [ ] **Step 6: Full suite and commit**

Run: `make test` — all green, negative tests now one higher than before.

```bash
git add scripts/validate.py scripts/test_validate.py
git commit -m "A crashing check fails that check, not the whole run

An unhandled exception aborted main(), so every later check went unrun and
the operator got a traceback where a verdict belonged. This is how one
malformed production-expectations entry hid every remaining result."
```

- [ ] **Step 7: Submit PR 1**

```bash
gt submit --no-interactive
```

Report the PR URL. Do not start Task 4 until this is submitted.

---

# PR 2 — `joel/checks-enforcement`

### Task 4: Coverage counts become assertions

**Files:**
- Modify: `scripts/validate.py` — add `coverage()`, then the nine call sites at lines `389, 460, 493, 562, 600, 657, 778, 910, 963` and the traversal note near `1295`
- Modify: `scripts/test_validate.py` — one new negative case

**Interfaces:**
- Consumes: `fail()` and `notes` in `validate.py`.
- Produces: `coverage(name: str, count: int, detail: str) -> None` and the module-level list `coverage_log: list[tuple[str, int]]`, which Task 5 reads.

- [ ] **Step 1: Write the failing test**

Add to `CASES` in `scripts/test_validate.py`:

```python
    (
        # The seventh zero-coverage guard. Six were written by hand -- assessment,
        # forecast-target, grouping, score, settlement-value, target-protocol -- and
        # lead times was missed, so a graph where every forecast lost its lead time
        # reported "0 checked" and passed.
        "the lead-time check traverses nothing",
        "scripts/validate.py",
        """    for forecast, stated in g.subject_objects(LEAD_HOURS):""",
        """    for forecast, stated in g.subject_objects(URIRef("https://example.invalid/none")):""",
        "lead times: nothing to check",
    ),
```

That anchor appears exactly once, at `scripts/validate.py:411`. Redirecting the traversal at a property no triple uses makes the loop run zero times, which is precisely the condition that used to pass.

- [ ] **Step 2: Run it and watch it fail**

Run: `poetry run python3 scripts/test_validate.py 2>&1 | grep -A2 'lead-time check traverses'`

Expected: `FAIL [the lead-time check traverses nothing]: validate.py passed but should have failed`. That is the bug: zero coverage passes.

- [ ] **Step 3: Add `coverage()`**

In `scripts/validate.py`, next to `fail()`:

```python
coverage_log: list[tuple[str, int]] = []


def coverage(name: str, count: int, detail: str, on_empty: str = "") -> None:
    """Record a check's traversal count, and fail when it is zero.

    Every check prints how much it looked at. Printing is not checking: six
    "traverses nothing" guards were written by hand and the seventh, for lead
    times, was missed, so the count could read 0 and the run stayed green.

    on_empty carries the diagnostic the hand-written guard used to print --
    which chain is broken, not merely that something is. A new check that
    passes nothing still gets the guard; it just gets a blunter message until
    someone writes a sharper one.
    """
    coverage_log.append((name, count))
    if count == 0 and EXAMPLES:
        fail(f"{name}: nothing to check, so this check proved nothing"
             + (f" -- {on_empty}" if on_empty else ""))
        return
    notes.append(f"{name}: {count} {detail}")
```

- [ ] **Step 4: Convert the nine call sites**

Replace each coverage note with a `coverage()` call, keeping the existing wording as the `detail` argument. Exact replacements:

| Line | Replace `notes.append(...)` with |
|---|---|
| 389 | `coverage("unit coherence", compared, "comparison pair(s) checked")` |
| 460 | `coverage("lead times", checked, "checked against issuance and interval start")` |
| 493 | `coverage("current assessments", len(by_proposition), "proposition(s) checked for a single current assessment")` |
| 562 | `coverage("skill scores", checked, "Brier score(s) checked against their inputs")` |
| 600 | `coverage("target protocols", len(targets), "observation target(s) checked for a protocol")` |
| 657 | `coverage("settlement protocols", checked, "market/protocol pair(s) checked for settlement agreement")` |
| 778 | `coverage("grouping coherence", checked, "market/grouping pair(s) checked for target agreement")` |
| 910 | `coverage("payouts", verified, "payout(s) checked against their resolution, holder and lot")` |
| 963 | `coverage("trades", checked, "trade(s) checked for opposite sides and equal quantity")` |

Leave line 838 (`payout skipped: ...`) alone — it is a per-item note, not a coverage count.

Near line 1295, replace the forecast-target traversal note with:

```python
    coverage("forecast targets", scored, "forecast probability/proposition pair(s) checked for target agreement")
```

**Then fold the seven hand-written zero-coverage guards into their `coverage()` call.** Each tests the same variable its new call counts, so leaving both reports one defect twice — but each also carries a diagnostic naming the broken chain, which a generic message would throw away. Move the diagnostic into `on_empty` and delete the guard:

| Guard | `on_empty` argument to add |
|---|---|
| 488 | `"the assessesProposition chain is broken"` |
| 557 | `"the usesScoringRule or scoresAssignment chain is broken"` |
| 595 | `"the wx:WeatherObservationTarget typing is broken"` |
| 652 | `"the settlementSource or sourceProtocol chain is broken"` |
| 772 | `"the inEventGrouping or expressesProposition chain is broken"` |
| 958 | `"the trading layer is unexercised again"` |
| 1289 | `"the has-part or assignsProbabilityTo chain is broken"` |

So line 493's call becomes:

```python
    coverage("current assessments", len(by_proposition),
             "proposition(s) checked for a single current assessment",
             "the assessesProposition chain is broken")
```

and the `if EXAMPLES and not by_proposition:` guard above it, with its `fail(...)` body, is deleted. Repeat for the other six.

**Leave `validate.py:364` and `validate.py:902` alone.** Those guard `settlement_compared` and `reached` — different variables from the ones their `coverage()` calls count, so they are not duplicates and deleting them would remove real coverage.

**The six existing "traverses nothing" negative tests must still pass unchanged.** Their expected substrings assert on the diagnostics above, which `on_empty` preserves. If one fails, the diagnostic was transcribed wrongly — fix the transcription, never the expectation.

- [ ] **Step 5: Run the test and watch it pass**

Run: `poetry run python3 scripts/test_validate.py 2>&1 | grep 'lead-time check traverses'`

Expected: `ok   [the lead-time check traverses nothing]`

- [ ] **Step 6: Confirm the note format survived**

Run: `make validate | head -20`

Expected: the same note lines as before, now prefixed by the coverage name — for example `lead times: 161 checked against issuance and interval start`. No note may read `: 0 `.

- [ ] **Step 7: Full suite and commit**

Run: `make test` — all green.

```bash
git add scripts/validate.py scripts/test_validate.py
git commit -m "Make each check's coverage count an assertion

Nine checks printed how much they looked at; printing is not checking. Six
zero-coverage guards were hand-written and the seventh, for lead times, was
missed -- a graph where every forecast lost its lead time reported 0 checked
and stayed green. coverage() fails on zero and every future check gets it."
```

---

### Task 5: The meta-test

**Files:**
- Create: `scripts/test_meta.py`
- Modify: `Makefile` (new `meta` target, added to `test`), `README.md`

**Interfaces:**
- Consumes: `validate.coverage_log`, and `registry.MODULES`/`SRC` from Task 1.
- Produces: `make meta`.

- [ ] **Step 1: Write the meta-test**

Create `scripts/test_meta.py`:

```python
#!/usr/bin/env python3
"""Tests about the checks themselves, rather than about the ontology.

A check with nothing to check must not pass. Six such guards were written by
hand and the seventh was missed, which is what a hand-maintained rule earns
over time. Calling every check with an empty graph enforces the rule for all
of them, including checks nobody has written yet.

Run: python3 scripts/test_meta.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from rdflib import Graph

sys.path.insert(0, str(Path(__file__).resolve().parent))

import validate as V  # noqa: E402
from registry import MODULES, ROOT, SRC  # noqa: E402


def schema_only() -> Graph:
    """The modules with no example data: every check should traverse nothing."""
    g = Graph()
    for rel in MODULES:
        g.parse(SRC / rel, format="turtle")
    return g


# The one check that reads no graph. It walks PROSE_FILES and compares what they
# name against the schema, so "nothing to check" is not a state it can be in.
# Exempting it by name, in code, beats exempting it by judgement at review time.
NOT_DATA_DEPENDENT = {
    "check_context_terms": "reads PROSE_FILES, not the example graph",
}


def check_names() -> list[str]:
    return sorted(n for n in dir(V) if n.startswith("check_"))


def main() -> int:
    failures: list[str] = []
    names = check_names()
    if not names:
        print("FAIL: found no check_* functions in validate.py")
        return 1

    g = schema_only()
    for name in names:
        fn = getattr(V, name)
        V.failures.clear()
        V.notes.clear()
        V.coverage_log.clear()
        if name in NOT_DATA_DEPENDENT:
            print(f"  --   [{name}] exempt: {NOT_DATA_DEPENDENT[name]}")
            continue
        try:
            fn(g)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{name} raised {type(exc).__name__}: {exc} on an empty graph")
            continue
        if V.failures:
            print(f"  ok   [{name}] fails with nothing to check")
        else:
            failures.append(
                f"{name} passed with nothing to check, so it proves nothing when its "
                f"traversal is empty"
            )

    # A smoke alarm, not a proof: a mention is not a test, and check_lead_times
    # was mentioned here while its zero-coverage hole went unnoticed for a
    # release. It catches only a check nobody wrote anything about at all.
    suite = (ROOT / "scripts" / "test_validate.py").read_text(encoding="utf-8")
    for name in names:
        if name not in suite:
            failures.append(f"{name} is named nowhere in test_validate.py")

    print(f"\n{len(names)} check(s) examined")
    if failures:
        print(f"\nFAILED ({len(failures)}):", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run it**

Run: `poetry run python3 scripts/test_meta.py`

Expected: one `ok` line per data-dependent check, one `--` line for the exempt `check_context_terms`, and `OK`.

This step only passes **after Task 4**, which is why Task 5 follows it: until `coverage()` lands, `check_lead_times` passes with nothing to check and this test correctly reports it. If you are running Task 5 before Task 4 is committed, that failure is the expected one.

- [ ] **Step 3: Prove it catches the real bug**

Temporarily revert `check_lead_times`' coverage call to a plain `notes.append`, run `poetry run python3 scripts/test_meta.py`, and confirm it reports `check_lead_times passed with nothing to check`. Restore, and confirm it passes again.

- [ ] **Step 3b: Give the two unnamed checks a mention**

The smoke alarm requires every `check_*` name to appear in `scripts/test_validate.py`. Three do not today: `check_trades` (Task 3 adds it), `check_dimensions`, and `check_context_terms`. Both remaining ones DO have negative cases — the cases simply never name the function they exercise, which is the gap the alarm is meant to expose.

Add the function name to the comment above each. For the Celsius/Fahrenheit unit case, extend its comment with:

```python
        # Exercises check_dimensions.
```

and for the first CONTEXT.md case:

```python
        # Exercises check_context_terms.
```

Do not invent new cases — the coverage exists; only the naming was missing.

- [ ] **Step 4: Wire it in**

In the `Makefile`, add after the `validate-negative` target:

```make
## Tests about the checks themselves: every check must fail with nothing to check.
meta:
	$(PY) scripts/test_meta.py
```

Add `meta` to `.PHONY` and to the `test` target, immediately after `validate-negative`.

- [ ] **Step 5: Document it**

In `README.md`'s usage block, add after the `make validate-negative` line:

```
make meta                            # tests about the checks: none may pass with nothing to check
```

And in the Validation section, after the paragraph about `scripts/test_validate.py`, add:

```
`make meta` checks the checks. Every check reports how much it traversed, and a
check that traversed nothing has proved nothing — so `scripts/test_meta.py` calls
each one with the schema and no example data and requires it to fail. Six such
guards were written by hand before this existed and the seventh, for lead times,
was missed; a rule enforced by memory is enforced wherever someone remembered.
```

- [ ] **Step 6: Full suite and commit**

Run: `make test` — all green, with `make meta` in the sequence.

```bash
git add scripts/test_meta.py Makefile README.md
git commit -m "Check the checks: none may pass with nothing to check

Calls every check_* with the schema and no data and requires it to fail.
Six zero-coverage guards were hand-written and the seventh was missed,
which is what a rule enforced by memory earns. This one covers checks
nobody has written yet."
```

- [ ] **Step 7: Submit PR 2**

```bash
gt submit --no-interactive
```

Report the PR URL. Do not start Task 6 until this is submitted.

---

# PR 3 — `joel/shape-mutants`

### Task 6: Generated shape mutants and the dead-constraint lint

**Files:**
- Create: `scripts/test_shapes.py`
- Modify: `Makefile` (new `shapes-negative` target, added to `test`), `README.md`

**Interfaces:**
- Consumes: `registry.MODULES`, `registry.SRC`, `registry.SHAPES`, `registry.exports()`, `registry.OUR_NS`.
- Produces: `make shapes-negative`.

- [ ] **Step 1: Write the shape tester**

Create `scripts/test_shapes.py`:

```python
#!/usr/bin/env python3
"""Tests about the SHACL shapes, rather than about the data they check.

Three properties, each earned by a bug that shipped:

  1. VACUITY. A shape whose sh:targetClass matches no focus node CONFORMS. A
     dead shape and a clean run are indistinguishable in pyshacl's output.
  2. SUPERTYPE MUTANTS. rdfs types a subclass instance as its parent, never the
     reverse, so a shape targeting a subclass misses data typed as the parent.
     MarketShape targeted ksh:WeatherMarket and ProbabilityShape targeted its
     two leaf classes; an export typing markets as ksh:Market conformed with no
     proposition and no ticker, and one typing probabilities as
     fm:ProbabilityAssignment conformed with a probability of 7.41. Retyping the
     focus nodes to each parent and requiring the shape to still fire derives
     that test from the hierarchy instead of from someone thinking of it.
  3. DEAD sh:class. validate_shapes.py runs with inference="rdfs", so range
     entailment types a property's object BEFORE SHACL looks. sh:class C on a
     path whose rdfs:range is already C can never fire; two such constraints
     shipped and a dangling protocol IRI conformed.

In-process on purpose: test_validate.py copies the whole repo per case, which
costs about a second each. The mutant matrix would push that suite past several
minutes; here the whole thing runs in about one.

Run: python3 scripts/test_shapes.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from pyshacl import validate as shacl_validate
from rdflib import Graph, RDF, RDFS, URIRef
from rdflib.namespace import Namespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
from registry import MODULES, OUR_NS, SHAPES, SRC, exports  # noqa: E402

SH = Namespace("http://www.w3.org/ns/shacl#")


def base_graph() -> Graph:
    g = Graph()
    for rel in MODULES:
        g.parse(SRC / rel, format="turtle")
    return g


def conforms(data: Graph, shapes: Graph) -> bool:
    ok, _, _ = shacl_validate(
        data, shacl_graph=shapes, inference="rdfs", advanced=True,
    )
    return ok


def targets(shapes: Graph) -> list[tuple[URIRef, URIRef]]:
    return sorted(shapes.subject_objects(SH.targetClass), key=lambda p: str(p[0]))


def subclasses_of(schema: Graph, cls: URIRef) -> set:
    return {cls} | set(schema.transitive_subjects(RDFS.subClassOf, cls))


def parents_of(schema: Graph, cls: URIRef) -> list:
    """Superclasses in our own namespaces. BFO parents are not ours to retype to."""
    return sorted(
        (p for p in schema.transitive_objects(cls, RDFS.subClassOf)
         if p != cls and isinstance(p, URIRef) and str(p).startswith(OUR_NS)),
        key=str,
    )


def main() -> int:
    schema = base_graph()
    shapes = Graph().parse(SHAPES, format="turtle")
    fixtures = exports()
    if not fixtures:
        print("FAIL: no export fixtures to mutate", file=sys.stderr)
        return 1

    failures: list[str] = []
    checked = 0

    # 3. Dead sh:class: static, no data needed.
    for prop_shape in shapes.objects(None, SH.property):
        path = shapes.value(prop_shape, SH.path)
        klass = shapes.value(prop_shape, SH["class"])
        if path is None or klass is None:
            continue
        checked += 1
        rng = schema.value(path, RDFS.range)
        if rng is not None and rng in subclasses_of(schema, klass):
            failures.append(
                f"sh:class {klass} on {path} can never fire: rdfs:range is already "
                f"{rng}, and inference=\"rdfs\" types the object before SHACL looks"
            )
        else:
            print(f"  ok   [sh:class on {str(path).split('#')[-1]}] can fire")

    for fixture in fixtures:
        data = base_graph()
        data.parse(fixture, format="turtle")

        for shape, cls in targets(shapes):
            label = str(shape).split("#")[-1]
            focus = {s for c in subclasses_of(schema, cls)
                     for s in data.subjects(RDF.type, c)}

            # 1. Vacuity.
            checked += 1
            if not focus:
                failures.append(
                    f"{label} matches no focus node in {fixture.name}; a shape with "
                    f"no focus nodes conforms, so it is indistinguishable from a pass"
                )
                continue
            print(f"  ok   [{label}] {len(focus)} focus node(s) in {fixture.name}")

            # 2. Supertype mutants.
            for parent in parents_of(schema, cls):
                checked += 1
                mutant = Graph()
                for triple in data:
                    mutant.add(triple)
                for node in focus:
                    # Every asserted type in the target's subclass closure, not just
                    # the target itself. The fixture types its market ksh:WeatherMarket
                    # while the shape targets ksh:Market, so removing only `cls`
                    # removed a triple that was never there: the node kept its subclass
                    # type, the shape still fired, and the mutant proved nothing. A
                    # test for shapes that cannot fail, that could not fail.
                    for asserted in subclasses_of(schema, cls):
                        mutant.remove((node, RDF.type, asserted))
                    mutant.add((node, RDF.type, parent))
                pname = str(parent).split("#")[-1]
                if conforms(mutant, shapes):
                    failures.append(
                        f"{label} stops firing when its focus nodes are retyped to "
                        f"{pname}: target the parent, not the subclass"
                    )
                else:
                    print(f"  ok   [{label}] still fires when retyped to {pname}")

    print(f"\n{checked} shape assertion(s) checked")
    if failures:
        print(f"\nFAILED ({len(failures)}):", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run it on the clean tree**

Run: `poetry run python3 scripts/test_shapes.py`

Expected: `OK`, with `ok` lines for the `sh:class` lint, focus-node counts per shape, and a retype line per parent class.

If a supertype mutant reports a failure on the clean tree, do not adjust the test — read it. It means a shape is still targeting a subclass, which is the bug this task exists to find.

- [ ] **Step 3: Prove the mutant test catches the real bug**

Temporarily revert `teh:MarketShape`'s target in `shapes/thermaledge-export.ttl`:

```bash
cp shapes/thermaledge-export.ttl /tmp/s.bak
sed -i '' 's|    sh:targetClass ksh:Market ;|    sh:targetClass ksh:WeatherMarket ;|' shapes/thermaledge-export.ttl
poetry run python3 scripts/test_shapes.py 2>&1 | tail -4
cp /tmp/s.bak shapes/thermaledge-export.ttl
```

Expected while reverted: a failure naming `MarketShape` and the retype to `Market`. Then restore and confirm `OK` again.

Repeat for `teh:ProbabilityShape`, reverting `sh:targetClass fm:ProbabilityAssignment` to the two leaf classes it originally targeted:

```bash
sed -i '' 's|    sh:targetClass fm:ProbabilityAssignment ;|    sh:targetClass fm:ForecastProbability, fm:MarketImpliedProbability ;|' shapes/thermaledge-export.ttl
```

and confirm it is caught the same way, then restore.

- [ ] **Step 4: Prove the dead-constraint lint fires**

Temporarily re-add the constraint that shipped dead:

```bash
cp shapes/thermaledge-export.ttl /tmp/s.bak
python3 - <<'PY'
import pathlib
p = pathlib.Path("shapes/thermaledge-export.ttl"); t = p.read_text()
t = t.replace("""        sh:path wx:underProtocol ;
        sh:minCount 1 ; sh:maxCount 1 ;""",
"""        sh:path wx:underProtocol ;
        sh:minCount 1 ; sh:maxCount 1 ;
        sh:class wx:MeasurementProtocol ;""")
p.write_text(t)
PY
poetry run python3 scripts/test_shapes.py 2>&1 | tail -3
cp /tmp/s.bak shapes/thermaledge-export.ttl
```

Expected while modified: a failure saying `sh:class ...MeasurementProtocol on ...underProtocol can never fire`. Then restore and confirm `OK`.

- [ ] **Step 5: Wire it in**

In the `Makefile`, after the `shapes` target:

```make
## Tests about the shapes themselves: no shape may match nothing, no shape may
## stop firing when its focus nodes are retyped to a parent class, and no
## sh:class may be dead under rdfs range entailment.
shapes-negative:
	$(PY) scripts/test_shapes.py
```

Add `shapes-negative` to `.PHONY` and to `test`, immediately after `shapes`.

- [ ] **Step 6: Document it**

In `README.md`'s usage block, after the `make shapes` line:

```
make shapes-negative                 # tests about the shapes: vacuity, retyping, dead constraints
```

And in the Validation section, replace the two paragraphs stating the two rules with a note that `make shapes-negative` now enforces both mechanically — keep the rules themselves, since they are the reasoning a reader needs; add that the supertype mutants are generated from the class hierarchy rather than hand-written.

- [ ] **Step 7: Full suite and commit**

Run: `make test` — all green, with `shapes-negative` in the sequence.

```bash
git add scripts/test_shapes.py Makefile README.md
git commit -m "Generate the shape mutants from the class hierarchy

Two shapes shipped targeting a subclass, so data typed as the parent matched
no focus node -- and a shape with no focus nodes conforms. Both were caught by
a human writing an adversarial fixture. Retyping focus nodes to each parent
and requiring the shape to still fire derives that test instead. Plus a static
lint for sh:class on a path whose rdfs:range already supplies the type, which
is how a dangling protocol IRI conformed."
```

- [ ] **Step 8: Submit PR 3**

```bash
gt submit --no-interactive
```

Report all three PR URLs and the stack order.

---

## What this plan deliberately does not do

- **Does not speed up the 93s negative suite.** Each case still copies the repo. Real, and it caps how many cases anyone writes, but it is cost rather than correctness. Task 6 avoids adding to it rather than fixing it.
- **Does not fix cq06's all-null row.** Aggregation over an empty inner result yields one null row that a row count reads as data. Harmless while both entries are `may_be_empty`; a `min_rows` of 1 on either would be vacuously satisfied. Fixing it changes query semantics, not the apparatus.
- **Does not enforce per-check negative-case coverage.** The strong form needs all 56 case tuples annotated with their target check. Task 5 ships the empty-graph test, which is stronger where it applies, plus an honest smoke alarm.
- **Touches no ontology file.** If `src/` or `queries/*.expected` changes, something went wrong.
