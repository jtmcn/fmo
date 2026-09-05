#!/usr/bin/env python3
"""Negative tests for `make typecheck`.

A type checker that has only ever been seen to pass is not known to work, and this
one is easier to render vacuous than the others: `ty check` handed no files prints
"All checks passed!" and exits 0. Each case here reintroduces one defect into a copy
of scripts/, runs ty, and asserts it fails with the expected rule. The source tree is
never modified.

The first three cases are the narrowings this repo already made -- a graph value
coerced to float, a traversal result passed where a URIRef is declared, the check
registry typed as a bare Callable. They exist because a revert is the likely
regression: each one reads as a harmless simplification. The fourth proves ty also
catches an error nobody has made yet, and the last three are about the make target
rather than about ty, since the vacuity hazard lives there.

Run: python3 scripts/test_typecheck.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = sorted(p.name for p in (ROOT / "scripts").glob("*.py"))

# (name, file, find, replace, rule expected in ty's output, substring expected with it)
CASES = [
    (
        # as_float's whole job. float(node) works at run time -- every rdflib node
        # subclasses str -- so nothing but the type checker objects to inlining it,
        # and the boundary where a graph value becomes a number stops being one place.
        "a graph value coerced to float without as_float",
        "validate.py",
        "if abs(as_float(stated) - actual) > 0.01:",
        "if abs(float(stated) - actual) > 0.01:",
        "invalid-argument-type",
        "float",
    ),
    (
        # The reverse narrowing: declaring URIRef on a parameter the callers feed from
        # g.objects(). The annotation claims more than the traversal delivers, which is
        # what half the original 33 diagnostics were.
        "a traversal result passed where a URIRef is declared",
        "validate.py",
        "def ancestors(g: Graph, cls: Node) -> set[URIRef]:",
        "def ancestors(g: Graph, cls: URIRef) -> set[URIRef]:",
        "invalid-argument-type",
        "ancestors",
    ),
    (
        # Callable[..., None] is the obvious annotation and it is wrong: the registry
        # reports by __name__, which callables do not have and functions do.
        "the check registry typed as a bare Callable",
        "validate.py",
        "    fn: FunctionType\n",
        "    fn: Callable[..., None]\n",
        "unresolved-attribute",
        "__name__",
    ),
    (
        # Not a revert: an error nobody has made. Also proves a newly added script is
        # checked rather than merely sitting in scripts/ -- see the make cases below.
        "a newly added script that does not type check",
        None,
        None,
        "def leads(count: int) -> str:\n    return count\n",
        "invalid-return-type",
        "zz_added_script.py",
    ),
]


def ty_command() -> list[str]:
    """ty from this interpreter's environment, with that environment named.

    Found next to sys.executable rather than on PATH: the test may be run without
    the venv activated, and a ty resolved from PATH would be a different pin. The
    explicit --python keeps import resolution identical to `make typecheck`, which
    inherits the environment poetry activates.
    """
    exe = Path(sys.executable).with_name("ty")
    if not exe.exists():
        found = shutil.which("ty")
        if found is None:
            return []
        exe = Path(found)
    return [str(exe), "check", "--python", sys.prefix, "--output-format", "concise"]


def workspace(tmp: str) -> Path:
    """scripts/ plus pyproject.toml -- what ty reads, and nothing else.

    Not the whole tree: the ontology, the examples and robot.jar are megabytes ty
    never opens, and this copy is made once per case.
    """
    work = Path(tmp) / "fmo"
    (work / "scripts").mkdir(parents=True)
    for name in SCRIPTS:
        shutil.copy(ROOT / "scripts" / name, work / "scripts" / name)
    shutil.copy(ROOT / "pyproject.toml", work / "pyproject.toml")
    # Resolved, because ty finds first-party modules by locating the project that
    # contains the files it was handed. On macOS the temp dir is /var/folders/...,
    # a symlink to /private/var/..., and the two spellings read as different
    # directories: every sibling import fails and the baseline fails with it.
    return work.resolve()


def run_ty(work: Path, ty: list[str]) -> tuple[int, str]:
    paths = sorted(str(p) for p in (work / "scripts").glob("*.py"))
    proc = subprocess.run(ty + paths, cwd=work, capture_output=True,
                          text=True, encoding="utf-8")
    return proc.returncode, proc.stdout + proc.stderr


def run_case(name: str, rel: str | None, find: str | None, replace: str,
             rule: str, expect: str, ty: list[str]) -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        work = workspace(tmp)
        if rel is None:
            # A file that is not there yet, which is the point of the case.
            (work / "scripts" / "zz_added_script.py").write_text(replace, encoding="utf-8")
        else:
            target = work / "scripts" / rel
            text = target.read_text(encoding="utf-8")
            if find is None or text.count(find) != 1:
                count = 0 if find is None else text.count(find)
                print(f"  SETUP FAIL [{name}]: anchor found {count} times in {rel}")
                return False
            target.write_text(text.replace(find, replace), encoding="utf-8")
        code, output = run_ty(work, ty)
        if code == 0:
            print(f"  FAIL [{name}]: ty passed but should have failed")
            return False
        if rule not in output:
            print(f"  FAIL [{name}]: failed on the wrong rule, wanted {rule!r}")
            print("         " + "\n         ".join(output.splitlines()[:3]))
            return False
        if expect not in output:
            print(f"  FAIL [{name}]: right rule, but {expect!r} is not in the message")
            return False
        print(f"  ok   [{name}]")
        return True


def make_cases() -> list[str]:
    """The three claims about the target rather than about ty."""
    out: list[str] = []
    if shutil.which("make") is None:
        return ["make not found, so the typecheck target went unverified"]

    # The hazard the guard exists for, asserted rather than assumed. It has to be
    # asserted somewhere with nothing to check: `ty check` given no paths falls back
    # to scanning the project, so running it in ROOT would exit 0 having checked all
    # 18 scripts, which proves nothing about the empty case.
    ty = ty_command()
    with tempfile.TemporaryDirectory() as tmp:
        bare = Path(tmp) / "fmo"
        bare.mkdir(parents=True)
        shutil.copy(ROOT / "pyproject.toml", bare / "pyproject.toml")
        bare = bare.resolve()
        proc = subprocess.run(ty, cwd=bare, capture_output=True,
                              text=True, encoding="utf-8")
    if proc.returncode != 0:
        out.append("ty with nothing to check no longer exits 0; the guard's reason is stale")
    else:
        print("  ok   [ty with nothing to check exits 0, which is what the guard is for]")

    # Run, not `make -n`: the guard is a recipe line, so a dry run prints it and
    # exits 0. It fails before the recipe reaches poetry, so running it is cheap.
    proc = subprocess.run(["make", "typecheck", "PYSCRIPTS="],
                          cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    if proc.returncode == 0:
        out.append("make typecheck accepted an empty file list, so it can pass vacuously")
    else:
        print("  ok   [make typecheck refuses an empty file list]")

    # `make -n` here: the claim is about the command make would run, and running
    # it for real would just be `make typecheck` a second time.
    proc = subprocess.run(["make", "-n", "typecheck"],
                          cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    missing = [s for s in SCRIPTS if f"scripts/{s}" not in proc.stdout]
    if proc.returncode != 0:
        out.append("make -n typecheck failed on the unmodified tree")
    elif missing:
        out.append(f"make typecheck does not check every script: {missing} missing")
    elif not SCRIPTS:
        out.append("scripts/ holds no .py files, so the file-list claim proved nothing")
    else:
        print(f"  ok   [make typecheck names all {len(SCRIPTS)} scripts in scripts/]")
    return out


def main() -> int:
    ty = ty_command()
    if not ty:
        print("SKIP test_typecheck: ty is not installed. Run `make setup`.")
        return 0

    # Baseline: the unmodified copy must type check, or a non-zero exit below could
    # be any pre-existing error rather than the one the case injected.
    with tempfile.TemporaryDirectory() as tmp:
        code, output = run_ty(workspace(tmp), ty)
    if code != 0:
        print("BASELINE FAIL: scripts/ does not type check on the unmodified tree")
        print(output)
        return 1
    print("  ok   [baseline: ty passes on the clean tree]")

    results = [run_case(*case, ty) for case in CASES]
    problems = make_cases()
    for problem in problems:
        print(f"  FAIL [{problem}]")

    passed = sum(results) + 3 - len(problems)
    total = len(results) + 3
    print(f"\n{passed}/{total} typecheck negative tests passed")
    if all(results) and not problems:
        print("OK")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
