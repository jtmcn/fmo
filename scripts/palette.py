"""The map's colour tokens, audited off viz/style.css rather than restated.

Which token is text and which is a mark is read from how the stylesheet uses it:
a `color:` declaration is text, and so is a `fill:` in a rule that sets a font.
The module colours are read off graph.js's COLOR map, which is what paints the dots.
A text use of a mark-only token then fails on contrast without anyone having
listed it.

Thresholds and colour science follow the dataviz skill's validator: WCAG
contrast, and Euclidean OKLab distance x100 under Machado-Oliveira-Fernandes
(2009) protan/deutan simulation at severity 1.0.
"""

from __future__ import annotations

import itertools
import math
import re
from pathlib import Path

TEXT_MIN = 4.5          # WCAG AA, body text; the map's chrome is 9.5-12px
MARK_MIN = 3.0          # WCAG non-text contrast
CVD_FLOOR = 6.0         # legal because every dot also carries a label and a fill/ring
NORMAL_FLOOR = 15.0
BAND = {"light": (0.43, 0.77), "dark": (0.48, 0.67)}   # OKLCH L, hued marks only
CHROMA_FLOOR = 0.10
SURFACES = ("paper", "paper-hi")
# The pivot in ink and borrowed ground in graphite are neutral on purpose
# (CONTEXT.md, Style): lightness and fill separate them, not hue.
NEUTRAL = {"ink", "graphite"}

MACHADO = {
    "protan": ((0.152286, 1.052583, -0.204868),
               (0.114503, 0.786281, 0.099216),
               (-0.003882, -0.048116, 1.051998)),
    "deutan": ((0.367322, 0.860646, -0.227968),
               (0.280085, 0.672501, 0.047413),
               (-0.011820, 0.042940, 0.968881)),
}

Rgb = tuple[float, float, float]


