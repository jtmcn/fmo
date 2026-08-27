# LSP Diagnostics Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clear the repo's 95 LSP diagnostics (pyright, ast-grep, typos) down to zero real findings — fixing the 26 genuine type/config issues and suppressing the 69 verified false positives — without changing any runtime behavior.

**Architecture:** The 95 findings split into exactly five root causes. Three are fixed in-config or in-type-annotating code (pyright environment resolution, two pyright narrowing gaps that are trivially restructured to be type-sound). Two are tool-config suppressions of verified false positives (an over-broad ast-grep heuristic rule, and a typos pass over deliberate `teh:`/`anc` identifiers). None require logic changes — every one is either a config file the repo was missing or a shallow code reshaping that is provably equivalent.

**Tech Stack:** pyright (via pi-lens), ast-grep (via pi-lens), typos-lsp (via pi-lens), and the existing `poetry` venv at `.venv`.

**Spec:** The diagnostics analyzed in the session. Findings are enumerated by file/rule/line so each task's completion is checkable by re-running `lsp_diagnostics` and counting zeros.

## Global Constraints

- Repository project conventions from `CLAUDE.md`: every code path must be provably behavior-preserving (no runtime change). The repo has no linter gate in CI; these diagnostics are advisory, so nothing may *degrade* clarity to silence a checker.
- Every validator check is fail-fast by design ("an empty result fails"); malformed-input crash-on-purpose is a **feature**. Wrap-with-try/except is the wrong fix for the `file-input.json.read_text()` findings — keep them throwing (or guard first), matching `load_ledger()`'s existing `SystemExit(1)` style.
- When a type can't be proven by checked-control-flow (see Task 3 `compare()`), **restructure the code to make the proof true**, never sprinkle `# type: ignore` or `typing.cast`.
- Spelling false positives come from a real `teh:` namespace prefix (test ontology) and a real `anc` local variable; fix by allowlisting exact identifiers in `pyproject.toml`, not by renaming domain terms.
- No changes to `examples/` (is generated) or `src/imports/bfo-core.ttl` (vendored) — this plan only touches `scripts/`, `pyproject.toml`, `pyrightconfig.json`, and any new config files.
- Verify every task by re-running `lsp_diagnostics` on `scripts/` and asserting the affected rule's count went to zero.

---

### Task 1: Point pyright at the poetry venv (fixes ~13 `reportMissingImports`)

**Files:**

- Create: `pyrightconfig.json` (repo root)

**Why:** `rdflib 7.6.0`, `pyshacl 0.40.1`, `rdflib.term`, `rdflib.namespace` are all installed in `.venv`, but pyright resolves against the system interpreter because there is no pyright config. The 13 errors (`axioms.py:23-24`, `extract_qudt_subset.py:25`, `generate_diagram.py:23-24`, `run_competency.py:34`, `shape_signatures.py:30,286`, `term_signatures.py:37-38`, `test_meta.py:29`, `test_shapes.py:42-44`, `validate.py:83-84`, `validate_shapes.py:28-29`) are all this one cause.

The venv interpreter is `<repo>/.venv/bin/python` (symlink to pyenv python3.12). Pyright supports `venvPath`/`venv`.

- [ ] **Step 1: Create `pyrightconfig.json`**

```json
{
  "venvPath": ".",
  "venv": ".venv"
}
```

- [ ] **Step 2: Verify pyright resolves the imports**

Run: `npx pyright scripts/validate.py 2>&1 | grep -c reportMissingImports` (or equivalent via your `lsp_diagnostics` on `scripts/`)
Expected: the `reportMissingImports` findings are gone; `rdflib`, `pyshacl`, `rdflib.term`, `rdflib.namespace` resolve.

- [ ] **Step 3: Commit**

```bash
git add pyrightconfig.json
git commit -m "chore(lint): point pyright at the poetry venv"
```

---

### Task 2: Rename the shadowed `path` parameter in `shape_signatures.py` (clears 1 + improves clarity)

**Files:**

- Modify: `scripts/shape_signatures.py:230-254` (param `path` at 207 → loop var `sh_path`)

