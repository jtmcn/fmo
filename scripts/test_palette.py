#!/usr/bin/env python3
"""Negative tests for the palette audit in `make diagram-check`.

Each case copies viz/, reintroduces one defect, and asserts the audit fails
naming it. Most are the values this audit replaced, so a revert is caught; the
last two prove the audit refuses to pass having read nothing. The source tree is
never modified.

Run: python3 scripts/test_palette.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import palette  # noqa: E402
from registry import ROOT  # noqa: E402

VIZ = ROOT / "viz"

# (name, file under viz/, find, replace, substring the audit must report)
CASES = [
    ("muted text back in the pre-audit grey", "style.css",
     "--ink-mute:  #58666B;", "--ink-mute:  #7C8A90;",
     "light: `.field h2` text --ink-mute on --paper is 2.78:1"),
    ("a text rule using the mark-only grey", "style.css",
     ".panel-curie {\n  margin: 0 0 22px;\n  font: 400 12px/1 var(--f-mono);\n  color: var(--ink-mute);",
     ".panel-curie {\n  margin: 0 0 22px;\n  font: 400 12px/1 var(--f-mono);\n  color: var(--graphite);",
     "`.panel-curie` text --graphite on --paper"),
    ("the bfo ring below 3:1 in light", "style.css",
     "--graphite:  #738187;", "--graphite:  #7C8A90;",
     "light: bfo mark --graphite on --paper is 2.78:1"),
    ("dark blue back above the lightness band", "style.css",
     "--cold:     #5B98D7;", "--cold:     #6BA8E8;",
     "dark: wx mark --cold OKLCH L 0.716"),
    ("dark grey inseparable from red under CVD", "style.css",
     "    --graphite: #58666C;", "    --graphite: #6C7A80;",
     "dark: ksh and bfo are dE"),
    ("the two dark blocks drifting apart", "style.css",
     "--warm: #DE6A75; --graphite", "--warm: #E8737E; --graphite",
     "the two dark blocks disagree on: warm"),
    ("text set in a module colour outside the stanza", "style.css",
     ".panel-kicker {\n  margin: 0 0 7px;\n  color: var(--ink-soft);",
     ".panel-kicker {\n  margin: 0 0 7px;\n  color: var(--warm);",
     "`.panel-kicker` sets text in module colour --warm"),
    ("a relation label filled in its module colour", "src/graph.js",
     "e.lab = el('text', { class: 'e-lab' });",
     "e.lab = el('text', { class: 'e-lab', fill: color(e.a) });",
     "graph.js:"),
    ("a text colour set from script", "src/ui.js",
     "  function show(n) {\n", "  function show(n) {\n    $('panel-title').style.color = 'red';\n",
     "ui.js:"),
    ("no light tokens to read", "style.css",
     ":root {\n  --paper:", ":root-gone {\n  --paper:",
     "no colour tokens found in the light block"),
    ("no module colours to read", "src/graph.js",
     "var COLOR = {", "var HUE = {",
     "no module colours found"),
]


def run(case: tuple[str, str, str, str, str]) -> str | None:
    name, rel, find, replace, expect = case
    with tempfile.TemporaryDirectory() as tmp:
        viz = Path(tmp) / "viz"
        shutil.copytree(VIZ, viz)
        target = viz / rel
        src = target.read_text(encoding="utf-8")
        if src.count(find) != 1:
            return f"injection point found {src.count(find)} times in {rel}"
        target.write_text(src.replace(find, replace), encoding="utf-8")
        errors, _ = palette.audit_viz(viz)
    if not any(expect in e for e in errors):
        return f"expected {expect!r}, got {errors or 'a pass'}"
    return None


def main() -> int:
    errors, summary = palette.audit_viz(VIZ)
    failed = 0
    if errors:
        print("FAIL  the unmodified viz/ does not pass:\n  " + "\n  ".join(errors))
        failed += 1
    else:
        print(f"ok    unmodified viz/ passes ({summary})")
    for case in CASES:
        why = run(case)
        print(("FAIL  " if why else "ok    ") + case[0] + (f": {why}" if why else ""))
        failed += bool(why)
    print(f"\n{len(CASES) - failed + (0 if errors else 1)}/{len(CASES) + 1} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