def _lin(h: str) -> Rgb:
    def one(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    h = h.lstrip("#")
    r, g, b = (one(int(h[i:i + 2], 16) / 255) for i in (0, 2, 4))
    return r, g, b


def contrast(a: str, b: str) -> float:
    def lum(h: str) -> float:
        r, g, b_ = _lin(h)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b_
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _oklab(rgb: Rgb) -> Rgb:
    r, g, b = rgb
    l_ = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m_ = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s_ = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    return (0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
            1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
            0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_)


def oklch(h: str) -> tuple[float, float]:
    L, a, b = _oklab(_lin(h))
    return L, math.hypot(a, b)


def _simulate(h: str, kind: str) -> Rgb:
    rgb = _lin(h)
    r, g, b = (max(0.0, min(1.0, sum(m * c for m, c in zip(row, rgb))))
               for row in MACHADO[kind])
    return r, g, b


def delta_e(a: str, b: str, kind: str | None = None) -> float:
    pa = _simulate(a, kind) if kind else _lin(a)
    pb = _simulate(b, kind) if kind else _lin(b)
    return 100 * math.dist(_oklab(pa), _oklab(pb))


# ---- reading the stylesheet ---------------------------------------------------

BLOCKS = {
    "light": r':root\s*\{',
    "dark (media query)": r':root:not\(\[data-theme="light"\]\)\s*\{',
    "dark (data-theme)": r':root\[data-theme="dark"\]\s*\{',
}
HEX = re.compile(r"#[0-9A-Fa-f]{6}")


def _uncomment(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _tokens(css: str, opener: str) -> dict[str, str]:
    m = re.search(opener + r"([^}]*)\}", css)
    if not m:
        return {}
    # Whitespace inside a value is formatting: rgba(0, 0, 0, .5) is rgba(0,0,0,.5).
    return {k: "".join(v.split())
            for k, v in re.findall(r"--([\w-]+)\s*:\s*([^;]+);", m.group(1))}


def themes(css: str) -> tuple[dict[str, dict[str, str]], list[str]]:
    """Light and dark token sets, dark overlaid on light as the cascade does it."""
    css = _uncomment(css)
    blocks = {name: _tokens(css, rx) for name, rx in BLOCKS.items()}
    errors = [f"no colour tokens found in the {name} block"
              for name, toks in blocks.items() if not toks]
    media, attr = blocks["dark (media query)"], blocks["dark (data-theme)"]
    if media != attr:
        drift = sorted(k for k in media.keys() | attr.keys() if media.get(k) != attr.get(k))
        errors.append(f"the two dark blocks disagree on: {', '.join(drift)}")
    return {"light": blocks["light"], "dark": {**blocks["light"], **media}}, errors


def text_uses(css: str) -> list[tuple[str, str]]:
    """(selector, token) for every token the stylesheet sets text in."""
    out = []
    for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", _uncomment(css)):
        sel = " ".join(sel.split())
        for tok in re.findall(r"(?<![-\w])color\s*:\s*var\(--([\w-]+)\)", body):
            out.append((sel, tok))
        if re.search(r"(?<![-\w])font(?:-[\w]+)?\s*:", body):
            for tok in re.findall(r"(?<![-\w])fill\s*:\s*var\(--([\w-]+)\)", body):
                out.append((sel, tok))
    return out


def module_colours(graph_js: str) -> dict[str, str]:
    m = re.search(r"var COLOR = \{([^}]*)\}", graph_js)
    return dict(re.findall(r"(\w+):\s*'var\(--([\w-]+)\)'", m.group(1))) if m else {}


# Text colour set from script can't be seen by text_uses(); it has to go through
# a CSS class so the audit reads it.
JS_TEXT_COLOUR = re.compile(r"\.style\.color|(?<![-\w])color\s*:\s*var\(|el\('text',\s*\{[^}]*fill")


def audit(css: str, graph_js: str, scripts: dict[str, str]) -> tuple[list[str], str]:
    """Every failure found, and a one-line summary of what was checked."""
    by_theme, errors = themes(css)
    uses = text_uses(css)
    modules = module_colours(graph_js)
    if not uses:
        errors.append("no text colour declarations found in style.css")
    if not modules:
        errors.append("no module colours found in graph.js's COLOR map")

    for name, src in scripts.items():
        for m in JS_TEXT_COLOUR.finditer(src):
            line = src.count("\n", 0, m.start()) + 1
            errors.append(f"{name}:{line} sets a text colour in script; use a CSS class")

    # Identity rides a swatch beside the text, never the text itself. The stanza
    # is the exception: there the prefix colour is syntax highlighting.
    hued = set(modules.values()) - NEUTRAL
    for sel, tok in uses:
        if tok in hued and not sel.startswith(".ttl "):
            errors.append(f"`{sel}` sets text in module colour --{tok}; key it with a swatch")

    checked = 0
    for theme, toks in by_theme.items():
        def hex_of(t: str) -> str | None:
            v = toks.get(t, "")
            return v if HEX.fullmatch(v) else None

        for sel, tok in uses:
            fg = hex_of(tok)
            if fg is None:
                errors.append(f"{theme}: `{sel}` sets text in --{tok}, not a hex token")
                continue
            # A surface colour as text sits on an ink fill (.jump:hover).
            grounds = ["ink"] if tok in SURFACES else list(SURFACES)
            for g in grounds:
                bg = hex_of(g)
                checked += 1
                if bg and contrast(fg, bg) < TEXT_MIN:
                    errors.append(f"{theme}: `{sel}` text --{tok} on --{g} is "
                                  f"{contrast(fg, bg):.2f}:1, under {TEXT_MIN}:1")

        marks = {m: hex_of(t) for m, t in modules.items()}
        for m, t in modules.items():
            h, paper = marks[m], hex_of("paper")
            if h is None or paper is None:
                errors.append(f"{theme}: module {m}'s --{t} is not a hex token")
                continue
            checked += 1
            if contrast(h, paper) < MARK_MIN:
                errors.append(f"{theme}: {m} mark --{t} on --paper is "
                              f"{contrast(h, paper):.2f}:1, under {MARK_MIN}:1")
            if t not in NEUTRAL:
                L, C = oklch(h)
                lo, hi = BAND[theme]
                if not lo <= L <= hi:
                    errors.append(f"{theme}: {m} mark --{t} OKLCH L {L:.3f} outside {lo}-{hi}")
                if C < CHROMA_FLOOR:
                    errors.append(f"{theme}: {m} mark --{t} chroma {C:.3f} reads as grey")

        # Any two dots can sit side by side on a force layout: all pairs, not adjacent.
        for (m1, h1), (m2, h2) in itertools.combinations(marks.items(), 2):
            if h1 is None or h2 is None:
                continue
            checked += 1
            cvd = min(delta_e(h1, h2, "protan"), delta_e(h1, h2, "deutan"))
            if cvd < CVD_FLOOR:
                errors.append(f"{theme}: {m1} and {m2} are dE {cvd:.1f} apart under "
                              f"simulated colour blindness, under {CVD_FLOOR}")
            normal = delta_e(h1, h2)
            if normal < NORMAL_FLOOR:
                errors.append(f"{theme}: {m1} and {m2} are dE {normal:.1f} apart, "
                              f"under {NORMAL_FLOOR}")

    summary = (f"{len(uses)} text uses of {len({t for _, t in uses})} tokens and "
               f"{len(modules)} module colours, {checked} comparisons over 2 themes")
    if not checked:
        errors.append("the palette audit compared nothing")
    return errors, summary


def audit_viz(viz: Path) -> tuple[list[str], str]:
    src = viz / "src"
    scripts = {p.name: p.read_text(encoding="utf-8")
               for p in sorted(src.glob("*.js")) if p.name != "data.js"}
    return audit((viz / "style.css").read_text(encoding="utf-8"),
                 scripts.get("graph.js", ""), scripts)
