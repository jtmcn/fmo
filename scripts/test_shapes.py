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
from rdflib import Graph, Literal, RDF, RDFS, URIRef
from rdflib.term import Node
from rdflib.namespace import Namespace, SKOS

sys.path.insert(0, str(Path(__file__).resolve().parent))
from registry import MODULES, ONTOLOGY_PREFIXES, SHAPES, SRC, VOCABULARY_SHAPES, exports  # noqa: E402

SH = Namespace("http://www.w3.org/ns/shacl#")

# One dead-sh:class check, plus one vacuity check and one mutant per sh:minCount
# property shape, per shape, per export fixture. Printing the total is not checking
# it: dropping an sh:minCount from the shapes file shrinks the matrix by one and the
# suite still says OK, which is the export contract quietly losing a required
# property. Checked in like a CQ .expected -- bump it deliberately.
EXPECTED_ASSERTIONS = 14

# The vocabulary shapes' matrix, counted separately because it runs over the
# modules rather than per export fixture: one vacuity check per shape, the
# enumeration-agreement and exception checks, and one mutant per constraint.
EXPECTED_VOCABULARY_ASSERTIONS = 28

KSH = Namespace(ONTOLOGY_PREFIXES["ksh"])
FM = Namespace(ONTOLOGY_PREFIXES["fm"])
VOC = Namespace("https://w3id.org/forecast-market-ontology/shapes/vocabulary#")


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


def property_shape(shapes: Graph, shape: Node, path: Node) -> Node:
    """The property shape under `shape` whose sh:path is `path`."""
    found = [p for p in shapes.objects(shape, SH.property) if shapes.value(p, SH.path) == path]
    if len(found) != 1:
        raise LookupError(f"{shape} has {len(found)} property shape(s) on {path}")
    return found[0]


def inverse_notation_shape(shapes: Graph, shape: Node) -> Node:
    """The property shape under `shape` on [sh:inversePath skos:notation]."""
    found = [p for p in shapes.objects(shape, SH.property)
             if shapes.value(shapes.value(p, SH.path), SH.inversePath) == SKOS.notation]
    if len(found) != 1:
        raise LookupError(f"{shape} has {len(found)} inverse-notation property shape(s)")
    return found[0]


