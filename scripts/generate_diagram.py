#!/usr/bin/env python3
"""Generate the interactive ontology map.

Writes viz/src/data.js from the ontology modules, then inlines the viz/ frontend
into a single self-contained build/ontology.html that opens by double-clicking.

The frontend is real files under viz/, not strings in here: adding a feature means
editing .js with syntax highlighting. This script only produces data and staples
the parts together.

Usage:
    python3 scripts/generate_diagram.py           # build/ontology.html
    python3 scripts/generate_diagram.py --check   # assert extraction is sane
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from rdflib import Graph, OWL, RDF, RDFS, URIRef
from rdflib.namespace import SH, SKOS

sys.path.insert(0, str(Path(__file__).resolve().parent))
from registry import MODULES, ROOT, SHAPES, SRC  # noqa: E402

VIZ = ROOT / "viz"
BUILD = ROOT / "build"

NS = {
    "https://w3id.org/forecast-market-ontology/core#": "fm",
    "https://w3id.org/forecast-market-ontology/weather#": "wx",
    "https://w3id.org/forecast-market-ontology/kalshi#": "ksh",
    "http://purl.obolibrary.org/obo/": "bfo",
    "http://qudt.org/schema/qudt/": "qudt",
    "http://www.w3.org/2002/07/owl#": "owl",
}
# These three are minted here; anything else is borrowed ground.
MINTED = ("fm", "wx", "ksh")
FILE_OF = {"fm": "core.ttl", "wx": "weather.ttl", "ksh": "kalshi.ttl"}

# The one export profile there is. Terms it constrains get marked so the map can
# answer "does an export have everything the shapes ask for" without a diff.
PROFILE_LABEL = "ThermalEdge export"


def curie(term) -> str | None:
    """Prefixed name, or None for terms outside the namespaces we draw."""
    if not isinstance(term, URIRef):
        return None
    s = str(term)
    for full, pre in NS.items():
        if s.startswith(full):
            return f"{pre}:{s[len(full):]}"
    return None


def stanzas(path: Path) -> dict[str, str]:
    """Map prefixed name -> its verbatim Turtle block.

    A stanza starts at column 0 and runs to the next column-0 line, except that
    triple-quoted strings in this repo wrap to column 0, so track them. A column-0
    comment ends the stanza before it too, or section banners land in the panel.
    """
    out: dict[str, str] = {}
    current: list[str] = []
    key: str | None = None
    in_quote = False

    for line in path.read_text().splitlines():
        head = line.split()[0] if line[:1].strip() else ""
        opens = head and not head.startswith(("@", "<"))
        if opens and not in_quote:
            if key:
                out[key] = "\n".join(current).rstrip()
            key = None if head.startswith("#") else (head if ":" in head else None)
            current = []
        if key is not None:
            current.append(line)
        if line.count('"""') % 2:
            in_quote = not in_quote

    if key:
        out[key] = "\n".join(current).rstrip()
    return out


