#!/usr/bin/env python3
"""What counts as a usable reasoner, in one place, for Python and for make.

Two copies of this question existed and they answered it differently. The Python
checkers asked test_reason.robot_command(). The Makefile asked itself:

    ifdef ROBOT_JAR / $(wildcard robot.jar) / command -v robot

That is a question about files, not about runtimes. macOS ships a /usr/bin/java
stub that is present on every machine and exits 1, so on a machine holding
robot.jar and no JDK the two answers disagreed: `make axioms` skipped with a
notice while `make reason`, one target above it, ran `java -jar robot.jar` and
died on the stub. Same shape as the three ledgers that each grew their own copy of
one set of invariants, and the same fix -- one home, with the copies deleted
rather than corrected, because a rule enforced by memory is enforced wherever
someone remembered.

Asked two ways:

    from reasoner import robot_command      # the checkers ask directly
    $(PY) scripts/reasoner.py <label>       # a recipe asks, and gets a command

The CLI writes the resolved command to stdout and nothing else, so a recipe can
capture it with `cmd=$(...)`; every notice goes to stderr. An empty stdout means
"there is no reasoner", which is a recipe's cue to stop quietly.

Absence and breakage are answered differently, and that asymmetry is deliberate.
A reasoner that is merely missing is a skip: a machine without Java is what the
README describes and what `make setup` warns about. A reasoner the operator
*named* through $ROBOT_JAR and that does not run is a failure, because naming it
was a decision and a typo must not read as a machine without Java. This is the
same distinction check_axioms makes one layer in, between a reasoner that said
"no" and one that said nothing.

Resolution is deliberately not done at Makefile parse time. The probe starts a
JVM, which costs about half a second, and `make typecheck` should not pay it to
decide something it never asks.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from registry import ROOT  # noqa: E402

# A wedged JVM should not hang every reasoner target at startup, which is what an
# unbounded probe buys in exchange for the one it catches.
PROBE_TIMEOUT = 60


class ReasonerBroken(RuntimeError):
    """A reasoner was named and does not run, which is not the same as having none."""


def robot_command() -> tuple[list[str] | None, str]:
    """The ROBOT command, or None and the reason there is none.

    Resolution order, which the Makefile no longer keeps a second copy of:
    $ROBOT_JAR, then ./robot.jar, then `robot` on PATH.

    The command is run, not merely found. shutil.which("java") answered a question
    nobody asked -- the stub is present on every Mac -- and check_axioms therefore
    skipped nothing and reported 9 of 9 axiom pins verified against a JVM that never
    started. --version is the cheapest thing ROBOT will do that still needs the
    runtime, and it proves ROBOT rather than java, which is what every caller goes on
    to invoke.

    The reason is returned rather than printed because each caller owns its own
    sentence -- and it is returned at all because "no ROBOT that runs" told an
    operator nothing they could act on while the stub's own first line, "Unable to
    locate a Java Runtime", was captured and discarded three lines away.
    """
    explicit = os.environ.get("ROBOT_JAR")
    jar = explicit
    if not jar and (ROOT / "robot.jar").exists():
        jar = str(ROOT / "robot.jar")
    if jar:
        if not shutil.which("java"):
            if explicit:
                raise ReasonerBroken(f"ROBOT_JAR names {jar}, but no java is on PATH")
            return None, f"no java on PATH to run {jar}"
        command = ["java", "-jar", jar]
    else:
        found = shutil.which("robot")
        if not found:
            return None, ("no ROBOT found: set ROBOT_JAR, drop robot.jar in the repo "
                          "root, or put robot on PATH")
        command = [found]
    try:
        proc = subprocess.run([*command, "--version"], capture_output=True,
                              text=True, encoding="utf-8", timeout=PROBE_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired) as exc:
        why = f"{command[0]} could not be run: {exc}"
    else:
        if proc.returncode == 0:
            return command, ""
        detail = (proc.stderr or proc.stdout).strip().splitlines()
        why = (f"{' '.join(command)} --version exited {proc.returncode}"
               + (f": {detail[0]}" if detail else ""))
    if explicit:
        raise ReasonerBroken(why)
    return None, why


def main(argv: list[str]) -> int:
    """Print the command for a recipe to capture, or nothing for it to stop on.

    The command is printed space-separated, so a path holding a space would be split
    by the shell that captured it. That was already true of `ROBOT := java -jar
    $(ROBOT_JAR)`, and quoting here would not survive an unquoted expansion there.
    """
    label = argv[0] if argv else "reason"
    try:
        command, why = robot_command()
    except ReasonerBroken as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    if command is None:
        print(f"SKIP {label}: {why}", file=sys.stderr)
        return 0
    print(" ".join(command))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
