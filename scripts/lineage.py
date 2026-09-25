#!/usr/bin/env python3
"""Version lineage: each release names the one before it, and no released IRI goes dark.

ThermalEdge pins FMO terms by digest. The digest says a term moved; it cannot say
that a term was retired, or what replaced it -- ksh:expirationTime was deleted outright
in 0.7.0 and a consumer holding it found nothing at the IRI. ADR 0003 sets the rules;
this enforces them against the PRIOR VERSION, read out of git history:

  prior version   each module's owl:priorVersion names the version before this one
  continuity      every term declared or tombstoned at the prior version is still
                  declared, or tombstoned, now -- tombstones are forever, so checking
                  one version back holds the whole history by induction
  tombstone form  owl:deprecated true, the old label, a skos:historyNote, and no
                  declaration or axiom that would still type data; any
                  dcterms:isReplacedBy names a declared term
  no use          no example, export, shape or query names a retired term

The prior version comes from history, not from a tag, because a stack of unmerged
versions has none: tags mark releases for consumers, and no check depends on one.
A shallow clone cannot answer and fails rather than skipping.

Run: python3 scripts/lineage.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS, SKOS

sys.path.insert(0, str(Path(__file__).resolve().parent))
from registry import ONTOLOGY_PREFIXES, OUR_NS, ROOT  # noqa: E402

OURS = ("core.ttl", "weather.ttl", "kalshi.ttl", "fmo.ttl")
BASE = "https://w3id.org/forecast-market-ontology/"
DECLARED_AS = (OWL.Class, OWL.ObjectProperty, OWL.DatatypeProperty, OWL.AnnotationProperty,
               OWL.NamedIndividual, RDFS.Datatype)
# What a tombstone must not keep: each would still type or constrain data.
LIVE_AXIOMS = (RDF.type, RDFS.domain, RDFS.range, RDFS.subClassOf, RDFS.subPropertyOf,
               OWL.equivalentClass, OWL.inverseOf, OWL.disjointWith)
VERSION = re.compile(r'owl:versionInfo\s+"([^"]+)"')


class LineageError(Exception):
    """Lineage could not be established -- not a finding about the ontology."""


def ours(term: object) -> bool:
    return isinstance(term, URIRef) and str(term).startswith(OUR_NS)


def declared(g: Graph) -> set[URIRef]:
    return {s for t in DECLARED_AS for s in g.subjects(RDF.type, t) if isinstance(s, URIRef) and ours(s)}


def tombstones(g: Graph) -> set[URIRef]:
    return {s for s in g.subjects(OWL.deprecated, Literal(True)) if isinstance(s, URIRef) and ours(s)}


def curie(term: URIRef) -> str:
    for prefix, ns in ONTOLOGY_PREFIXES.items():
        if str(term).startswith(ns):
            return f"{prefix}:{str(term)[len(ns):]}"
    return str(term)


def audit(prior: Graph, head: Graph, prior_version: str, texts: dict[str, str]) -> list[str]:
    """Every lineage finding for head against prior. Raises LineageError on nothing to check."""
    findings: list[str] = []

    headers = [URIRef(BASE + m.removesuffix(".ttl")) for m in OURS]
    for onto in headers:
        if (onto, RDF.type, OWL.Ontology) not in head:
            raise LineageError(f"no owl:Ontology header for {onto}, so there is no lineage to check")
        want = URIRef(f"{onto}/{prior_version}")
        got = sorted(str(o) for o in head.objects(onto, OWL.priorVersion))
        if got != [str(want)]:
            findings.append(f"{onto} owl:priorVersion is {got or 'absent'}, expected {want}")

    released = declared(prior) | tombstones(prior)
    if not released:
        raise LineageError(f"no term declared at {prior_version}, so continuity checked nothing")
    now_declared, now_retired = declared(head), tombstones(head)
    for term in sorted(released - now_declared - now_retired, key=str):
        findings.append(f"{curie(term)} was released in {prior_version} and is gone without a tombstone")

    for term in sorted(now_retired, key=str):
        name = curie(term)
        for p in LIVE_AXIOMS:
            if (term, p, None) in head:
                findings.append(f"{name} is a tombstone but keeps {head.qname(p)}")
        if not list(head.objects(term, RDFS.label)):
            findings.append(f"{name} is a tombstone without its rdfs:label")
        if not list(head.objects(term, SKOS.historyNote)):
            findings.append(f"{name} is a tombstone without a skos:historyNote saying when and why")
        for repl in head.objects(term, DCTERMS.isReplacedBy):
            if repl not in now_declared:
                findings.append(f"{name} is replaced by {repl}, which is not declared")

    if not texts:
        raise LineageError("no example, shape or query file to scan for retired terms")
    for term in sorted(now_retired, key=str):
        pattern = re.compile(rf"(?:{re.escape(curie(term))}|<{re.escape(str(term))}>)(?![\w-])")
        for path, text in sorted(texts.items()):
            if pattern.search(text):
                findings.append(f"{path} uses retired term {curie(term)}")
    return findings


def git(*args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    if proc.returncode != 0:
        raise LineageError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def version_of(text: str) -> str | None:
    found = VERSION.search(text)
    return found.group(1) if found else None


def prior_release(current: str) -> tuple[str, str]:
    """The newest ancestor commit whose fmo.ttl states a version other than `current`."""
    if git("rev-parse", "--is-shallow-repository").strip() == "true":
        raise LineageError("shallow clone: the prior version is in history this checkout lacks "
                           "(CI needs fetch-depth: 0)")
    for sha in git("log", "--format=%H", "--", "src/fmo.ttl").split():
        text = subprocess.run(["git", "show", f"{sha}:src/fmo.ttl"], cwd=ROOT,
                              capture_output=True, text=True, encoding="utf-8").stdout
        version = version_of(text)
        if version and version != current:
            return version, sha
    raise LineageError(f"no commit states a version before {current}")


def modules_at(sha: str | None) -> Graph:
    g = Graph()
    for name in OURS:
        text = (ROOT / "src" / name).read_text(encoding="utf-8") if sha is None \
            else git("show", f"{sha}:src/{name}")
        g.parse(data=text, format="turtle")
    return g


def scanned_texts() -> dict[str, str]:
    files = [*sorted((ROOT / "examples").rglob("*.ttl")), *sorted((ROOT / "shapes").glob("*.ttl")),
             *sorted((ROOT / "queries").glob("*.rq"))]
    return {str(p.relative_to(ROOT)): p.read_text(encoding="utf-8") for p in files}


def main() -> int:
    try:
        current = version_of((ROOT / "src" / "fmo.ttl").read_text(encoding="utf-8"))
        if current is None:
            raise LineageError("src/fmo.ttl states no owl:versionInfo")
        prior_version, sha = prior_release(current)
        head, prior = modules_at(None), modules_at(sha)
        texts = scanned_texts()
        findings = audit(prior, head, prior_version, texts)
    except LineageError as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1
    print(f"{current} against prior version {prior_version} ({sha[:7]}): "
          f"{len(declared(prior) | tombstones(prior))} released term(s), "
          f"{len(tombstones(head))} tombstone(s), {len(texts)} file(s) scanned")
    if findings:
        print(f"\nFAILED ({len(findings)}):", file=sys.stderr)
        for f in findings:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
