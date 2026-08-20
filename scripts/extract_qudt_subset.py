#!/usr/bin/env python3
"""Extract the units this ontology uses from a QUDT checkout into a vendored subset.

QUDT ships ~60k triples of units and ~14k of quantity kinds. Importing all of that to
use sixteen units would swamp the ontology, so this pulls only what we reference,
preserving the authoritative IRIs, labels, symbols, conversion factors, dimension
vectors, and quantity-kind links.

Usage:
    git clone --depth 1 https://github.com/qudt/qudt-public-repo.git /tmp/qudt
    python3 scripts/extract_qudt_subset.py /tmp/qudt

Writes src/imports/qudt-subset.ttl. Re-run to refresh against a newer QUDT.

To add a unit, put it in UNITS below and re-run. Do not hand-edit the output: the
conversion factors are load-bearing and transcribing them by hand is how unit bugs
get in, which is the exact failure this module exists to prevent.
"""

from __future__ import annotations

import sys
from pathlib import Path

from rdflib import Graph, Namespace, URIRef, RDF, RDFS, OWL, Literal

QUDT = Namespace("http://qudt.org/schema/qudt/")
UNIT = Namespace("http://qudt.org/vocab/unit/")
QK = Namespace("http://qudt.org/vocab/quantitykind/")
DV = Namespace("http://qudt.org/vocab/dimensionvector/")

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "src" / "imports" / "qudt-subset.ttl"

# Units referenced by the weather and market modules. Temperature, precipitation
# depth, wind speed, pressure, humidity, and wind direction.
UNITS = [
    "DEG_F", "DEG_C", "K",                                  # temperature
    "IN", "MilliM", "CentiM",                               # precipitation depth
    "MI-PER-HR", "KN", "M-PER-SEC", "KiloM-PER-HR",         # wind speed
    "PA", "HectoPA", "MilliBAR", "IN_HG",                   # pressure
    "PERCENT",                                              # relative humidity
    "DEG",                                                  # wind direction
]

# Quantity kinds our units actually link to in QUDT source.
#
# Chosen by inspecting qudt:unitForQuantityKind rather than by picking the terms whose
# names read best, because QUDT's links here are uneven: pressure units link to
# ForcePerArea and not to quantitykind:Pressure, wind speed units link to Velocity and
# LinearVelocity but only M-PER-SEC links to Speed, and PERCENT links to 39 kinds none
# of which is RelativeHumidity. Quantity kind is therefore carried as documentation.
# Dimensional compatibility is checked against qudt:hasDimensionVector, which is
# complete and consistent across every unit we use.
QUANTITY_KINDS = [
    "Temperature", "Length", "Velocity", "LinearVelocity", "Speed",
    "ForcePerArea", "VapourPressure", "DimensionlessRatio", "PlaneAngle", "Angle",
]

