#!/usr/bin/env python3
"""Tests about the SHACL shapes, rather than about the data they check.

Three properties, each earned by a bug that shipped:

  1. VACUITY. A shape whose sh:targetClass matches no focus node CONFORMS. A
     dead shape and a clean run are indistinguishable in pyshacl's output.
  2. REQUIRED-PROPERTY MUTANTS. A mutant must retype AND break something: the
     export fixture is valid, so it conforms whether or not a shape matched it
     -- retyping alone can't tell "matched and found nothing wrong" from
     "matched nothing". For each shape's sh:minCount property, retyping its
     focus nodes to the shape's own targetClass and dropping that property
     must produce a violation. This proves every shape's required-property
     constraints actually fire on export-shaped data -- a generated version of
     the hand-written cases. It does NOT prove a shape's targetClass is
     general enough; that stays covered by the hand-written "an export market
     typed as a plain market, with no proposition" case in test_validate.py,
     which encodes what an export legitimately types things as. The hierarchy
     cannot supply that.
  3. DEAD sh:class. validate_shapes.py runs with inference="rdfs", so range
     entailment types a property's object BEFORE SHACL looks. sh:class C on a
     path whose rdfs:range is already C can never fire; two such constraints
     shipped and a dangling protocol IRI conformed.

In-process on purpose: test_validate.py copies the whole repo per case, which
costs about a second each. The mutant matrix would push that suite past several
minutes; here the whole thing runs in about 3 seconds.

Run: python3 scripts/test_shapes.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from pyshacl import validate as shacl_validate
from rdflib import Graph, RDF, RDFS, URIRef
from rdflib.namespace import Namespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
from registry import MODULES, SHAPES, SRC, exports  # noqa: E402

SH = Namespace("http://www.w3.org/ns/shacl#")


def base_graph() -> Graph:
    g = Graph()
    for rel in MODULES:
        g.parse(SRC / rel, format="turtle")
    return g


def targets(shapes: Graph) -> list[tuple[URIRef, URIRef]]:
    return sorted(shapes.subject_objects(SH.targetClass), key=lambda p: str(p[0]))


def subclasses_of(schema: Graph, cls: URIRef) -> set:
    return {cls} | set(schema.transitive_subjects(RDFS.subClassOf, cls))


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

            # Retyping alone proves nothing -- the fixture is valid regardless.
            # A mutant must also break something.
            mutants_for_shape = 0
            for prop_shape in shapes.objects(shape, SH.property):
                path = shapes.value(prop_shape, SH.path)
                if path is None or shapes.value(prop_shape, SH.minCount) is None:
                    continue
                checked += 1
                mutants_for_shape += 1
                mutant = Graph()
                for triple in data:
                    mutant.add(triple)
                for node in focus:
                    for asserted in subclasses_of(schema, cls):
                        mutant.remove((node, RDF.type, asserted))
                    mutant.add((node, RDF.type, cls))
                    for _, _, obj in list(data.triples((node, path, None))):
                        mutant.remove((node, path, obj))
                pname = str(path).split("#")[-1]
                _, results_graph, _ = shacl_validate(
                    mutant, shacl_graph=shapes, inference="rdfs", advanced=True,
                )
                if (None, SH.resultPath, path) in results_graph:
                    print(f"  ok   [{label}] catches a missing {pname}")
                else:
                    failures.append(
                        f"{label} does not report a violation on {pname} for a node "
                        f"typed as its own targetClass in {fixture.name}"
                    )

            if mutants_for_shape == 0:
                failures.append(
                    f"{label} has no sh:minCount property, so no mutant was generated "
                    f"for it: the shape is present but nothing proves it can fire"
                )

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
