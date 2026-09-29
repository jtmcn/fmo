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
import os
import re
import subprocess
import sys
from functools import cache
from pathlib import Path

from rdflib import BNode, Graph, Literal, OWL, RDF, RDFS, URIRef
from rdflib.namespace import DCTERMS, SH, SKOS
from rdflib.paths import Path as PropertyPath
from rdflib.plugins.sparql import prepareQuery

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger as L  # noqa: E402
import palette  # noqa: E402
import validate as V  # noqa: E402
from registry import MODULES, OUR_NS, QUERIES, ROOT, SHAPES, SRC, examples  # noqa: E402

VIZ = ROOT / "viz"
BUILD = ROOT / "build"

NS = {
    "https://w3id.org/forecast-market-ontology/core#": "fm",
    "https://w3id.org/forecast-market-ontology/weather#": "wx",
    "https://w3id.org/forecast-market-ontology/kalshi#": "ksh",
    "http://purl.obolibrary.org/obo/": "bfo",
    "http://qudt.org/schema/qudt/": "qudt",
    "http://www.w3.org/2002/07/owl#": "owl",
    "http://www.w3.org/ns/prov#": "prov",
}
# What the panel calls each borrowed prefix. Shipped in the page data, so a prefix
# with no name fails diagram-check rather than falling back to the bare prefix.
EXTERNAL_NAME = {"bfo": "Basic Formal Ontology", "qudt": "QUDT", "owl": "OWL",
                 "prov": "PROV-O"}
PREFIX = {pre: full for full, pre in NS.items()}
# These three are minted here; anything else is borrowed ground.
MINTED = ("fm", "wx", "ksh")
FILE_OF = {"fm": "core.ttl", "wx": "weather.ttl", "ksh": "kalshi.ttl"}

# The one export profile there is. Its lens answers "does an export have
# everything the shapes ask for" without a diff.
PROFILE_LABEL = "ThermalEdge export"

# Datatype properties whose domain is left open on purpose, so nothing on the map
# carries them. Pinned rather than counted: a fifth means a domain was dropped or
# turned into an unnamed restriction, and that property would quietly leave every
# class panel with no count moving.
OPEN_DATATYPES = ["fm:identifier", "fm:realizedValue", "fm:referenceTime",
                  "wx:stationIdentifier"]


def curie(term) -> str | None:
    """Prefixed name, or None for terms outside the namespaces we draw."""
    if not isinstance(term, URIRef):
        return None
    s = str(term)
    for full, pre in NS.items():
        if s.startswith(full):
            return f"{pre}:{s[len(full):]}"
    return None


def iri(c: str) -> URIRef:
    """The IRI behind a prefixed name curie() made."""
    pre, local = c.split(":", 1)
    return URIRef(PREFIX[pre] + local)


def is_minted(c: str) -> bool:
    return c.split(":")[0] in MINTED


def parents(g: Graph) -> dict[str, set[str]]:
    """Named superclasses by prefixed name, self-loops dropped."""
    up: dict[str, set[str]] = {}
    for s, o in g.subject_objects(RDFS.subClassOf):
        a, b = curie(s), curie(o)
        if a and b and a != b:
            up.setdefault(a, set()).add(b)
    return up