**Why:** `facts(path: Path = SHAPES)` takes a filesystem path, then line 233 reassigns the same name to the SHACL property-path term from `_single(...)`. Pyright reports `reportAssignmentType` — the loop var is typed `Unknown | None`. Beyond silencing the checker, shadowing a parameter for a *different* noun ("path") is a genuine readability defect. Rename only the inner loop variable; the function parameter keeps its name and its `Path` type.

- [ ] **Step 1: Rename the inner loop variable**

Change lines 231-246:

```python
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
```

(`_single` returns `None`-able; the `if sh_path is None: continue` guard already exists. Only the names change — behavior identical.)

- [ ] **Step 2: Verify pyright silent on line 233**

Run: `npx pyright scripts/shape_signatures.py` (diagnostics filtered to that file)
Expected: `reportAssignmentType` at the loop gone.

- [ ] **Step 3: Verify the check still runs**

Run: `poetry run python scripts/shape_signatures.py --check`
Expected: `OK: <n> shape signatures reproducible, <m> constrained path(s)` (exactly as before the edit).

- [ ] **Step 4: Commit**

```bash
git add scripts/shape_signatures.py
git commit -m "refactor: rename shadowed path variable in shape_signatures.facts"
```

---

### Task 3: Make `compare()` type-honest so `old`/`new` are non-optional (clears ~11 pyright findings)

**Files:**

- Modify: `scripts/shape_signatures.py:409-497` (the `compare()` body)

**Why:** `old, new = base.get(name), current.get(name)` gives `dict | None`, and pyright won't narrow through `.get()`. The code's logic *already* guarantees both are present after the two early `continue`s (identical-digest skip, then the removed/added branches). The honest fix is to establish membership explicitly and then index — which pyright narrows cleanly — instead of hiding the invariant. This eliminates the `reportOptionalMemberAccess` at 437-442, `reportOptionalSubscript` at 445/473-474, and `reportArgumentType` at 481 (the `was`/`now` into `_compare_path`), all in one restructure.

- [ ] **Step 1: Restructure the body membership**

Replace the block from the leading `old, new = base.get(name), current.get(name)` through the `if new.get("deactivated") ...` line with explicit membership checks:

```python
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
```

Keep the existing early `_body_digest(...) == ...` skip and the existing `else` that appends nothing. The exact old code is lines 423-449; replace them with the above, preserving the `continue` order note (added-vs-removed keeps its priorities; keep the original message text and verdict-kind pairs).

- [ ] **Step 2: Narrow `in_base/in_current` for the path loop (the `was`/`now` argument)**

Replace the block that builds `was, now` from `old["paths"].get(path)` / `new["paths"].get(path)`:

```python
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
```

- [ ] **Step 3: Do a dry-run of the signatures/diff to confirm no behavior drift**

Run: `poetry run python scripts/shape_signatures.py --check` and `poetry run python scripts/shape_signatures.py > /tmp/sig.json && poetry run python scripts/shape_signatures.py --compare build/baseline-shapes.json 2>/dev/null` — the point is output shape is unchanged (verdict strings identical). Expected: no `CHANGED`/`WEAKENED` verdicts appear that weren't there before.

- [ ] **Step 4: Verify pyright clears the run**