# Predicates worth carrying. Everything else in QUDT (LaTeX expressions, UCUM codes,
# wikidata matches, per-system provenance) is noise for our purposes.
# qudt:ucumCode is omitted: its values carry the custom qudt:UCUMcs datatype, which would
# drag a datatype declaration into the subset for no benefit here. qudt:scalingOf is
# omitted because it points at base units we do not vendor (unit:RAD, unit:K), which would
# leave dangling references in a subset that is otherwise closed.
KEEP = {
    RDF.type, RDFS.label,
    QUDT.symbol, QUDT.conversionMultiplier, QUDT.conversionOffset,
    QUDT.hasDimensionVector, QUDT.unitForQuantityKind,
}


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    qudt_root = Path(sys.argv[1])
    units_file = qudt_root / "src/main/rdf/vocab/unit/VOCAB_QUDT-UNITS-ALL.ttl"
    qk_file = qudt_root / "src/main/rdf/vocab/quantitykinds/VOCAB_QUDT-QUANTITY-KINDS-ALL.ttl"
    for f in (units_file, qk_file):
        if not f.exists():
            print(f"not found: {f}\nIs {qudt_root} a qudt-public-repo checkout?", file=sys.stderr)
            return 1

    src = Graph()
    src.parse(units_file, format="turtle")
    src.parse(qk_file, format="turtle")
    print(f"source: {len(src)} triples")

    out = Graph()
    out.bind("qudt", QUDT)
    out.bind("unit", UNIT)
    out.bind("quantitykind", QK)
    out.bind("dimensionvector", DV)

    wanted = [UNIT[u] for u in UNITS] + [QK[q] for q in QUANTITY_KINDS]
    missing = [str(t) for t in wanted if (t, None, None) not in src]
    if missing:
        print("MISSING from QUDT:\n  " + "\n  ".join(missing), file=sys.stderr)
        return 1

    dim_vectors: set[URIRef] = set()
    for term in wanted:
        # QUDT carries each label twice, plain and @en. Keep one, preferring @en.
        labels = [o for o in src.objects(term, RDFS.label) if isinstance(o, Literal)]
        english = [o for o in labels if o.language == "en"]
        keep_label = (english or labels or [None])[0]

        for p, o in src.predicate_objects(term):
            if p not in KEEP:
                continue
            if p == RDFS.label and o != keep_label:
                continue
            # Keep quantity-kind links only for kinds we actually vendored, so the
            # subset stays closed and the compatibility check cannot silently pass
            # by pointing at a term that is not here.
            if p in (QUDT.unitForQuantityKind, QUDT.applicableUnit) and o not in wanted:
                continue
            out.add((term, p, o))
            if p == QUDT.hasDimensionVector:
                dim_vectors.add(o)

    # Carry the dimension vectors themselves so dimensional comparison is self-contained.
    for dvec in dim_vectors:
        for p, o in src.predicate_objects(dvec):
            if p in (RDF.type, RDFS.label):
                out.add((dvec, p, o))
        out.add((dvec, RDF.type, QUDT.QuantityKindDimensionVector))

    # Ontology header so the subset can be owl:imports-ed like any other module.
    subset_iri = URIRef("https://w3id.org/forecast-market-ontology/imports/qudt-subset")
    out.add((subset_iri, RDF.type, OWL.Ontology))
    out.add((subset_iri, RDFS.label, Literal("QUDT subset for FMO")))
    out.add((subset_iri, RDFS.comment, Literal(
        "Units and quantity kinds extracted from the QUDT public repo. "
        "Generated by scripts/extract_qudt_subset.py; do not hand-edit.")))
    # Declare every class our terms are instances of, so the bridge axioms in core.ttl
    # have something to attach to and no class arrives undeclared. QUDT types units with
    # more than qudt:Unit alone (qudt:DerivedUnit and friends), so collect rather than
    # hard-code, and assert the extra ones under qudt:Unit to keep the subset rooted.
    typed_as = {o for _, o in out.subject_objects(RDF.type) if isinstance(o, URIRef)}
    for cls in typed_as | {QUDT.Unit, QUDT.QuantityKind, QUDT.QuantityKindDimensionVector}:
        if cls == OWL.Ontology:
            continue
        out.add((cls, RDF.type, OWL.Class))
        if str(cls).endswith("Unit") and cls != QUDT.Unit:
            out.add((cls, RDFS.subClassOf, QUDT.Unit))

    header = f"""# QUDT subset, extracted by scripts/extract_qudt_subset.py -- DO NOT HAND-EDIT.
#
# {len(UNITS)} units and {len(QUANTITY_KINDS)} quantity kinds pulled from the QUDT public
# repo, preserving authoritative IRIs, conversion factors, and dimension vectors.
# Regenerate with:
#     python3 scripts/extract_qudt_subset.py /path/to/qudt-public-repo
#
# QUDT is licensed CC BY 4.0. See https://github.com/qudt/qudt-public-repo.
#
# Note: units link to quantity kinds via qudt:unitForQuantityKind. QUDT's published
# distribution also carries the inverse, qudt:applicableUnit, but that is derived by
# their build rather than asserted in source, so do not rely on it being present.

"""
    body = out.serialize(format="turtle")
    OUT.write_text(header + body)

    print(f"wrote {OUT.relative_to(ROOT)}: {len(out)} triples, "
          f"{len(UNITS)} units, {len(QUANTITY_KINDS)} quantity kinds, "
          f"{len(dim_vectors)} dimension vectors")
    for u in UNITS:
        term = UNIT[u]
        sym = next(iter(out.objects(term, QUDT.symbol)), "?")
        dv = next(iter(out.objects(term, QUDT.hasDimensionVector)), None)
        kinds = sorted(str(k).split("/")[-1] for k in out.objects(term, QUDT.unitForQuantityKind))
        print(f"  unit:{u:14s} {str(sym):6s} dim={str(dv).split('/')[-1] if dv else '?':20s} {kinds}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