def stanzas(path: Path) -> dict[str, str]:
    """Map prefixed name -> its verbatim Turtle blocks, joined in file order.

    A term can be stated in more than one block -- FM-0015 lists the API field
    names in their own table further down -- and the panel shows all of them.

    A stanza starts at column 0 and runs to the next column-0 line, except that
    triple-quoted strings in this repo wrap to column 0, so track them. A column-0
    comment ends the stanza before it too, or section banners land in the panel.
    """
    out: dict[str, str] = {}
    current: list[str] = []
    key: str | None = None
    in_quote = False

    def close(k: str, lines: list[str]) -> None:
        block = "\n".join(lines).rstrip()
        out[k] = out[k] + "\n\n" + block if k in out else block

    for line in path.read_text(encoding="utf-8").splitlines():
        head = line.split()[0] if line[:1].strip() else ""
        opens = head and not head.startswith(("@", "<"))
        if opens and not in_quote:
            if key:
                close(key, current)
            key = None if head.startswith("#") else (head if ":" in head else None)
            current = []
        if key is not None:
            current.append(line)
        if line.count('"""') % 2:
            in_quote = not in_quote

    if key:
        close(key, current)
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

    def history(s) -> list[dict]:
        """Change and history notes, oldest wording first. ADR 0003 requires the
        change note on a term redefined in place; it is the only field saying why."""
        out = [{"kind": kind, "text": " ".join(str(v).split())}
               for kind, pred in (("changed", SKOS.changeNote), ("history", SKOS.historyNote))
               for v in g.objects(s, pred)]
        return sorted(out, key=lambda h: (h["kind"], h["text"]))

    def fields(s) -> list[str]:
        """The API field names a property is read from (FM-0015), as skos:notation."""
        return sorted(str(v) for v in g.objects(s, SKOS.notation))

    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    def touch(cid: str) -> str:
        """Register a node lazily; borrowed ground gets no stanza."""
        if cid not in nodes:
            nodes[cid] = {
                "id": cid, "module": cid.split(":")[0], "minted": False,
                "label": cid.split(":")[1], "def": None, "note": None,
                "example": None, "ttl": None,
                # Two different things, and the panel must not say one for the other:
                # a shape names this class, versus an edge a shape walks lands on it.
            }
        return cid

    for s in g.subjects(RDF.type, OWL.Class):
        cid = curie(s)
        if not cid or not is_minted(cid):
            continue
        touch(cid)
        nodes[cid].update({
            "minted": True,
            "label": text(s, RDFS.label) or cid.split(":")[1],
            "def": text(s, SKOS.definition),
            "note": text(s, SKOS.scopeNote),
            "example": text(s, SKOS.example),
            "history": history(s),
            "ttl": src_text[cid.split(":")[0]].get(cid),
        })

    # Hierarchy: named superclasses only. Restrictions are blank nodes and already
    # legible in the stanza. Minted files only, so a bridge is drawn whatever its subject.
    for s, o in minted_graph().subject_objects(RDFS.subClassOf):
        a, b = curie(s), curie(o)
        if a and b and a != b:
            edges.append({"s": touch(a), "t": touch(b), "k": "sub"})

    def ends(term) -> list[str]:
        """Endpoints a domain or range draws to: a named class, or each member of
        a union. Anything else (an unnamed restriction, no declaration) draws none."""
        c = curie(term)
        if c:
            return [c]
        u = g.value(term, OWL.unionOf) if term is not None else None
        return [x for x in (curie(m) for m in g.items(u)) if x] if u else []

    def borrowed_supers(p) -> list[str]:
        """Super-properties outside FMO: the panel lists them, the map draws none."""
        return sorted(c for c in map(curie, g.objects(p, RDFS.subPropertyOf))
                      if c and not is_minted(c))

    properties: dict[str, dict] = {}
    for p in g.subjects(RDF.type, OWL.ObjectProperty):
        pid = curie(p)
        if not pid or not is_minted(pid):
            continue
        d, r = ends(g.value(p, RDFS.domain)), ends(g.value(p, RDFS.range))
        properties[pid] = {
            "label": text(p, RDFS.label) or pid.split(":")[1],
            "def": text(p, SKOS.definition),
            "note": text(p, SKOS.scopeNote),
            "history": history(p),
            "fields": fields(p),
            "ttl": src_text[pid.split(":")[0]].get(pid),
            "dom": d, "rng": r, "supers": borrowed_supers(p),
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
        if not pid or not is_minted(pid):
            continue
        carriers = ends(g.value(p, RDFS.domain))
        datatypes[pid] = {
            "label": text(p, RDFS.label) or pid.split(":")[1],
            "def": text(p, SKOS.definition),
            "note": text(p, SKOS.scopeNote),
            "history": history(p),
            "fields": fields(p),
            "ttl": src_text[pid.split(":")[0]].get(pid),
            "range": datatype(g.value(p, RDFS.range)),
            "supers": borrowed_supers(p),
            # Same distinction the object properties draw: a domain left open on
            # purpose has nothing to hang from, and is not a lost attachment.
            "open": not carriers,
            # Borrowed ground can carry one of ours -- fm:instantDateTime hangs off
            # a BFO instant nothing else in the ontology touches, so no node exists
            # for it. The panel skips a carrier it cannot find; check() does not.
            "on": carriers,
        }

    # The map is laid out from the outline's rows, which also give every subClassOf,
    # second parents included, so the missing edges come from there.
    tree = outline(g, nodes, lambda u: text(u, RDFS.label))
    have = {(e["s"], e["t"]) for e in edges if e["k"] == "sub"}
    for r in tree:
        touch(r["id"])
        r["on"] = True
        r.pop("label", None)
        if r["via"] and (r["id"], r["via"]) not in have:
            have.add((r["id"], r["via"]))
            edges.append({"s": r["id"], "t": touch(r["via"]), "k": "sub"})
    place(tree, nodes)

    # Tombstones (ADR 0003). Search resolves a retired name to what replaced it,
    # so an old IRI in someone's data still lands somewhere on the map.
    retired: dict[str, dict] = {}
    for t in g.subjects(OWL.deprecated, Literal(True)):
        tid = curie(t)
        if not tid or not is_minted(tid):
            continue
        retired[tid] = {
            "label": text(t, RDFS.label) or tid.split(":")[1],
            "to": sorted(c for c in map(curie, g.objects(t, DCTERMS.isReplacedBy)) if c),
            "note": text(t, SKOS.historyNote),
        }

    # The export profile, read off the shapes rather than restated here: whatever
    # teh: targets or walks is what an export has to carry.
    sh = Graph()
    sh.parse(SHAPES, format="turtle")
    # sh:class narrows a path's range, so it names a class the export must carry just
    # as sh:targetClass does. Reading only the targets missed it.
    named = set(sh.objects(None, SH.targetClass)) | set(sh.objects(None, SH["class"]))
    walked = set(sh.objects(None, SH.path))
    # Targeting the reader does not understand. A shape using one of these constrains
    # a term the map never lights, and nothing downstream would notice -- the README
    # promises the opposite, so fail here instead.
    unread = sorted(str(t).rsplit("#", 1)[-1] for t in
                    (SH.targetNode, SH.targetObjectsOf, SH.targetSubjectsOf)
                    if (None, t, None) in sh)
    unread += ["implicit class target" for s_ in sh.subjects(RDF.type, SH.NodeShape)
               if (s_, RDF.type, RDFS.Class) in sh]
    lenses = [lens(
        "export", PROFILE_LABEL, f"the {PROFILE_LABEL} shapes", "constrained",
        named={c for c in map(curie, named) if c},
        paths={c for c in map(curie, walked) if c}, edges=edges,
        # curie() returns None for a blank-node path or a namespace the map does
        # not draw; a term quietly leaving the lens is what this count makes loud.
        unmapped=sum(1 for t in named | walked if curie(t) is None), unread=unread,
        group="Export profile")]
    lenses += question_lenses(g, set(nodes), set(properties) | set(datatypes), edges)
    lenses.append(coverage_lens(g, nodes, edges))

    # Disjointness never reaches the canvas -- it relates classes that share nothing
    # to draw -- so it lives on the panel. Stated three ways in OWL; all three read.
    disjoint: dict[str, set[str]] = {}

    def apart(members: list) -> None:
        names = [c for c in map(curie, members) if c]
        for a_ in names:
            disjoint.setdefault(a_, set()).update(b_ for b_ in names if b_ != a_)

    for s_, o in g.subject_objects(OWL.disjointWith):
        apart([s_, o])
    for ax in g.subjects(RDF.type, OWL.AllDisjointClasses):
        members = g.value(ax, OWL.members)
        if members is not None:
            apart(list(g.items(members)))
    for _, u in g.subject_objects(OWL.disjointUnionOf):
        apart(list(g.items(u)))
    for cid, n in nodes.items():
        n["disjoint"] = sorted(disjoint.get(cid, ()))

    # Orphans: classes nothing relates to, by a drawn relation, a literal or one of
    # our OWL restrictions, on the class or any ancestor (BFO's own don't count).
    related = {c for e in edges if e["k"] == "rel" for c in (e["s"], e["t"])}
    related |= {c for v in datatypes.values() for c in v["on"]}
    related |= {c for s_, o in g.subject_objects(RDFS.subClassOf)
                if isinstance(o, BNode) and g.value(o, OWL.onProperty) is not None
                for c in [curie(s_)] if c and is_minted(c)}
    # ...and both ends of one: wx:SnowDepth's restriction relates wx:SnowCover too.
    for s_, o in g.subject_objects(RDFS.subClassOf):
        if isinstance(o, BNode) and (sid := curie(s_)) and is_minted(sid):
            for pred in (OWL.someValuesFrom, OWL.allValuesFrom, OWL.onClass, OWL.hasValue):
                c = curie(g.value(o, pred))
                if c:
                    related.add(c)
    supers = parents(g)

    def lineage(c: str) -> set[str]:
        seen, stack = {c}, [c]
        while stack:
            for b_ in supers.get(stack.pop(), ()):
                if b_ not in seen:
                    seen.add(b_)
                    stack.append(b_)
        return seen

    lenses.append(lens(
        "unrelated", "Unrelated classes", "", "unrelated",
        # entity itself is left out: fm:isAbout ranges over it, and a relation any
        # class at all can stand in says nothing about this one.
        named={c for c, n in nodes.items()
               if n["minted"] and not (lineage(c) - {ROOT_CLASS}) & related},
        paths=set(), edges=edges, group="Structure",
        line="related to nothing: joined to the map only by rdfs:subClassOf",
        # No orphans is the goal, so this lens lighting nothing is a pass.
        goal_empty=True,
        about="Minted classes nothing relates to: no relation, literal property or OWL "
              "restriction, on the class or any ancestor. Joined to the rest only by "
              "rdfs:subClassOf: orphan terms."))

    # BFO local names are opaque numerics; borrow their labels so the map reads.
    for n in nodes.values():
        if not n["minted"]:
            uri = iri(n["id"])
            n["label"] = text(uri, RDFS.label) or n["id"].split(":", 1)[1]
            n["def"] = text(uri, SKOS.definition) or text(uri, RDFS.comment)
        n["deg"] = sum(1 for e in edges if n["id"] in (e["s"], e["t"]))

    return {
        "tree": tree,
        "grid": {"row": ROW, "col": COL, "depth": max(r["d"] for r in tree)},
        "version": text(URIRef("https://w3id.org/forecast-market-ontology/core"),
                        OWL.versionInfo) or "",
        "nodes": sorted(nodes.values(), key=lambda n: n["id"]),
        "edges": edges,
        "properties": properties,
        "datatypes": dict(sorted(datatypes.items())),
        "retired": dict(sorted(retired.items())),
        "lenses": lenses,
        "external": EXTERNAL_NAME,
    }


def minted_graph() -> Graph:
    """The minted files alone, so an axiom can be told apart from an import's."""
    m = Graph()
    for f in FILE_OF.values():
        m.parse(SRC / f, format="turtle")
    return m


def query_terms(o, seen: set[int] | None = None) -> set[URIRef]:
    """Every IRI in a parsed query's algebra -- what it matches on, never what its
    comments mention. Property paths (a/rdfs:subClassOf*) are walked too."""
    seen = set() if seen is None else seen
    if id(o) in seen:
        return set()
    seen.add(id(o))
    if isinstance(o, URIRef):
        return {o}
    if isinstance(o, dict):
        parts = list(o.values())
    elif isinstance(o, (list, tuple, set)):
        parts = list(o)
    elif isinstance(o, PropertyPath):
        parts = list(vars(o).values())
    else:
        return set()
    return set().union(*(query_terms(x, seen) for x in parts)) if parts else set()


def question_lenses(g: Graph, classes: set[str], props: set[str], edges: list[dict]) -> list[dict]:
    """One lens per competency question: the classes its query matches on and the
    properties it walks. Plus one for the terms no question touches -- the book's
    "every term traces back to a competency question", made visible rather than
    enforced, since class-coverage-expectations.json is where classes are classified.
    """
    prefixes = (QUERIES / "prefixes.txt").read_text(encoding="utf-8")
    out: list[dict] = []
    for f in sorted(QUERIES.glob("cq*.rq")):
        text_ = f.read_text(encoding="utf-8")
        head = re.match(r"# (CQ\w+)\. (.*?)\n#\s*\n", text_, re.S)
        cq = head.group(1) if head else f.stem
        question = " ".join(l.lstrip("# ") for l in head.group(2).splitlines()) if head else ""
        used = {c for c in map(curie, query_terms(prepareQuery(prefixes + text_).algebra))
                if c and is_minted(c)}
        # Anything the map cannot draw must at least be a live individual: a query
        # matching on a retired or undeclared term answers a question about nothing.
        stale = sorted(c for c in used if (iri(c), OWL.deprecated, Literal(True)) in g
                       or (c not in classes and c not in props
                           and (iri(c), RDF.type, OWL.NamedIndividual) not in g))
        slug = f.stem.split("-", 1)[1].replace("-", " ") if "-" in f.stem else ""
        out.append(lens(f.stem, f"{cq} · {slug}", cq, "used",
                        named=used & classes, paths=used & props, edges=edges,
                        about=question, stale=stale, group="Competency questions"))
    touched = {c for ln in out for c in ln["named"] + ln["reached"]}
    walked = {p for ln in out for p in ln["paths"]}
    minted = {c for c in classes if is_minted(c)}
    # Untouched properties are listed, not lit: as paths they would light their ends.
    out.append(lens("no-question", "No question", "any competency question", "untouched",
                    named=minted - touched, paths=set(), edges=edges,
                    about="Minted classes that no competency question uses or reaches.",
                    unwalked=sorted(p for p in props if is_minted(p) and p not in walked),
                    goal_empty=True, group="Competency questions"))
    return out


COVERAGE_SAYS = {
    "direct": "An example instantiates it directly.",
    "subclass": "No example instantiates it directly, but one instantiates a subclass.",
    "schema": "Its individuals are declared in src/, so no example could add one.",
}


def coverage_lens(g: Graph, nodes: dict[str, dict], edges: list[dict]) -> dict:
    """The classes the examples exercise, and for every other minted class, the
    reason its class-coverage-expectations.json entry gives.

    Which classes count as exercised is validate.exercise(), the function
    check_class_coverage itself uses, so the map and the check cannot disagree.
    Each minted node gets a `coverage` record for its panel.
    """
    ex = Graph()
    ex += g
    for path in examples():
        ex.parse(path, format="turtle")
    direct, reached, schema = ({c for c in map(curie, xs) if c} for xs in V.exercise(g, ex))
    ledger = L.load(V.COVERAGE_LEDGER, V.COVERAGE_CATEGORIES)
    for n in nodes.values():
        if not n["minted"]:
            continue
        cid = n["id"]
        state = ("schema" if cid in schema else "direct" if cid in direct
                 else "subclass" if cid in reached else None)
        cov: dict = {"state": state, "says": COVERAGE_SAYS.get(state or "")}
        if state is None:
            for cat in V.COVERAGE_CATEGORIES:
                entry = ledger.get(cat, {}).get(cid)
                if isinstance(entry, dict):
                    cov = {"state": cat, "says": entry.get("reason", ""),
                           "checked": entry.get("checked")}
                    break
        n["coverage"] = cov
    return lens("coverage", "Example coverage", "the example data", "exercised",
                named=(direct | reached) & set(nodes), paths=set(), edges=edges,
                about="Classes an example instantiates, directly or through a subclass. "
                      "Select a dimmed class to read why no example does.",
                group="Example data")


def lens(key: str, label: str, source: str, named_as: str, *, named: set[str],
         paths: set[str], edges: list[dict], **extra) -> dict:
    """A lens: a named subset of the map that lights while the rest dims.

    The ends of a path it walks light too, as *reached* rather than named: a range
    can be wider than the class a shape actually requires. `named_as` is the word
    for what it names.
    """
    reached = {c for e in edges if e.get("p") in paths for c in (e["s"], e["t"])} - named
    words = {"named": named_as, "reached": "reached", "path": "walked"}
    return {"id": key, "label": label, "source": source, "words": words,
            "named": sorted(named), "reached": sorted(reached), "paths": sorted(paths),
            **extra}


ROOT_CLASS = "bfo:BFO_0000001"   # entity
ROW, COL = 120, 34                # layout grid: one row per depth, one column per leaf
# Families read forecast, pivot, market, left to right; borrowed ground (3) last.
# PROV after that: at 3, prov:Agent sorted by label into fm:Agent's siblings.
SIDE_ORDER = {"wx": 0, "fm": 1, "ksh": 2, "prov": 4}
# Edge crossings among the subClassOf drawn at rest. Pinned, not minimised: a
# change that tangles the tree fails here instead of looking fine in review.
MAX_CROSSINGS = 12


def place(rows: list[dict], nodes: dict[str, dict]) -> None:
    """Tree positions from the outline's rows: y is depth, leaves take columns in
    reading order, and a parent sits over the middle of its children. Computed here
    rather than simulated in the page, so diagram-check can count what it draws."""
    full = [r for r in rows if not r["dup"]]
    kids: dict[str, list[str]] = {}
    for r in full:
        if r["via"]:
            kids.setdefault(r["via"], []).append(r["id"])
    x: dict[str, float] = {}
    leaves = 0
    for r in full:                       # depth-first, so leaves arrive in order
        if not kids.get(r["id"]):
            x[r["id"]] = leaves * COL
            leaves += 1
    for r in reversed(full):             # children always before their parent
        if kids.get(r["id"]):
            x[r["id"]] = sum(x[c] for c in kids[r["id"]]) / len(kids[r["id"]])
    mid = (leaves - 1) * COL / 2
    for r in full:
        if r["id"] in nodes:
            nodes[r["id"]]["px"] = round(x[r["id"]] - mid, 1)
            nodes[r["id"]]["py"] = r["d"] * ROW


def crossings(nodes: list[dict], edges: list[dict]) -> int:
    """Pairs of subClassOf segments that cross; edges sharing an end never count."""
    at = {n["id"]: (n["px"], n["py"]) for n in nodes}
    segs = [(e["s"], e["t"]) for e in edges if e["k"] == "sub" and e["s"] != e["t"]]

    def ccw(p, q, r) -> bool:
        return (r[1] - p[1]) * (q[0] - p[0]) > (q[1] - p[1]) * (r[0] - p[0])

    n = 0
    for i, (a, b) in enumerate(segs):
        for c, d in segs[i + 1:]:
            if {a, b} & {c, d}:
                continue
            A, B, C, D = at[a], at[b], at[c], at[d]
            if ccw(A, C, D) != ccw(B, C, D) and ccw(A, B, C) != ccw(A, B, D):
                n += 1
    return n


def outline(g: Graph, nodes: dict[str, dict], label) -> list[dict]:
    """The outline's rows, in reading order: the subsumption tree from bfo:entity
    down to every class on the map, depth-first, children by side then label.

    It climbs from every node through the imports to entity, so BFO's own skeleton
    (process under occurrent under entity) is walked too -- depth means distance
    from entity or nothing -- and build() puts those rows on the map. A class with
    two parents is listed under each; the second listing is a `dup` and is not
    expanded again.
    """
    up = parents(g)
    keep: set[str] = set()
    stack = list(nodes)
    while stack:
        c = stack.pop()
        if c not in keep:
            keep.add(c)
            stack += up.get(c, ())

    down: dict[str, list[str]] = {}
    for c in keep:
        for parent in up.get(c, set()) & keep:
            down.setdefault(parent, []).append(c)

    def name(c: str) -> str:
        if c in nodes:
            return nodes[c]["label"]
        return str(label(iri(c)) or c.split(":", 1)[1])

    rows: list[dict] = []
    seen: set[str] = set()

    def walk(c: str, depth: int, via: str | None) -> None:
        row = {"id": c, "d": depth, "via": via, "dup": c in seen, "on": c in nodes}
        if not row["on"]:
            row["label"] = name(c)
        rows.append(row)
        if row["dup"]:
            return
        seen.add(c)
        for child in sorted(down.get(c, []), key=lambda x: (
                SIDE_ORDER.get(x.split(":")[0], 3), name(x).lower(), x)):
            walk(child, depth + 1, c)

    for root in sorted(c for c in keep if not up.get(c, set()) & keep):
        walk(root, 0, None)
    return rows


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
        return "<style>\n" + (VIZ / href.group(1)).read_text(encoding="utf-8") + "\n</style>"

    def script(m):
        return "<script>\n" + (VIZ / m.group(1)).read_text(encoding="utf-8") + "\n</script>"

    html = re.sub(r"<link\b[^>]*>", link, html)
    return re.sub(r'<script\b[^>]*\bsrc="([^"]+)"[^>]*></script>', script, html)


MIN_HIT_PX = 12   # radius: a 24px target, the dataviz minimum


@cache
def fresh_positions() -> dict[str, dict[str, list]]:
    """Every class's position from two separate builds, under different hash seeds:
    set iteration order is where a layout would drift between runs."""
    out = {}
    for seed in ("1", "2"):
        run = subprocess.run([sys.executable, __file__, "--positions"], check=True,
                             capture_output=True, text=True,
                             env={**os.environ, "PYTHONHASHSEED": seed})
        out[seed] = json.loads(run.stdout)
    return out


def hit_px(graph_js: str) -> int | None:
    """The screen-pixel reach graph.js's hit test gives every node, or None."""
    m = re.search(r"var HIT_PX = (\d+);", graph_js)
    return int(m.group(1)) if m else None


def check(data: dict, html: str) -> int:
    """The smallest thing that fails if extraction silently breaks."""
    # data.js and the modules share window.FMO; a data key named like a module is
    # overwritten by it before anything reads the data.
    modules = {p.stem for p in (VIZ / "src").glob("*.js") if p.stem != "data"}
    clash = sorted(set(data) & modules)
    assert not clash, f"data key shares a name with a viz module: {clash}"

    minted = [n for n in data["nodes"] if n["minted"]]
    assert len(minted) > 90, f"expected ~102 minted classes, got {len(minted)}"
    assert len(data["properties"]) > 40, f"only {len(data['properties'])} properties"

    # Read off the minted files by its own parse, as raw IRIs: reusing curie() would
    # check the generator against itself. Minted means not under imports/.
    asserted = Graph()
    for m in MODULES:
        if not m.startswith("imports/"):
            asserted.parse(SRC / m, format="turtle")
    g = Graph()
    for m in MODULES:
        g.parse(SRC / m, format="turtle")
    subs = {(s_, o) for s_, o in asserted.subject_objects(RDFS.subClassOf)
            if isinstance(s_, URIRef) and isinstance(o, URIRef) and s_ != o}
    ups = {(s_, o) for s_, o in asserted.subject_objects(RDFS.subPropertyOf)
           if isinstance(o, URIRef)}
    unnamed = sorted({str(t) for pair in subs | ups for t in pair
                      if not any(str(t).startswith(ns) for ns in NS)})
    assert not unnamed, f"asserted in a minted file, but no prefix the map can name: {unnamed[:5]}"
    bridges = {(s_, o) for s_, o in subs if not str(s_).startswith(OUR_NS)}
    assert bridges, "no bridge asserted in a minted file: the comparison below proves nothing"
    drawn_subs = {(iri(e["s"]), iri(e["t"])) for e in data["edges"] if e["k"] == "sub"}
    undrawn = sorted(f"{s_} ⊑ {o}" for s_, o in subs - drawn_subs)
    assert not undrawn, f"subClassOf asserted in a minted file but not drawn: {undrawn[:5]}"

    # The node set: minted classes, bridge ends, object-property domains and ranges
    # (a union's members), and everything they climb to. All seeded from the files.
    seeds = {c for c in asserted.subjects(RDF.type, OWL.Class)
             if isinstance(c, URIRef) and str(c).startswith(OUR_NS)}
    seeds |= {t for pair in bridges for t in pair}
    for p in asserted.subjects(RDF.type, OWL.ObjectProperty):
        for end_ in (asserted.value(p, RDFS.domain), asserted.value(p, RDFS.range)):
            u = asserted.value(end_, OWL.unionOf) if end_ is not None else None
            seeds |= ({end_} if isinstance(end_, URIRef)
                      else {m for m in asserted.items(u) if isinstance(m, URIRef)} if u else set())
    want_nodes: set = set()
    stack = list(seeds)
    while stack:
        c = stack.pop()
        if c not in want_nodes:
            want_nodes.add(c)
            stack += [o for o in g.objects(c, RDFS.subClassOf)
                      if isinstance(o, URIRef) and o != c]
    have_nodes = {iri(n["id"]) for n in data["nodes"]}
    assert have_nodes == want_nodes, \
        f"node set is not the minted classes, bridge ends, domains, ranges and their " \
        f"ancestors: {sorted(map(str, have_nodes ^ want_nodes))[:5]}"

    # Every borrowed module on the map is named in the page data, not by its prefix.
    nameless = sorted({n["module"] for n in data["nodes"] if not n["minted"]}
                      - set(data.get("external", {})))
    assert not nameless, f"borrowed prefix with no display name in the page data: {nameless}"

    # Super-properties outside FMO, per property, as the minted files assert them.
    want_supers = {(s_, o) for s_, o in ups if not str(o).startswith(OUR_NS)}
    assert want_supers, "no super-property outside FMO asserted: the comparison proves nothing"
    shown_supers = {(iri(pid), iri(c)) for v in (data["properties"], data["datatypes"])
                    for pid, t in v.items() for c in t.get("supers", [])}
    assert shown_supers == want_supers, \
        f"super-properties outside FMO not carried to the panel: " \
        f"{sorted(f'{a_} ⊑ {b_}' for a_, b_ in shown_supers ^ want_supers)[:5]}"

    missing = [n["id"] for n in minted if not n["ttl"]]
    assert not missing, f"no Turtle stanza found for: {missing[:5]}"
    # Every stanza is one complete statement, so it ends at a full stop. A block
    # that runs on past its own is how the swallowed section banners looked.
    ragged = [n["id"] for n in minted if not n["ttl"].rstrip().endswith(".")]
    assert not ragged, f"stanza does not end at its full stop: {ragged[:5]}"
    # A later block for the same term (an API field table) once replaced the
    # declaration instead of joining it; the stanza must still say what the term is.
    stanzas_ = {**{n["id"]: n["ttl"] for n in minted},
                **{k: v["ttl"] for k, v in data["properties"].items()},
                **{k: v.get("ttl") for k, v in data["datatypes"].items()}}
    undeclared = [t for t, ttl in stanzas_.items()
                  if not re.search(rf"^{re.escape(t)}\s+a\s", ttl or "", re.M)]
    assert not undeclared, f"stanza lost its declaration: {undeclared[:5]}"
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
                     if is_minted(c) and c not in drawn_ids})
    assert not orphan, f"carries a datatype property but is not on the map: {orphan[:5]}"
    left_open = sorted(pid for pid, v in dts.items() if v["open"])
    assert left_open == OPEN_DATATYPES, \
        f"the set of domain-less datatype properties changed: {left_open}"

    # Every lens has to land on the map and light something. A term a lens names
    # and the map cannot show is exactly the hole the lens exists to make visible.
    known = drawn_ids | set(data["properties"]) | set(dts)
    assert data["lenses"], "no lenses built"
    for ln in data["lenses"]:
        name = ln["label"]
        # A lens listing what is wrong is empty when nothing is; every other lens
        # lighting nothing means its reader found nothing to read.
        assert ln["named"] or ln["paths"] or ln.get("goal_empty"), \
            f"the {name} lens lights nothing"
        assert not ln.get("unmapped"), \
            f"{ln['unmapped']} {name} term(s) outside the namespaces the map draws"
        assert not ln.get("unread"), f"the {name} reader does not understand: {ln['unread']}"
        assert not ln.get("stale"), f"{name} matches on a retired or undeclared term: {ln['stale']}"
        absent = [t for t in ln["named"] + ln["reached"] + ln["paths"] if t not in known]
        assert not absent, f"{name} term absent from the map: {absent}"
        stray = [p for p in ln["paths"] if p not in data["properties"] and p not in dts]
        assert not stray, f"{name} path is neither an object nor a datatype property: {stray}"
        # Named or merely reached, never both: the panel says something different for
        # each, and saying "constrained" of a range narrowed elsewhere names the wrong class.
        both = sorted(set(ln["named"]) & set(ln["reached"]))
        assert not both, f"{name}: tagged as named and reached at once: {both}"
        ends = {c for e in data["edges"] if e.get("p") in ln["paths"] for c in (e["s"], e["t"])}
        assert set(ln["reached"]) == ends - set(ln["named"]), \
            f"{name}: reached classes are not the ends of the paths it walks"
    # Every minted class says where it stands with the examples; an unexercised one
    # with no ledger entry would show an empty field, which validate also refuses.
    unplaced = sorted(n["id"] for n in minted if not (n.get("coverage") or {}).get("state"))
    assert not unplaced, f"minted class with no example-coverage state: {unplaced[:5]}"
    cov = next(ln for ln in data["lenses"] if ln["id"] == "coverage")
    exercised = sorted(n["id"] for n in minted if n["coverage"]["state"] in ("direct", "subclass"))
    assert sorted(set(cov["named"]) & {n["id"] for n in minted}) == exercised, \
        "the coverage lens and the panel's coverage states disagree"

    walked = {p for ln in data["lenses"] if ln["id"].startswith("cq") for p in ln["paths"]}
    untouched = next(ln for ln in data["lenses"] if ln["id"] == "no-question")
    unwalked = sorted(p for p in (*data["properties"], *dts) if p not in walked)
    listed = set(untouched.get("unwalked", []))
    assert untouched.get("unwalked") == unwalked, \
        f"properties no question walks not listed: {sorted(set(unwalked) ^ listed)[:5]}"

    asked = sorted(f.stem for f in QUERIES.glob("cq*.rq"))
    have = sorted(ln["id"] for ln in data["lenses"] if ln["id"].startswith("cq"))
    assert asked == have, f"competency questions without a lens: {sorted(set(asked) - set(have))}"
    prof = next(ln for ln in data["lenses"] if ln["id"] == "export")
    assert prof["named"] and prof["paths"], f"no shapes read from {SHAPES.name}"
    lit = len(prof["named"]) + len(prof["reached"])
    prof_rel = [p for p in prof["paths"] if p in data["properties"]]

    # Self-contained means self-contained: nothing left to fetch, nothing unresolved.
    remote = re.findall(r'(?:src|href)="(?://|https?:)[^"]*"', html)
    assert not remote, f"built file still fetches: {remote[:3]}"
    assert "<script src" not in html and "</script>" in html, "inlining did not run"

    # Notes, field names and tombstones are counted again straight off the graph:
    # a panel that silently stops showing them looks exactly like a term without any.
    terms = {**{n["id"]: n for n in minted}, **data["properties"], **dts}
    noted = {c for p in (SKOS.changeNote, SKOS.historyNote) for c in map(curie, g.subjects(p, None))
             if c is not None and c in terms}
    shown = {tid for tid, t in terms.items() if t.get("history")}
    assert noted == shown, f"change/history notes not carried to the panel: {sorted(noted ^ shown)}"
    notations = sum(1 for s_, _ in g.subject_objects(SKOS.notation) if curie(s_) in terms)
    carried = sum(len(t.get("fields", [])) for t in terms.values())
    assert notations == carried, f"{notations} API field names on the map's terms, {carried} carried"
    tombs = {c for c in map(curie, g.subjects(OWL.deprecated, Literal(True)))
             if c and is_minted(c)}
    assert tombs == set(data["retired"]), \
        f"tombstones not indexed for search: {sorted(tombs ^ set(data['retired']))}"
    stranded = [t for t, v in data["retired"].items()
                if not v["to"] or any(x not in terms for x in v["to"])]
    assert not stranded, f"retired term resolves to nothing on the map: {stranded}"

    # The outline is the keyboard path to every class, so every class must be in it
    # once in full, under every parent it has, at a depth its parent's row explains.
    rows = data["tree"]
    roots = [r["id"] for r in rows if r["via"] is None]
    assert roots == [ROOT_CLASS], f"outline roots are {roots}, not {ROOT_CLASS} alone"
    full = [r["id"] for r in rows if not r["dup"]]
    missing = sorted({n["id"] for n in data["nodes"]} - set(full))
    assert not missing, f"not in the outline: {missing[:5]}"
    twice = sorted({c for c in full if full.count(c) > 1})
    assert not twice, f"expanded more than once in the outline: {twice}"
    listed = {(r["id"], r["via"]) for r in rows}
    unlisted = sorted((e["s"], e["t"]) for e in data["edges"]
                      if e["k"] == "sub" and (e["s"], e["t"]) not in listed)
    assert not unlisted, f"subClassOf with no outline row: {unlisted[:5]}"
    depth: dict[str, int] = {}
    for r in rows:
        want = 0 if r["via"] is None else depth.get(r["via"], -2) + 1
        assert r["d"] == want, f"{r['id']} under {r['via']} at depth {r['d']}, expected {want}"
        if not r["dup"]:
            depth[r["id"]] = r["d"]

    # Disjointness read a second way, by SPARQL, and compared pair for pair.
    pairs = {tuple(sorted((a_, b_))) for n in data["nodes"] for a_, b_ in
             ((n["id"], o) for o in n.get("disjoint", []))}
    stated: set[tuple[str, str]] = set()
    for row in g.query("""
        PREFIX owl: <http://www.w3.org/2002/07/owl#>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        SELECT ?a ?b WHERE {
          { ?a owl:disjointWith ?b } UNION
          { ?ax a owl:AllDisjointClasses ; owl:members ?l .
            ?l rdf:rest*/rdf:first ?a . ?l rdf:rest*/rdf:first ?b } UNION
          { ?c owl:disjointUnionOf ?l .
            ?l rdf:rest*/rdf:first ?a . ?l rdf:rest*/rdf:first ?b }
          FILTER (?a != ?b) }"""):
        a_, b_ = curie(row[0]), curie(row[1])  # type: ignore[index]
        if a_ and b_ and (a_ in drawn_ids or b_ in drawn_ids):
            stated.add((min(a_, b_), max(a_, b_)))
    assert pairs == stated, f"disjoint pairs not carried to the panel: {sorted(pairs ^ stated)[:5]}"

    # The drawn tree: every class on its depth's row, few enough crossings, and the
    # same picture every build.
    unplaced_ = sorted(n["id"] for n in data["nodes"] if "px" not in n)
    assert not unplaced_, f"no position for: {unplaced_[:5]}"
    off_row = sorted(n["id"] for n in data["nodes"] if n["py"] != depth[n["id"]] * ROW)
    assert not off_row, f"not on its depth's row: {off_row[:5]}"
    crossed = crossings(data["nodes"], data["edges"])
    assert crossed <= MAX_CROSSINGS, \
        f"{crossed} subClassOf crossings, over the pinned {MAX_CROSSINGS}"
    drawn_at = {n["id"]: [n["px"], n["py"]] for n in data["nodes"]}
    for seed, fresh in fresh_positions().items():
        moved = sorted(c for c in drawn_at.keys() | fresh.keys() if drawn_at.get(c) != fresh.get(c))
        assert not moved, f"layout differs from a build under PYTHONHASHSEED={seed}: {moved[:5]}"

    # A pointer target of at least 24px across, whatever the dot's size.
    reach = hit_px((VIZ / "src" / "graph.js").read_text(encoding="utf-8"))
    assert reach is not None and reach >= MIN_HIT_PX, \
        f"graph.js HIT_PX is {reach}; a node's target must reach {MIN_HIT_PX}px from its centre"

    # Contrast and colour-blind separation, read off the stylesheet the page ships.
    bad, palette_summary = palette.audit_viz(VIZ)
    assert not bad, "palette audit failed:\n  " + "\n  ".join(bad)

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
          f"{prof['label']} fully covered ({lit} classes lit, "
          f"{len(prof_rel)} relations, "
          f"{len(prof['paths']) - len(prof_rel)} literal properties), "
          f"pivot intact, all stanzas found, nothing remote")
    print(f"OK: {len(shown)} terms show change/history notes, {carried} API field names, "
          f"{len(tombs)} tombstones resolve to a replacement")
    print(f"OK: palette, {palette_summary}")
    states = [n["coverage"]["state"] for n in minted]
    print(f"OK: lenses, {len(have)} competency questions, "
          f"{len(untouched['named'])} minted classes and {len(unwalked)} properties "
          f"no question touches; coverage "
          + ", ".join(f"{k} {states.count(k)}" for k in
                      ("direct", "subclass", "schema", *V.COVERAGE_CATEGORIES)))
    lonely = next(ln for ln in data["lenses"] if ln["id"] == "unrelated")
    print(f"OK: structure, {len(pairs)} disjoint pairs on the panel, "
          f"{len(lonely['named'])} minted classes nothing relates to: {', '.join(lonely['named'])}")
    print(f"OK: layout, {len(data['nodes'])} classes on {data['grid']['depth'] + 1} rows, "
          f"{crossed} subClassOf crossings (ceiling {MAX_CROSSINGS})")
    print(f"OK: outline, {len(rows)} rows under {ROOT_CLASS}, "
          f"{sum(r['dup'] for r in rows)} second listings, "
          f"{sum(not r['on'] for r in rows)} rows off the map")
    return 0


def main() -> int:
    data = build()
    if "--positions" in sys.argv:
        print(json.dumps({n["id"]: [n["px"], n["py"]] for n in data["nodes"]}))
        return 0
    (VIZ / "src" / "data.js").write_text(
        # </script> inside a definition would close the inlined block early.
        "window.FMO = " + json.dumps(data, indent=1).replace("</", "<\\/") + ";\n", encoding="utf-8")
    html = inline((VIZ / "index.html").read_text(encoding="utf-8"))

    if "--check" in sys.argv:
        return check(data, html)

    BUILD.mkdir(exist_ok=True)
    out = BUILD / "ontology.html"
    out.write_text(html, encoding="utf-8")
    n_min = sum(1 for n in data["nodes"] if n["minted"])
    print(f"{out.relative_to(ROOT)}: {n_min} minted classes, "
          f"{len(data['nodes']) - n_min} external, {len(data['edges'])} edges, "
          f"{len(data['properties'])} object and {len(data['datatypes'])} datatype "
          f"properties ({out.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