def build() -> dict:
    g = Graph()
    for m in MODULES:
        g.parse(SRC / m, format="turtle")

    src_text = {p: stanzas(SRC / f) for p, f in FILE_OF.items()}

    def text(s, pred):
        """Prose, unwrapped. Turtle sources hard-wrap at ~90 columns; keeping those
        breaks would re-wrap the panel at whatever width the .ttl happened to use.
        Blank lines survive as paragraph breaks."""
        v = g.value(s, pred)
        if not v:
            return None
        paras = re.split(r"\n\s*\n", str(v).strip())
        return "\n\n".join(" ".join(p.split()) for p in paras)

    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    def touch(cid: str) -> str:
        """Register a node lazily; external terms get a stub."""
        if cid not in nodes:
            nodes[cid] = {
                "id": cid, "module": cid.split(":")[0], "minted": False,
                "label": cid.split(":")[1], "def": None, "note": None,
                "example": None, "ttl": None, "profile": False,
            }
        return cid

    for s in g.subjects(RDF.type, OWL.Class):
        cid = curie(s)
        if not cid or cid.split(":")[0] not in MINTED:
            continue
        touch(cid)
        nodes[cid].update({
            "minted": True,
            "label": text(s, RDFS.label) or cid.split(":")[1],
            "def": text(s, SKOS.definition),
            "note": text(s, SKOS.scopeNote),
            "example": text(s, SKOS.example),
            "ttl": src_text[cid.split(":")[0]].get(cid),
        })

    # Hierarchy: named superclasses only. Restrictions are blank nodes and already
    # legible in the stanza, so drawing them would duplicate without adding.
    for s, o in g.subject_objects(RDFS.subClassOf):
        a, b = curie(s), curie(o)
        if a and b and a in nodes and nodes[a]["minted"]:
            edges.append({"s": a, "t": touch(b), "k": "sub"})

    def ends(term) -> list[str]:
        """Endpoints a domain or range draws to: a named class, or each member of
        a union. Anything else (an unnamed restriction, no declaration) draws none."""
        c = curie(term)
        if c:
            return [c]
        u = g.value(term, OWL.unionOf) if term is not None else None
        return [x for x in (curie(m) for m in g.items(u)) if x] if u else []

    properties: dict[str, dict] = {}
    for p in g.subjects(RDF.type, OWL.ObjectProperty):
        pid = curie(p)
        if not pid or pid.split(":")[0] not in MINTED:
            continue
        d, r = ends(g.value(p, RDFS.domain)), ends(g.value(p, RDFS.range))
        properties[pid] = {
            "label": text(p, RDFS.label) or pid.split(":")[1],
            "def": text(p, SKOS.definition),
            "note": text(p, SKOS.scopeNote),
            "ttl": src_text[pid.split(":")[0]].get(pid),
            # Left open on purpose in the ontology, so there is no edge to draw;
            # check() uses this to tell that apart from an extraction failure.
            "open": not (d and r),
        }
        # touch() both ends: a class no subClassOf edge happened to reach is still
        # a real endpoint, and dropping the relation loses it silently.
        for a in d:
            for b in r:
                edges.append({"s": touch(a), "t": touch(b), "k": "rel", "p": pid})

    def datatype(term) -> str:
        """The datatype's short name. A faceted range -- xsd:decimal held to 0..1 --
        is a blank node, and the base type it restricts is what a reader wants."""
        if term is not None and not isinstance(term, URIRef):
            term = g.value(term, OWL.onDatatype)
        return str(term).rsplit("#", 1)[-1] if term is not None else "literal"

    # Datatype properties end at a literal, so there is no far class to draw an edge
    # to. They hang off the class that carries them instead, and the panel lists them.
    datatypes: dict[str, dict] = {}
    for p in g.subjects(RDF.type, OWL.DatatypeProperty):
        pid = curie(p)
        if not pid or pid.split(":")[0] not in MINTED:
            continue
        carriers = ends(g.value(p, RDFS.domain))
        datatypes[pid] = {
            "label": text(p, RDFS.label) or pid.split(":")[1],
            "def": text(p, SKOS.definition),
            "note": text(p, SKOS.scopeNote),
            "ttl": src_text[pid.split(":")[0]].get(pid),
            "range": datatype(g.value(p, RDFS.range)),
            # Same distinction the object properties draw: a domain left open on
            # purpose has nothing to hang from, and is not a lost attachment.
            "open": not carriers,
            # Borrowed ground can carry one of ours -- fm:instantDateTime hangs off
            # a BFO instant nothing else in the ontology touches, so no node exists
            # for it. The panel skips a carrier it cannot find; check() does not.
            "on": carriers,
        }

    # The export profile, read off the shapes rather than restated here: whatever
    # teh: targets or walks is what an export has to carry.
    sh = Graph()
    sh.parse(SHAPES, format="turtle")
    prof_classes = {c for c in map(curie, sh.objects(None, SH.targetClass)) if c}
    prof_paths = {c for c in map(curie, sh.objects(None, SH.path)) if c}
    for cid in prof_classes & set(nodes):
        nodes[cid]["profile"] = True
    for table in (properties, datatypes):
        for pid, v in table.items():
            v["profile"] = pid in prof_paths
    for e in edges:
        e["profile"] = e.get("p") in prof_paths

    # BFO local names are opaque numerics; borrow their labels so the map reads.
    inverse = {pre: full for full, pre in NS.items()}
    for n in nodes.values():
        if not n["minted"]:
            pre, local = n["id"].split(":", 1)
            uri = URIRef(inverse[pre] + local)
            n["label"] = text(uri, RDFS.label) or local
            n["def"] = text(uri, SKOS.definition) or text(uri, RDFS.comment)
        n["deg"] = sum(1 for e in edges if n["id"] in (e["s"], e["t"]))

    return {
        "version": text(URIRef("https://w3id.org/forecast-market-ontology/core"),
                        OWL.versionInfo) or "",
        "nodes": sorted(nodes.values(), key=lambda n: n["id"]),
        "edges": edges,
        "properties": properties,
        "datatypes": dict(sorted(datatypes.items())),
        "profile": {
            "label": PROFILE_LABEL,
            "classes": sorted(prof_classes),
            "paths": sorted(prof_paths),
        },
    }


def inline(html: str) -> str:
    """Fold the viz/ tree into one file: local <link> and <script src> become
    literals, remote ones are dropped. Attribute order is not assumed -- the
    webfont <link> writes href first, and matching on order let it through.

    Dropping the webfonts is what keeps the built file honest: it opens offline
    with no network call, on the system stack style.css already falls back to."""
    def link(m):
        href = re.search(r'href="([^"]+)"', m.group(0))
        if not href or "//" in href.group(1):
            return ""
        return "<style>\n" + (VIZ / href.group(1)).read_text() + "\n</style>"

    def script(m):
        return "<script>\n" + (VIZ / m.group(1)).read_text() + "\n</script>"

    html = re.sub(r"<link\b[^>]*>", link, html)
    return re.sub(r'<script\b[^>]*\bsrc="([^"]+)"[^>]*></script>', script, html)


