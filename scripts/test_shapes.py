#!/usr/bin/env python3
"""Tests about the SHACL shapes, rather than about the data they check.

Three properties, each earned by a bug that shipped:

  1. VACUITY. A shape whose sh:targetClass matches no focus node CONFORMS. A
     dead shape and a clean run are indistinguishable in pyshacl's output.
     Focus nodes are counted under the same rdfs entailment validate_shapes.py
     runs, over the nodes the fixture itself contributes -- see rdfs_entailed.
  2. REQUIRED-PROPERTY MUTANTS. A mutant must retype AND break something: the
     export fixture is valid, so it conforms whether or not a shape matched it
     -- retyping alone can't tell "matched and found nothing wrong" from
     "matched nothing". For each shape's sh:minCount property, retyping its
     focus nodes to the shape's own targetClass and dropping that property
     must produce an sh:minCount violation from that property shape. This proves
     every shape's required-property constraints actually fire on export-shaped
     data -- a generated version of the hand-written cases. It does NOT prove a shape's targetClass is
     general enough; that stays covered by the hand-written "an export market
     typed as a plain market, with no proposition" case in test_validate.py,
     which encodes what an export legitimately types things as. The hierarchy
     cannot supply that.
  3. DEAD sh:class. validate_shapes.py runs with inference="rdfs", so range
     entailment types a property's object BEFORE SHACL looks. sh:class C on a
     path whose rdfs:range is already C can never fire; two such constraints
     shipped and a dangling protocol IRI conformed. Ranges are read through
     rdfs:subPropertyOf, the way the inference reads them.

The matrix size is an assertion too, in EXPECTED_ASSERTIONS -- see its comment.

In-process on purpose: test_validate.py copies the whole repo per case, which
costs about a second each. The mutant matrix would push that suite past several
minutes; here the whole thing runs in about 3 seconds.

Run: python3 scripts/test_shapes.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from pyshacl import validate as shacl_validate
from rdflib import Graph, RDF, RDFS
from rdflib.term import Node
from rdflib.namespace import Namespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
from registry import MODULES, SHAPES, SRC, exports  # noqa: E402

SH = Namespace("http://www.w3.org/ns/shacl#")

# One dead-sh:class check, plus one vacuity check and one mutant per sh:minCount
# property shape, per shape, per export fixture. Printing the total is not checking
# it: dropping an sh:minCount from the shapes file shrinks the matrix by one and the
# suite still says OK, which is the export contract quietly losing a required
# property. Checked in like a CQ .expected -- bump it deliberately.
EXPECTED_ASSERTIONS = 14


def base_graph() -> Graph:
    g = Graph()
    for rel in MODULES:
        g.parse(SRC / rel, format="turtle")
    return g


def targets(shapes: Graph) -> list[tuple[Node, Node]]:
    return sorted(shapes.subject_objects(SH.targetClass), key=lambda p: str(p[0]))


def subclasses_of(schema: Graph, cls: Node) -> set:
    return {cls} | set(schema.transitive_subjects(RDFS.subClassOf, cls))


def ranges_of(schema: Graph, path: Node) -> set:
    """Every rdfs:range the inference sees on a property, its own and inherited.

    A direct range read with Graph.value misses two things pyshacl's rdfs closure
    does not: a range inherited through rdfs:subPropertyOf, and the second of two
    declared ranges (value picks one arbitrarily).
    """
    props = {path} | set(schema.transitive_objects(path, RDFS.subPropertyOf))
    return {r for prop in props for r in schema.objects(prop, RDFS.range)}


def rdfs_entailed(data: Graph, shapes: Graph) -> Graph:
    """The data as validate_shapes.py's inference="rdfs" leaves it.

    Focus nodes have to come from the graph pyshacl actually matches against.
    Asserted rdf:type plus the subclass closure is not that graph: rdfs entailment
    types nodes through rdfs:domain and rdfs:range too, and the export shapes lean
    on it deliberately -- ProbabilityShape's own comment says an export may leave
    probabilities untyped because the domain of fm:probabilityValue supplies the
    parent. Reproducing the rule here is how the two drift apart, so run the same
    inference instead: inplace leaves the entailed triples in this throwaway copy.
    """
    entailed = Graph()
    for triple in data:
        entailed.add(triple)
    shacl_validate(entailed, shacl_graph=shapes, inference="rdfs",
                   advanced=True, inplace=True)
    return entailed


def main() -> int:
    schema = base_graph()
    shapes = Graph().parse(SHAPES, format="turtle")
    fixtures = exports()
    if not fixtures:
        print("FAIL: no export fixtures to mutate", file=sys.stderr)
        return 1

    if not targets(shapes):
        print("FAIL: no sh:targetClass in the shapes file, so the whole matrix is "
              "empty and every shape conforms vacuously", file=sys.stderr)
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
        dead = ranges_of(schema, path) & subclasses_of(schema, klass)
        if dead:
            failures.append(
                f"sh:class {klass} on {path} can never fire: rdfs:range is already "
                f"{sorted(str(r) for r in dead)}, and inference=\"rdfs\" types the "
                f"object before SHACL looks"
            )
        else:
            print(f"  ok   [sh:class on {str(path).split('#')[-1]}] can fire")

    for fixture in fixtures:
        fixture_graph = Graph().parse(fixture, format="turtle")
        data = base_graph()
        for triple in fixture_graph:
            data.add(triple)
        # Vacuity is a claim about the FIXTURE, but focus nodes were read off the
        # union, so an individual declared in a module would answer for a fixture
        # that has none. No module declares one today; the day one does, every
        # fixture reports focus nodes it does not contain.
        from_fixture = set(fixture_graph.subjects())
        entailed = rdfs_entailed(data, shapes)

        for shape, cls in targets(shapes):
            label = str(shape).split("#")[-1]
            # The entailment already materialised the subclass closure, so asking
            # for cls alone is asking exactly what pyshacl's targetClass asks.
            focus = set(entailed.subjects(RDF.type, cls)) & from_fixture

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
                # sh:resultPath alone credits ANY shape on this path, not the one
                # under test -- a deactivated shape reusing the same path passed
                # silently. sh:sourceShape pins the result to this property shape.
                # ...and sh:sourceShape alone still credits any constraint on that
                # shape. The mutant retypes its focus nodes as well as dropping the
                # property, so a violation raised by the retyping -- sh:class,
                # sh:nodeKind, a range check -- would pass for the missing property.
                caught = any(
                    results_graph.value(result, SH.resultPath) == path
                    and results_graph.value(result, SH.sourceConstraintComponent)
                    == SH.MinCountConstraintComponent
                    for result in results_graph.subjects(SH.sourceShape, prop_shape)
                )
                if caught:
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
    if checked != EXPECTED_ASSERTIONS:
        failures.append(
            f"expected {EXPECTED_ASSERTIONS} shape assertion(s), ran {checked}: the "
            f"matrix changed size, so this suite is no longer checking what it was. "
            f"If the shapes file gained or lost a shape or an sh:minCount, update "
            f"EXPECTED_ASSERTIONS in this file to match"
        )
    if failures:
        print(f"\nFAILED ({len(failures)}):", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