def vocabulary_checks() -> tuple[int, list[str]]:
    """Vacuity, enumeration agreement, exceptions, and one mutant per constraint.

    Each mutant must be caught by the constraint it targets, from the shape that
    owns it: most of them also trip a neighbour (a duplicated code leaves another
    uncarried), and a check crediting any violation would hide a dead constraint.
    """
    shapes = Graph().parse(VOCABULARY_SHAPES, format="turtle")
    modules = base_graph()
    entailed = rdfs_entailed(modules, shapes)
    failures: list[str] = []
    checked = 0

    # 1. Vacuity, per shape, over whichever target it declares.
    for shape in sorted(set(shapes.subjects(RDF.type, SH.NodeShape)), key=str):
        focus: set = set()
        for cls in shapes.objects(shape, SH.targetClass):
            focus |= set(entailed.subjects(RDF.type, cls))
        for prop in shapes.objects(shape, SH.targetObjectsOf):
            focus |= set(entailed.objects(None, prop))
        focus |= set(shapes.objects(shape, SH.targetNode))
        label = str(shape).split("#")[-1]
        checked += 1
        if focus:
            print(f"  ok   [{label}] {len(focus)} focus node(s) in the modules")
        else:
            failures.append(f"{label} matches no focus node in the modules, so it conforms vacuously")

    # 2. The enumeration is written twice; the two copies must agree. Field names are
    # excluded, since not every field is mirrored; anything else counts as a code.
    listed = {
        item
        for prop in shapes.subjects(SH.path, SKOS.notation)
        for items in shapes.objects(prop, SH["in"])
        for item in shapes.items(items)
        if not (isinstance(item, Literal) and str(item.datatype).endswith("FieldName"))
    }
    carried = set(shapes.objects(VOC.DocumentedCodesCarriedShape, SH.targetNode))
    checked += 1
    if listed != carried:
        failures.append(
            f"sh:in and sh:targetNode disagree on the documented codes: only in sh:in "
            f"{sorted(map(str, listed - carried))}, only targeted "
            f"{sorted(map(str, carried - listed))}"
        )
    else:
        print(f"  ok   [enumeration] {len(listed)} code(s), sh:in and sh:targetNode agree")

    # 3. An exception names an individual with no code and a scope note saying why.
    # SHACL cannot see an exception go stale; this can.
    excepted = {
        item
        for alternatives in shapes.objects(None, SH["or"])
        for member in shapes.items(alternatives)
        for items in shapes.objects(member, SH["in"])
        for item in shapes.items(items)
    }
    checked += 1
    stale = sorted(str(i) for i in excepted if any(modules.objects(i, SKOS.notation)))
    unexplained = sorted(str(i) for i in excepted if not any(modules.objects(i, SKOS.scopeNote)))
    if not excepted:
        failures.append("no exception found under sh:or, so this check read nothing")
    elif stale or unexplained:
        failures.append(f"exceptions that carry a code: {stale}; with no scope note: {unexplained}")
    else:
        print(f"  ok   [exceptions] {len(excepted)} excepted, none coded, each with a scope note")

    # 4. Mutants.
    status = property_shape(shapes, VOC.MarketStatusShape, SKOS.notation)
    action = property_shape(shapes, VOC.OrderActionShape, SKOS.notation)
    unique = inverse_notation_shape(shapes, VOC.NotationUniqueShape)
    documented = inverse_notation_shape(shapes, VOC.DocumentedCodesCarriedShape)
    strike = property_shape(shapes, VOC.StrikeTypeShape, SKOS.notation)
    market_field = property_shape(shapes, VOC.MarketFieldShape, SKOS.notation)
    order_field = property_shape(shapes, VOC.OrderFieldShape, SKOS.notation)
    notation = SKOS.notation
    probe = URIRef("https://w3id.org/forecast-market-ontology/examples/probe#Unexplained")

    def code(value: str, datatype: str) -> Literal:
        return Literal(value, datatype=KSH[datatype])

    mutants = [
        ("a coded individual with its code removed", status, SH.MinCountConstraintComponent,
         [], [(KSH.Finalized, notation, code("finalized", "StatusCode"))]),
        ("a second code on one individual", status, SH.MaxCountConstraintComponent,
         [(KSH.Finalized, notation, code("closed", "StatusCode"))], []),
        ("two individuals sharing one code", unique, SH.MaxCountConstraintComponent,
         [(KSH.Closed, notation, code("finalized", "StatusCode"))],
         [(KSH.Closed, notation, code("closed", "StatusCode"))]),
        ("another field's datatype", action, SH.DatatypeConstraintComponent,
         [(KSH.Buy, notation, code("buy", "SideCode"))],
         [(KSH.Buy, notation, code("buy", "ActionCode"))]),
        ("a code outside the enumeration", action, SH.InConstraintComponent,
         [(KSH.Sell, notation, code("sel", "ActionCode"))],
         [(KSH.Sell, notation, code("sell", "ActionCode"))]),
        ("a documented code nobody carries", documented, SH.MinCountConstraintComponent,
         [], list(modules.triples((KSH.ResolvedScalar, None, None)))),
        ("a new outcome with neither a code nor an exception", VOC.ResolutionOutcomeShape,
         SH.OrConstraintComponent, [(probe, RDF.type, KSH.ResolutionOutcome)], []),
        # FM-0015: strike types, the comparators' codes.
        ("a comparator with its strike code removed and no exception", VOC.StrikeTypeShape,
         SH.OrConstraintComponent, [], [(FM.Custom, notation, code("custom", "StrikeTypeCode"))]),
        ("a strike code outside the enumeration", strike, SH.InConstraintComponent,
         [(FM.Between, notation, code("betwen", "StrikeTypeCode"))],
         [(FM.Between, notation, code("between", "StrikeTypeCode"))]),
        ("a documented strike type nobody carries", documented, SH.MinCountConstraintComponent,
         [], list(modules.triples((KSH.FunctionalStrike, None, None)))),
        # FM-0015: field names on the properties that mirror them.
        ("a mirrored property with its field name removed", market_field,
         SH.MinCountConstraintComponent, [],
         [(KSH.closeTime, notation, code("close_time", "MarketFieldName"))]),
        ("a field name outside the schema's field list", market_field, SH.InConstraintComponent,
         [(KSH.closeTime, notation, code("close_tme", "MarketFieldName"))],
         [(KSH.closeTime, notation, code("close_time", "MarketFieldName"))]),
        ("a field name typed as another schema's", order_field, SH.DatatypeConstraintComponent,
         [(KSH.orderQuantity, notation, code("initial_count_fp", "TradeFieldName"))],
         [(KSH.orderQuantity, notation, code("initial_count_fp", "OrderFieldName"))]),
    ]
    for name, source, component, add, remove in mutants:
        checked += 1
        mutant = Graph()
        for triple in modules:
            mutant.add(triple)
        for triple in remove:
            mutant.remove(triple)
        for triple in add:
            mutant.add(triple)
        _, results, _ = shacl_validate(mutant, shacl_graph=shapes, inference="rdfs", advanced=True)
        caught = any(
            results.value(result, SH.sourceConstraintComponent) == component
            for result in results.subjects(SH.sourceShape, source)
        )
        if caught:
            print(f"  ok   [vocabulary] catches {name}")
        else:
            failures.append(f"vocabulary shapes do not catch {name} with {component.split('#')[-1]}")

    return checked, failures


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

    vocabulary_checked, vocabulary_failures = vocabulary_checks()
    failures += vocabulary_failures
    if vocabulary_checked != EXPECTED_VOCABULARY_ASSERTIONS:
        failures.append(
            f"expected {EXPECTED_VOCABULARY_ASSERTIONS} vocabulary shape assertion(s), ran "
            f"{vocabulary_checked}: update EXPECTED_VOCABULARY_ASSERTIONS if a vocabulary "
            f"shape or mutant was added or removed on purpose"
        )

    print(f"\n{checked} export and {vocabulary_checked} vocabulary shape assertion(s) checked")
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