def check(data: dict, html: str) -> int:
    """The smallest thing that fails if extraction silently breaks."""
    minted = [n for n in data["nodes"] if n["minted"]]
    assert len(minted) > 90, f"expected ~102 minted classes, got {len(minted)}"
    assert len(data["properties"]) > 40, f"only {len(data['properties'])} properties"

    missing = [n["id"] for n in minted if not n["ttl"]]
    assert not missing, f"no Turtle stanza found for: {missing[:5]}"
    # Every stanza is one complete statement, so it ends at a full stop. A block
    # that runs on past its own is how the swallowed section banners looked.
    ragged = [n["id"] for n in minted if not n["ttl"].rstrip().endswith(".")]
    assert not ragged, f"stanza does not end at its full stop: {ragged[:5]}"
    undocumented = [n["id"] for n in minted if not n["def"]]
    assert not undocumented, f"no definition for: {undocumented[:5]}"

    # A relation with both ends declared has to reach the map. Half the object
    # properties once drew nothing and the map still looked convincing.
    drawn = {e["p"] for e in data["edges"] if e["k"] == "rel"}
    lost = [p for p, v in data["properties"].items() if not v["open"] and p not in drawn]
    assert not lost, f"declared domain and range but no edge drawn: {lost[:5]}"

    # Datatype properties are the half of the vocabulary that ends at a literal.
    # They draw no edge, so nothing else here would notice them going missing.
    dts = data["datatypes"]
    assert len(dts) > 25, f"expected ~34 datatype properties, got {len(dts)}"
    for field in ("def", "ttl"):
        blank = [pid for pid, v in dts.items() if not v[field]]
        assert not blank, f"datatype property with no {field}: {blank[:5]}"
    drawn_ids = {n["id"] for n in data["nodes"]}
    orphan = sorted({c for v in dts.values() for c in v["on"]
                     if c.split(":")[0] in ("fm", "wx", "ksh") and c not in drawn_ids})
    assert not orphan, f"carries a datatype property but is not on the map: {orphan[:5]}"

    # The export profile has to land on the map. A term the shapes constrain and the
    # map cannot show is exactly the hole this tagging exists to make visible.
    prof = data["profile"]
    assert prof["classes"] and prof["paths"], f"no shapes read from {SHAPES.name}"
    known = drawn_ids | set(data["properties"]) | set(dts)
    absent = [t for t in prof["classes"] + prof["paths"] if t not in known]
    assert not absent, f"{prof['label']} term absent from the map: {absent}"
    tagged = sum(1 for n in data["nodes"] if n["profile"])
    assert tagged == len(prof["classes"]), \
        f"{len(prof['classes'])} targeted classes but {tagged} tagged"
    marked = sum(1 for t in (data["properties"], dts) for v in t.values() if v["profile"])
    assert marked == len(prof["paths"]), \
        f"{len(prof['paths'])} shape paths but {marked} tagged properties"

    # Self-contained means self-contained: nothing left to fetch, nothing unresolved.
    remote = re.findall(r'(?:src|href)="(?://|https?:)[^"]*"', html)
    assert not remote, f"built file still fetches: {remote[:3]}"
    assert "<script src" not in html and "</script>" in html, "inlining did not run"

    # The README's pivot: both sides must still reach the same proposition.
    rel = {(e["s"], e.get("p"), e["t"]) for e in data["edges"] if e["k"] == "rel"}
    for want in [("ksh:Market", "ksh:expressesProposition", "fm:Proposition"),
                 ("fm:Proposition", "fm:hasSubject", "fm:ObservationTarget")]:
        assert want in rel, f"pivot edge missing: {want}"

    # Every minted class reaches BFO by subClassOf -- validate.py's rule, redrawn.
    up: dict[str, list[str]] = {}
    for e in data["edges"]:
        if e["k"] == "sub":
            up.setdefault(e["s"], []).append(e["t"])
    for n in minted:
        seen: set[str] = set()
        stack = [n["id"]]
        while stack:
            c = stack.pop()
            if c not in seen:
                seen.add(c)
                stack += up.get(c, [])
        assert any(c.startswith("bfo:") for c in seen), f"{n['id']} does not reach BFO"

    print(f"OK: {len(minted)} classes, {len(data['properties'])} properties "
          f"({len(drawn)} drawn), {len(dts)} datatype properties, "
          f"{prof['label']} fully covered ({tagged} classes, {marked} properties), "
          f"pivot intact, all stanzas found, nothing remote")
    return 0


def main() -> int:
    data = build()
    (VIZ / "src" / "data.js").write_text(
        # </script> inside a definition would close the inlined block early.
        "window.FMO = " + json.dumps(data, indent=1).replace("</", "<\\/") + ";\n")
    html = inline((VIZ / "index.html").read_text())

    if "--check" in sys.argv:
        return check(data, html)

    BUILD.mkdir(exist_ok=True)
    out = BUILD / "ontology.html"
    out.write_text(html)
    n_min = sum(1 for n in data["nodes"] if n["minted"])
    print(f"{out.relative_to(ROOT)}: {n_min} minted classes, "
          f"{len(data['nodes']) - n_min} external, {len(data['edges'])} edges, "
          f"{len(data['properties'])} object and {len(data['datatypes'])} datatype "
          f"properties ({out.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