Run: `npx pyright scripts/shape_signatures.py`
Expected: all `reportOptional*` and `reportArgumentType` listed for this file are gone (Task 2's `reportAssignmentType` already gone).

- [ ] **Step 5: Commit**

```bash
git add scripts/shape_signatures.py
git commit -m "refactor: make shape_signatures.compare membership explicit so pyright narrows"
```

---

### Task 4: Silence `depth possibly unbound` in `check_protocols` (1 finding)

**Files:**

- Modify: `scripts/validate.py:638-647`

**Why:** `levels` is a fixed 3-tuple literal (`[market]`, `[grouping]`, `list(...)`), so `enumerate(levels)` always binds `depth`. Pyright flags `reportPossiblyUnboundVariable` at 647 because it can't know a custom object is non-empty. The clean fix: don't depend on `depth` at all — resolve *which* holder produced the source by tracking the holder list, which is already guaranteed non-empty. This makes the invariant structurally visible instead of asserted.

- [ ] **Step 1: Replace the depth-indexed key resolution**

Current:

```python
        levels = ([market], [grouping], list(g.objects(grouping, IN_SERIES)))
        sources: set[URIRef] = set()
        for depth, holders in enumerate(levels):
            sources = {s for h in holders for s in g.objects(h, SETTLEMENT_SOURCE)}
            if sources:
                break
```

New (track whether the market holder itself resolved):

```python
        grouped = [market, grouping, *g.objects(grouping, IN_SERIES)]
        sources: set[URIRef] = set()
        for holder in grouped:
            sources = set(g.objects(holder, SETTLEMENT_SOURCE))
            if sources:
                break
```

then keep the market-own logic by testing the resolved holder: `key = holder if holder is market else grouping`.

Preserve behavior: `holder` from the fixed list; once found the loop breaks, identical to the old depth-only loop. The `hold is market` equality check matches the old `depth == 0` condition exactly (depth 0 was only `[market]`).

- [ ] **Step 2: Verify pyright**

Run: `npx pyright scripts/validate.py`
Expected: `reportPossiblyUnboundVariable` at line ~647 gone.

- [ ] **Step 3: Verify the whole suite still passes**

Run: `poetry run python scripts/validate.py` (and `make validate` if in the runtime)
Expected: `OK ...` summary, all counts non-zero, no regressions.

- [ ] **Step 4: Commit**

```bash
git add scripts/validate.py
git commit -m "refactor: resolve settlement-source holder without unbound-depth narrowing"
```

---

### Task 5: Suppress the false-positive typos (`teh`, `anc`) — 48 findings

**Files:**

- Create: `typos.toml` (repo root) — pi-lens/typos discovery reads exactly `typos.toml`, `_typos.toml`, or `.typos.toml`. Use the plain `typos.toml` name so detection is unambiguous; a `[tool.typos]` table inside `pyproject.toml` would not flip the advisory-to-blocking gate the same way.

**Why:** 48 typos findings are all the same two identifiers:

- `teh:` — the *deliberate* RDF/OWL prefix for the test-ontology fixture (`test_shape_drift.py`, `generate_diagram.py`). It is not a typo.
- `anc` — a real local variable in `validate.py` (`anc = ancestors(g, cls)`).

These are exact-identifier matches; per pi-lens/typos docs the correct tool is `extend-identifiers`, not `extend-words` (which would also rewrite substrings inside unrelated words).

- [ ] **Step 1: Create `typos.toml` with the identifier allowlist**

```toml
[default.extend-identifiers]
teh = "teh"      # RDF namespace prefix for the test-ontology fixture (teh:TargetShape...)
anc = "anc"      # local var name, shorthand for "ancestors" (validate.py)
```

(Note: the presence of a repo-local typos config flips typos findings from advisory to *blocking* — the deliberate opt-in documented in pi-lens. Confirm the team wants the typos gate before committing; the allowlist itself is the correct shape.)

- [ ] **Step 2: Verify typos silence**

Run: `npx --package typos-cli typos scripts/` (or the repo's typos invocation) and confirm `teh`/`anc` are no longer reported.

- [ ] **Step 3: Commit**

```bash
git add typos.toml
git commit -m "chore(lint): allowlist teh:/anc identifiers for typos"
```

---

### Task 6: Quiet the over-broad `unchecked-throwing-call-python` ast-grep rule — 6 findings

**Files:**

- Create: `rules/ast-grep-rules/rules/unchecked-throwing-call-python.yml` (project-local override, same rule id)

**Why:** The bundled rule flags `int(...)`/`float(...)`/`json.loads(...)`/`open(...)` calls anywhere not wrapped in try/except. Six findings here, two of which are pure false positives from its overly-literal patterns:

- `generate_verification_data.py:134` — the `int((1 - OVERCONFIDENCE)*100)` is *inside a module docstring* (a comment literal), not executable code.
- `validate.py:698` — `float("inf")` is a harmless literal.

The other four (`load_ledger`, `run_competency:77`, `shape_signatures --compare baseline`, `validate.py:1212`) are all *intentional fail-fast* reads of project-owned files, matching the existing `LEDGER.exists() → SystemExit(1)` guard in `load_ledger()`. Wrapping them in try/except contradicts `CLAUDE.md`'s fail-fast philosophy. The correct disposition is to make the project rule match the intent: keep the `json.*`/`open()`/`os.*` I/O triggers but drop the `int($EXPR)`/`float($EXPR)` literals (the genuine "may raise ValueError" is value-from-parsed-data, not a hardcoded constant).

pi-lens loads project ast-grep rules from `<root>/rules/ast-grep-rules/rules/<id>.yml` and a same-id rule **overrides** the built-in.

- [ ] **Step 1: Create the project rule copy that narrows the pattern set**

```yaml
# project override of ast-grep's bundled unchecked-throwing-call-python:
# this repo's checkers are fail-fast by design (see CLAUDE.md), and the
# bundled rule's int()/float() literal patterns false-positive on
# hardcoded constants (float("inf")) and on prose inside docstrings.
id: unchecked-throwing-call-python
language: Python
severity: error
message: "File I/O or decode call not guarded -- this repo fails fast (see CLAUDE.md)"
note: |
  Raised for file reads and JSON decodes in scripts where the caller has
  not already established the file exists. Constants like float("inf")
  and int(N) literals are excluded: those cannot raise.
rule:
  any:
    - pattern: open($$$)
    - pattern: json.loads($$$)
    - pattern: json.load($$$)
    - pattern: os.stat($$$)
    - pattern: os.lstat($$$)
    - pattern: os.remove($$$)
    - pattern: os.unlink($$$)
    - pattern: os.rename($$$)
    - pattern: os.mkdir($$$)
    - pattern: os.makedirs($$$)
    - pattern: os.rmdir($$$)
    - pattern: os.listdir($$$)
    - pattern: os.access($$$)
    - pattern: shutil.copy($$$)
    - pattern: shutil.move($$$)
    - pattern: shutil.rmtree($$$)
  not:
    inside:
      stopBy: end
      kind: try_statement
```

This removes only the two false positives; the four real `file reads` findings are left as legitimate because those code paths *should* throw on a genuinely missing/malformed input and are guarded first (`load_ledger`, `run_competency`'s `path.open()`, `shape_signatures`'s `is_file()` guard, and `validate.py`'s existing `ledger.exists()` in `load_ledger`). If the team wants to keep int()/float() tracking, drop this task and instead wrap the four reads; but that changes fail-fast behavior, which is out of scope.

- [ ] **Step 2: Verify only the two docstring/constant false positives went silent, and the four fail-fast ones remain flagged**

Run ast-grep on `scripts/` with the project rule active (dispatched file). Expected findings now == 4 (`generate_verification_data.py` and `validate.py:698` no longer flagged).

- [ ] **Step 3: Commit**

```bash
git add rules/ast-grep-rules/rules/unchecked-throwing-call-python.yml
git commit -m "chore(lint): override ast-grep throwing-call rule to drop int()/float() literal false positives"
```

---

### Task 7: Final validation pass

- [ ] **Step 1: Re-run the full LSP diagnostic sweep**

Run: `lsp_diagnostics` on `scripts/` (plus root).
Expected: 0 remaining findings — pyright imports resolved, shape_signatures and validate type-clean, typos allowlisted, ast-grep down to the 4 intended fail-fast reads.

- [ ] **Step 2: Run the project suite end-to-end**

Run: `make test` (or at minimum `make validate` + `make shapes` + the two scripts' own `--check` modes).
Expected: all green, proving no runtime behavior changed.

- [ ] **Step 3: Self-review against `CLAUDE.md` constraints**

Confirm: no term renamed (only a local variable in Task 4), no `# type: ignore`/`cast` introduced, no try/except added where a fail-fast throw was the contract, `examples/` untouched. Adjust step plans if any constraint is violated.

- [ ] **Step 4: Final commit if anything drifted**

```bash
git add -A
git commit -m "chore: reconcile plan residuals"
```
