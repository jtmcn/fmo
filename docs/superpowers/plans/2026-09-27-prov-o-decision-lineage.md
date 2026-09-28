# PROV-O Import and Decision Lineage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Import a generated PROV-O subset grounded in BFO, align FMO's provenance properties to it, and add retrieval and trading-decision terms so a decision can be traced to the copies of forecasts and observations it read.

**Architecture:** `src/imports/prov-subset.ttl` is generated from the pinned W3C file and imported by `core.ttl`, which also holds the bridge axioms. Retrieval terms go in `core.ttl`, decision terms in `kalshi.ttl`. Two new validator checks enforce what OWL's open world cannot. A new example file and CQ9 exercise the lineage end to end.

**Tech Stack:** Turtle/OWL 2 DL, rdflib, pyshacl, ROBOT + HermiT, SPARQL 1.1, Poetry.

**Spec:** `.fmo/specs/FM-0022-prov-o-decision-lineage.md`

## Global Constraints

- Every minted class and property has `rdfs:label` and `skos:definition`; repo pointers go in `skos:editorialNote`, never `skos:scopeNote`.
- Every class, bridged ones included, reaches `bfo:entity` via `rdfs:subClassOf`.
- A new source file updates `MODULES` in `scripts/registry.py`, the imports and `src/catalog-v001.xml`.
- Every new validator check has `@check(...)`, one `coverage()` per traversal, and a negative test in `scripts/test_validate.py`.
- An empty SPARQL result fails; queries use `a/rdfs:subClassOf*`.
- Never edit `src/imports/bfo-core.ttl`, `src/imports/qudt-subset.ttl`, `shapes/thermaledge-export.ttl` or its pin.
- `src/imports/prov-subset.ttl` is generated; never hand-edit it.
- Code comments: one or two lines, only the non-obvious "why".
- Run everything through `poetry run`. Commit messages carry no co-author line.
- PROV-O source: `https://www.w3.org/ns/prov-o-20130430.ttl`, sha256 `3d03c8e15753178541fb8cd59fbefecaf1861f9c37ef75190c6e938b85fb0c3d`.
- Release: 0.21.0, `owl:priorVersion` 0.20.0, `owl:incompatibleWith` 0.20.0, in all four modules.

## Review Focus

1. **PROV timestamps without an offset.** `prov:endedAtTime` ranges over `xsd:dateTime`, not `xsd:dateTimeStamp`, so `check_timestamp_offsets` as written skips it. Expected: an offset-less `prov:endedAtTime` fails validation. Pinned in Task 3 (case "a retrieval end time with no offset").
2. **A copy linked from its own side.** Data may say `copy fm:isOutputOf retrieval` rather than `retrieval fm:hasOutput copy`. Expected: both checks find the retrieval either way. Pinned in Task 3 (case "a late fetch stated from the copy's side").
3. **Content with no issuance time.** A quote copy carries no `wx:issuanceTime`. Expected: `check_retrievals` skips ordering for it without failing, and CQ9 still returns its row with `?issuedAt` unbound. Pinned by the quote copy in the Task 3 example and the CQ9 expected rows in Task 5.
4. **A decision dated before a fetch it cites.** Expected: fails with "fetched later". Pinned in Task 4.
5. **Material agents under PROV.** `fm:hasAgent ⊑ prov:wasAssociatedWith` makes every existing `fm:hasAgent` target a `prov:Agent`. Expected: the ontology and examples stay consistent. Pinned by `make reason` in Task 2, whose baseline reasons over every example.

---

## File Structure

| File | Responsibility |
|---|---|
| `scripts/extract_prov_subset.py` (new) | Verify the pinned digest and write the PROV subset |
| `src/imports/prov-subset.ttl` (new, generated) | PROV classes and properties FMO uses |
| `src/core.ttl` | Import, bridge axioms, property alignment, retrieval terms |
| `src/weather.ttl` | `wx:supersedes` alignment, `wx:issuanceTime` scope note |
| `src/kalshi.ttl` | Trading decision terms |
| `scripts/registry.py` | `MODULES`, `EXTERNAL_PREFIXES`, `EXAMPLE_PREFIXES` |
| `scripts/axioms.py` | `prov` prefix for readable axiom keys |
| `scripts/validate.py` | PROV grounding traversal, `check_retrievals`, `check_trading_decisions`, offsets on `xsd:dateTime` |
| `scripts/test_validate.py`, `scripts/test_reason.py` | Negative tests and reasoner mutants |
| `examples/kxhighny-2026-08-15-lineage.ttl` (new) | Retrievals, a fresh trade and a stale hold |
| `queries/cq09-decision-lineage.rq` / `.expected` (new) | Decision lineage CQ |
| `queries/axiom-expectations.json` | New axiom sites pinned or exempt |
| `Makefile`, `src/catalog-v001.xml`, `queries/prefixes.txt` | Plumbing |
| `CONTEXT.md`, `docs/design-notes.md`, `README.md` | Vocabulary, rationale, status |

---

### Task 0: Amend the spec to match the repo's constraints

Three findings from planning change the spec. Record them before any code.

**Files:**
- Modify: `.fmo/specs/FM-0022-prov-o-decision-lineage.md`

- [ ] **Step 1: Replace the SHACL claim.** Example data is only ever validated against the export contract, which the spec forbids touching, and `shapes/vocabulary.ttl` runs over the modules alone. So the cardinality rules move into validator checks. In the frontmatter, replace the claim whose witness is `make reason (disjointness mutant); make shapes-negative (hold-reason mutant)` with:

```yaml
  - claim: >-
      A decision statement is a trade instruction or a hold statement and never
      both, and every hold carries exactly one reason.
    witness: make reason (disjointness mutant); make validate-negative (check_trading_decisions, hold with no reason)
```

- [ ] **Step 2: Rename the checks** in the ordering claim's witness to `check_retrievals` and `check_trading_decisions`. Each check also enforces its node's required properties, which is where the SHACL constraints went.

- [ ] **Step 3: Add the fifth alignment.** In "Alignment by sub-property" in `## Problem`, add `fm:hasAgent ⊑ prov:wasAssociatedWith`. `fm:hasAgent` already relates a process to its agent, and minting PROV data beside it unaligned would give two unconnected statements of one fact. In `touches`, remove `shapes/` and `scripts/test_shapes.py`, and add `scripts/axioms.py`, `queries/axiom-expectations.json` and `queries/prefixes.txt`.

- [ ] **Step 4: Append a comment** under `## Comments`:

```markdown
- 2026-09-27, planning: the SHACL constraints moved into check_retrievals and
  check_trading_decisions, because example data is validated only against the
  forbidden export contract. fm:hasAgent joined the alignment.
```

- [ ] **Step 5: Commit**

```bash
git add .fmo/specs/FM-0022-prov-o-decision-lineage.md
git commit -m "FM-0022: move lineage cardinality from SHACL to validator checks; align fm:hasAgent"
```

---

### Task 1: Generate the PROV-O subset and ground it in BFO

**Files:**
- Create: `scripts/extract_prov_subset.py`, `src/imports/prov-subset.ttl` (generated)
- Modify: `scripts/registry.py`, `scripts/axioms.py`, `scripts/validate.py:1603-1625`, `scripts/test_validate.py` (append to `CASES`), `src/core.ttl` (header imports, QUDT bridge block near line 180), `src/catalog-v001.xml`, `Makefile`, `queries/prefixes.txt`

**Interfaces:**
- Produces: the ontology IRI `https://w3id.org/forecast-market-ontology/imports/prov-subset`, the constant `PROV = "http://www.w3.org/ns/prov#"` in `validate.py`, and the `"prov"` key in `registry.EXTERNAL_PREFIXES`.

- [ ] **Step 1: Write the failing negative tests.** Append to `CASES` in `scripts/test_validate.py`:

```python
    (
        # Exercises check_bridged_grounding's PROV traversal: PROV makes no BFO
        # commitment, so without the bridge its classes float under owl:Thing.
        "a bridged PROV class left ungrounded",
        "src/core.ttl",
        "prov:Entity rdfs:subClassOf bfo:BFO_0000002 .   # continuant\n",
        "",
        "bridged external class not grounded in BFO: http://www.w3.org/ns/prov#Entity",
    ),
    (
        "the PROV traversal finding no class",
        "scripts/validate.py",
        'PROV = "http://www.w3.org/ns/prov#"',
        'PROV = "http://www.w3.org/ns/zz#"',
        "bridged PROV classes: nothing to check",
    ),
```

- [ ] **Step 2: Run them to confirm they fail**

Run: `poetry run python3 scripts/test_validate.py 2>&1 | grep -E "PROV"`
Expected: both report `SETUP FAIL ... anchor found 0 times`.

- [ ] **Step 3: Write the extractor** at `scripts/extract_prov_subset.py`:

```python
#!/usr/bin/env python3
"""Extract the PROV-O terms FMO uses into a vendored subset.

Usage:
    curl -sSLo /tmp/prov-o.ttl https://www.w3.org/ns/prov-o-20130430.ttl
    python3 scripts/extract_prov_subset.py /tmp/prov-o.ttl

Writes src/imports/prov-subset.ttl. Do not hand-edit the output.

Only axioms among the kept terms survive. The property chains go, because they
point into the qualified pattern FMO does not use, and so does wasRevisionOf's
owl:AnnotationProperty typing, which would pun it and take the import out of OWL DL.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

from rdflib import Graph, Literal, Namespace, OWL, RDF, RDFS, URIRef, XSD

PROV = Namespace("http://www.w3.org/ns/prov#")
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "src" / "imports" / "prov-subset.ttl"
SOURCE = "https://www.w3.org/ns/prov-o-20130430.ttl"
# The W3C Recommendation is immutable in principle; the digest makes it so in practice.
SHA256 = "3d03c8e15753178541fb8cd59fbefecaf1861f9c37ef75190c6e938b85fb0c3d"

CLASSES = ["Entity", "Activity", "Agent", "SoftwareAgent"]
PROPERTIES = [
    "used", "wasGeneratedBy", "wasAssociatedWith", "wasAttributedTo",
    "wasDerivedFrom", "wasRevisionOf", "startedAtTime", "endedAtTime",
]
DECLARATIONS = {OWL.Class, OWL.ObjectProperty, OWL.DatatypeProperty}
AXIOMS = {RDFS.subClassOf, RDFS.subPropertyOf, RDFS.domain, RDFS.range, OWL.disjointWith}


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    path = Path(sys.argv[1])
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != SHA256:
        print(f"{path}: sha256 {digest}, expected {SHA256} for {SOURCE}", file=sys.stderr)
        return 1

    src = Graph().parse(path, format="turtle")
    kept = {PROV[t] for t in CLASSES + PROPERTIES}
    missing = sorted(str(t) for t in kept if (t, None, None) not in src)
    if missing:
        print("MISSING from PROV-O:\n  " + "\n  ".join(missing), file=sys.stderr)
        return 1

    out = Graph()
    out.bind("prov", PROV)
    for term in sorted(kept, key=str):
        for p, o in src.predicate_objects(term):
            if p == RDF.type and o in DECLARATIONS:
                out.add((term, p, o))
            elif p in (RDFS.label, RDFS.comment) and isinstance(o, Literal):
                out.add((term, p, o))
            elif p in AXIOMS and (o in kept or (isinstance(o, URIRef) and str(o).startswith(str(XSD)))):
                out.add((term, p, o))

    subset = URIRef("https://w3id.org/forecast-market-ontology/imports/prov-subset")
    out.add((subset, RDF.type, OWL.Ontology))
    out.add((subset, RDFS.label, Literal("PROV-O subset for FMO")))
    out.add((subset, RDFS.comment, Literal(
        f"Terms extracted from {SOURCE}. Generated by scripts/extract_prov_subset.py; do not hand-edit.")))

    header = f"""# PROV-O subset, extracted by scripts/extract_prov_subset.py -- DO NOT HAND-EDIT.
#
# {len(CLASSES)} classes and {len(PROPERTIES)} properties from {SOURCE}
# (sha256 {SHA256}). Regenerate with `make prov`.
#
# PROV-O is published by the W3C under the W3C Document License.

"""
    OUT.write_text(header + out.serialize(format="turtle"), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(out)} triples")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Generate the subset and inspect it**

```bash
curl -sSLo /tmp/prov-o.ttl https://www.w3.org/ns/prov-o-20130430.ttl
poetry run python3 scripts/extract_prov_subset.py /tmp/prov-o.ttl
grep -c "owl:AnnotationProperty\|propertyChainAxiom\|InstantaneousEvent\|wasInfluencedBy" src/imports/prov-subset.ttl
```

Expected: `wrote src/imports/prov-subset.ttl: N triples`. The grep prints `0`. `prov:Activity owl:disjointWith prov:Entity` is present.

- [ ] **Step 5: Add the Makefile target.** Put this beside `qudt:`, add `prov` to `.PHONY`, and add `$(SRC)/imports/prov-subset.ttl` to the `$(BUILD)/merged.owl` prerequisites:

```make
## Regenerate the vendored PROV-O subset from the pinned W3C file:
##   curl -sSLo /tmp/prov-o.ttl https://www.w3.org/ns/prov-o-20130430.ttl
PROV_O ?= /tmp/prov-o.ttl
prov:
	$(PY) scripts/extract_prov_subset.py $(PROV_O)
```

- [ ] **Step 6: Wire the module in.**
  - `scripts/registry.py`: set `MODULES = ["imports/bfo-core.ttl", "imports/qudt-subset.ttl", "imports/prov-subset.ttl", "core.ttl", "weather.ttl", "kalshi.ttl", "fmo.ttl"]`, and add `"prov": "http://www.w3.org/ns/prov#",` to `EXTERNAL_PREFIXES`.
  - `scripts/axioms.py`: add `"http://www.w3.org/ns/prov#": "prov",` to `PREFIXES`.
  - `queries/prefixes.txt`: add `PREFIX prov: <http://www.w3.org/ns/prov#>` after the `qudt:` line.
  - `src/catalog-v001.xml`: after the `qudt` entry add
    `<uri id="prov"     name="https://w3id.org/forecast-market-ontology/imports/prov-subset" uri="imports/prov-subset.ttl"/>`.
  - `src/core.ttl`: add `@prefix prov: <http://www.w3.org/ns/prov#> .` to the prefixes, and `<https://w3id.org/forecast-market-ontology/imports/prov-subset>` to `owl:imports`.

- [ ] **Step 7: Add the bridge axioms** in `src/core.ttl`, directly after the QUDT bridge block (near line 184):

```turtle
# PROV makes no BFO commitment. Entity under continuant makes PROV-DM's
# entity/activity disjointness follow from BFO's own.
prov:Entity rdfs:subClassOf bfo:BFO_0000002 .   # continuant
prov:Activity rdfs:subClassOf bfo:BFO_0000015 .   # process
# Not under fm:Agent, which is material: the agent of a retrieval is usually software.
prov:Agent rdfs:subClassOf bfo:BFO_0000002 .   # continuant
fm:Agent rdfs:subClassOf prov:Agent .
```

- [ ] **Step 8: Extend `check_bridged_grounding`.** Add a separate traversal with its own `coverage()`, because one shared counter stays non-zero when one namespace empties. Define `PROV = "http://www.w3.org/ns/prov#"` next to `QUDT = ...` near line 329. Then append to the body of `check_bridged_grounding`, and change its `reason=` to `"its population is the bridged QUDT and PROV classes"`:

```python
    prov_classes = sorted(
        (s for s in g.subjects(RDF.type, OWL.Class) if str(s).startswith(PROV)), key=str
    )
    for iri in prov_classes:
        if ENTITY not in ancestors(g, iri):
            fail(f"bridged external class not grounded in BFO: {iri}")
    coverage("bridged PROV classes", len(prov_classes), "class(es) checked for BFO grounding",
             "the PROV subset declares no owl:Class, so the bridge axioms guard nothing",
             always=True)
```

- [ ] **Step 9: Run the checks**

Run: `poetry run python3 scripts/validate.py && poetry run python3 scripts/test_validate.py 2>&1 | grep -E "PROV|FAIL"`
Expected: validate reports `bridged PROV classes: 4 class(es)` and `OK`. Both new cases print `ok`, and no `FAIL` line appears.

- [ ] **Step 10: Run the targets the import touches**

Run: `make meta reason axioms signatures diagram-check lineage`
Expected: every target passes. If `make axioms` reports new unclassified sites, those are the bridge `subClassOf` links. Add each under `exempt` in `queries/axiom-expectations.json` with the reason `"Grounding, not a constraint data can violate: check_bridged_grounding proves the path to bfo:entity."`, except `prov:Entity subClassOf bfo:BFO_0000002`, which Task 2 pins. Give that one the same exempt reason for now.

- [ ] **Step 11: Commit**

```bash
git add scripts/extract_prov_subset.py src/imports/prov-subset.ttl scripts/registry.py scripts/axioms.py \
  scripts/validate.py scripts/test_validate.py src/core.ttl src/catalog-v001.xml Makefile \
  queries/prefixes.txt queries/axiom-expectations.json
git commit -m "Import a generated PROV-O subset and ground it in BFO (FM-0022)"
```

---

### Task 2: Align FMO's provenance properties to PROV

**Files:**
- Modify: `src/core.ttl` (`fm:hasAgent`, `fm:isOutputOf`, `fm:hasInput`, `fm:issuedBy`), `src/weather.ttl` (`wx:supersedes`, `wx:issuanceTime`), `scripts/test_reason.py` (append to `CASES`), `queries/axiom-expectations.json`

**Interfaces:**
- Consumes: the PROV properties from Task 1.
- Produces: `fm:hasInput ⊑ prov:used`, which is what CQ9 walks in Task 5.

- [ ] **Step 1: Write the failing reasoner case.** Append to `CASES` in `scripts/test_reason.py`. The process is fresh and has no inputs, outputs or agent, so only `prov:Entity ⊑ continuant` can make it inconsistent. Through their inverses, the example's existing processes are already `prov:Activity`, disjoint from `prov:Entity`.

```python
    (
        # prov:used ranges over prov:Entity, grounded under continuant, so an
        # occurrent input is a BFO branch clash rather than a quiet retyping.
        "a bare process used as the input to a process",
        EXAMPLE,
        """ex:Derivation-1200Z a ksh:PriceToProbabilityDerivation ;
    fm:hasInput ex:Quote-1200Z ;""",
        """ex:BareProcess a bfo:BFO_0000015 .

ex:Derivation-1200Z a ksh:PriceToProbabilityDerivation ;
    fm:hasInput ex:Quote-1200Z , ex:BareProcess ;""",
    ),
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `poetry run python3 scripts/test_reason.py 2>&1 | grep "bare process"`
Expected: the case reports that the reasoner accepted the mutant, because `fm:hasInput` is not yet aligned.

- [ ] **Step 3: Add the sub-property axioms.**
  - `src/core.ttl`, in each property's block:
    - `fm:hasInput`: `rdfs:subPropertyOf prov:used ;`
    - `fm:isOutputOf`: `rdfs:subPropertyOf prov:wasGeneratedBy ;`. Not on `fm:hasOutput`: PROV's inverse, `prov:generated`, is not in the subset, and the inverse axiom carries the alignment.
    - `fm:issuedBy`: `rdfs:subPropertyOf prov:wasAttributedTo ;`
    - `fm:hasAgent`: add `prov:wasAssociatedWith` to its existing `rdfs:subPropertyOf` as a second object: `rdfs:subPropertyOf bfo:BFO_0000057 , prov:wasAssociatedWith ;`.
  - `src/weather.ttl`: add `@prefix prov: <http://www.w3.org/ns/prov#> .`, and in `wx:supersedes` add `rdfs:subPropertyOf prov:wasRevisionOf ;`.

- [ ] **Step 4: Record why issuance is not generation.** Replace the `skos:scopeNote` on `wx:issuanceTime` in `src/weather.ttl` with:

```turtle
    skos:scopeNote "Distinct from the interval the content concerns, and from a model run cycle time. A CLI report is issued the morning after the day it covers. Not a sub-property of prov:generatedAtTime: generation is when content came to exist, issuance is when it was made public, and a report generated at 05:40 and issued at 06:00 must keep both." .
```

- [ ] **Step 5: Run the reasoner suite**

Run: `make reason reason-negative && poetry run python3 scripts/test_reason.py`
Expected: the baseline is consistent (Review Focus 5), and "a bare process used as the input to a process" fires.

- [ ] **Step 6: Pin the grounding axiom.** In `queries/axiom-expectations.json`, move `core.ttl: prov:Entity subClassOf bfo:BFO_0000002` (use the exact key `make axioms` prints) from `exempt` to `pinned`, with the value `"a bare process used as the input to a process"`.

Run: `make axioms validate shapes cq`
Expected: all pass. `make axioms` confirms that deleting the grounding axiom stops the case from firing.

- [ ] **Step 7: Commit**

```bash
git add src/core.ttl src/weather.ttl scripts/test_reason.py queries/axiom-expectations.json
git commit -m "Align hasInput, isOutputOf, issuedBy, hasAgent and supersedes to PROV (FM-0022)"
```

---

### Task 3: Retrieval terms, `check_retrievals`, and the retrieval half of the example

**Files:**
- Modify: `src/core.ttl` (new "Data handling" section after the "Processes" section), `scripts/validate.py`, `scripts/test_validate.py`, `scripts/registry.py`, `queries/axiom-expectations.json`
- Create: `examples/kxhighny-2026-08-15-lineage.ttl`

**Interfaces:**
- Produces: `fm:DataHandlingProcess`, `fm:Retrieval`, `fm:RetrievedCopy` and `fm:retrievedFrom`; individuals `lex:Retrieval-06Z`, `lex:Retrieval-12Z`, `lex:Retrieval-Quote-1200Z`, `lex:Copy-06Z`, `lex:Copy-12Z`, `lex:Copy-Quote-1200Z`, `lex:Forecast-GEFS-12Z`, `lex:IngestJob` and `lex:Strategy`; and in `validate.py`, `aware_instant(value: Node) -> datetime` and the constants `ENDED_AT`, `RETRIEVAL`, `RETRIEVED_COPY`, `RETRIEVED_FROM`, `CARRIER_OF`, `IS_OUTPUT_OF`.

- [ ] **Step 1: Add the terms** to `src/core.ttl`, after the `fm:EvaluationProcess` block:

```turtle
################################################################
# Data handling
################################################################

fm:DataHandlingProcess a owl:Class ;
    rdfs:subClassOf bfo:BFO_0000015 ;   # process
    rdfs:label "data handling process" ;
    skos:definition "A process in which an agent acquires, stores or transforms information content entities for its own use." ;
    skos:scopeNote "Not under fm:InformationProcess, which requires new content as output: a retrieval makes a new carrier of existing content and nothing more." .

fm:Retrieval a owl:Class ;
    rdfs:subClassOf fm:DataHandlingProcess ;
    rdfs:label "retrieval" ;
    skos:definition "A data handling process in which an agent requests an information content entity from an endpoint and brings a copy of it onto a carrier the agent controls." ;
    rdfs:subClassOf [ a owl:Restriction ;
        owl:onProperty fm:hasInput ; owl:someValuesFrom fm:InformationContentEntity ] ,
                    [ a owl:Restriction ;
        owl:onProperty fm:hasOutput ; owl:someValuesFrom fm:RetrievedCopy ] ;
    skos:scopeNote "The fetch time is prov:endedAtTime. Set against the content's wx:issuanceTime, it says how stale the copy was when it arrived." ;
    skos:editorialNote "check_retrievals in scripts/validate.py requires one end time and one endpoint." .

fm:RetrievedCopy a owl:Class ;
    rdfs:subClassOf fm:InformationBearingEntity ;
    rdfs:label "retrieved copy" ;
    skos:definition "An information bearing entity that is the output of a retrieval and carries the content that retrieval requested." ;
    rdfs:subClassOf [ a owl:Restriction ;
        owl:onProperty fm:isOutputOf ; owl:someValuesFrom fm:Retrieval ] ;
    skos:scopeNote "The content is the issuer's; the copy is ours. Two fetches of one forecast are two copies of one information content entity, so a decision cites the copy to say which fetch it read." .

fm:retrievedFrom a owl:DatatypeProperty ;
    rdfs:label "retrieved from" ;
    rdfs:domain fm:Retrieval ;
    rdfs:range xsd:anyURI ;
    skos:definition "The endpoint a retrieval requested its content from." .
```

- [ ] **Step 2: Register the example prefix.** In `scripts/registry.py`, add `"lex": "https://w3id.org/forecast-market-ontology/examples/kxhighny-2026-08-15-lineage#",` to `EXAMPLE_PREFIXES`.

- [ ] **Step 3: Create the example** at `examples/kxhighny-2026-08-15-lineage.ttl`:

```turtle
# Worked example: where a trading decision's inputs came from.
#
# Two GEFS forecasts for the Central Park high, issued 09:40Z and 15:40Z, each
# fetched once, and a quote fetched at noon. A decision at 11:59:30Z trades on the
# 06Z copy, which was then the latest. A hold at 16:30Z still reads the 06Z copy,
# though the 12Z forecast had been issued and fetched by then: CQ9 flags it stale.
#
# Values are illustrative and are not real fetches, orders, or holdings.

@prefix lex:  <https://w3id.org/forecast-market-ontology/examples/kxhighny-2026-08-15-lineage#> .
@prefix ex:   <https://w3id.org/forecast-market-ontology/examples/kxhighny-2026-08-15#> .
@prefix tex:  <https://w3id.org/forecast-market-ontology/examples/kxhighny-2026-08-15-trading#> .
@prefix fm:   <https://w3id.org/forecast-market-ontology/core#> .
@prefix wx:   <https://w3id.org/forecast-market-ontology/weather#> .
@prefix ksh:  <https://w3id.org/forecast-market-ontology/kalshi#> .
@prefix bfo:  <http://purl.obolibrary.org/obo/> .
@prefix prov: <http://www.w3.org/ns/prov#> .
@prefix owl:  <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .

<https://w3id.org/forecast-market-ontology/examples/kxhighny-2026-08-15-lineage>
    a owl:Ontology ;
    owl:imports <https://w3id.org/forecast-market-ontology/fmo> ;
    rdfs:label "Worked example: decision lineage for KXHIGHNY-26AUG15-B82.5" .

################################################################
# 1. The software agents
################################################################

lex:IngestJob a prov:SoftwareAgent ;
    rdfs:label "ThermalEdge ingest job 2.4.0" .

lex:Strategy a prov:SoftwareAgent ;
    rdfs:label "ThermalEdge strategy 2.4.0" .

################################################################
# 2. A later forecast for the same target
################################################################

lex:Forecast-GEFS-12Z a wx:Forecast ;
    rdfs:label "GEFS 12Z forecast for Central Park high, 2026-08-15" ;
    wx:forecastFor ex:Target-HighTemp ;
    wx:producedByModel ex:GEFS ;
    fm:issuedBy ex:NWS ;
    wx:issuanceTime "2026-08-15T15:40:00Z"^^xsd:dateTime .

################################################################
# 3. Retrievals, and the copies they leave
################################################################

lex:Retrieval-06Z a fm:Retrieval ;
    rdfs:label "ingest fetches the GEFS 06Z forecast" ;
    fm:hasInput ex:Forecast-GEFS-06Z ;
    fm:hasOutput lex:Copy-06Z ;
    prov:wasAssociatedWith lex:IngestJob ;
    fm:retrievedFrom "https://nomads.ncep.noaa.gov/pub/data/nccf/com/gens/prod/gefs.20260815/06/"^^xsd:anyURI ;
    prov:startedAtTime "2026-08-15T09:47:02Z"^^xsd:dateTime ;
    prov:endedAtTime "2026-08-15T09:47:03Z"^^xsd:dateTime .

lex:Copy-06Z a fm:RetrievedCopy ;
    rdfs:label "stored copy of the GEFS 06Z forecast" ;
    bfo:BFO_0000101 ex:Forecast-GEFS-06Z .     # is carrier of

lex:Retrieval-12Z a fm:Retrieval ;
    rdfs:label "ingest fetches the GEFS 12Z forecast" ;
    fm:hasInput lex:Forecast-GEFS-12Z ;
    fm:hasOutput lex:Copy-12Z ;
    prov:wasAssociatedWith lex:IngestJob ;
    fm:retrievedFrom "https://nomads.ncep.noaa.gov/pub/data/nccf/com/gens/prod/gefs.20260815/12/"^^xsd:anyURI ;
    prov:startedAtTime "2026-08-15T15:52:10Z"^^xsd:dateTime ;
    prov:endedAtTime "2026-08-15T15:52:11Z"^^xsd:dateTime .

lex:Copy-12Z a fm:RetrievedCopy ;
    rdfs:label "stored copy of the GEFS 12Z forecast" ;
    bfo:BFO_0000101 lex:Forecast-GEFS-12Z .

# A quote has no issuance time, so this copy is never ordered against one.
lex:Retrieval-Quote-1200Z a fm:Retrieval ;
    rdfs:label "ingest fetches the noon quote" ;
    fm:hasInput ex:Quote-1200Z ;
    fm:hasOutput lex:Copy-Quote-1200Z ;
    prov:wasAssociatedWith lex:IngestJob ;
    fm:retrievedFrom "https://api.elections.kalshi.com/trade-api/v2/markets/KXHIGHNY-26AUG15-B82.5"^^xsd:anyURI ;
    prov:startedAtTime "2026-08-15T12:00:03Z"^^xsd:dateTime ;
    prov:endedAtTime "2026-08-15T12:00:04Z"^^xsd:dateTime .

lex:Copy-Quote-1200Z a fm:RetrievedCopy ;
    rdfs:label "stored copy of the noon quote" ;
    bfo:BFO_0000101 ex:Quote-1200Z .
```

- [ ] **Step 4: Write the failing negative tests.** Add `LINEAGE = "examples/kxhighny-2026-08-15-lineage.ttl"` beside `TRADING` at the top of `scripts/test_validate.py`, then append to `CASES`:

```python
    (
        # Exercises check_retrievals: a fetch cannot precede the content's issuance.
        "a retrieval ending before its content was issued",
        LINEAGE,
        'prov:endedAtTime "2026-08-15T15:52:11Z"^^xsd:dateTime',
        'prov:endedAtTime "2026-08-15T15:30:00Z"^^xsd:dateTime',
        "ended at 2026-08-15T15:30:00+00:00, before",
    ),
    (
        "a retrieval with no endpoint",
        LINEAGE,
        '    fm:retrievedFrom "https://nomads.ncep.noaa.gov/pub/data/nccf/com/gens/prod/gefs.20260815/12/"^^xsd:anyURI ;\n',
        "",
        "a retrieval needs exactly one fm:retrievedFrom, has 0",
    ),
    (
        # prov:endedAtTime ranges over xsd:dateTime, so only an extended
        # check_timestamp_offsets sees a missing offset here.
        "a retrieval end time with no offset",
        LINEAGE,
        'prov:endedAtTime "2026-08-15T09:47:03Z"^^xsd:dateTime',
        'prov:endedAtTime "2026-08-15T09:47:03"^^xsd:dateTime',
        "prov#endedAtTime on https://w3id.org/forecast-market-ontology/examples/kxhighny-2026-08-15-lineage#Retrieval-06Z has no timezone offset",
    ),
    (
        # Data may link the copy to its retrieval from either end: with the link
        # stated only from the copy, the ordering must still be found and reported.
        "a late fetch stated from the copy's side",
        LINEAGE,
        """    fm:hasOutput lex:Copy-12Z ;
    prov:wasAssociatedWith lex:IngestJob ;
    fm:retrievedFrom "https://nomads.ncep.noaa.gov/pub/data/nccf/com/gens/prod/gefs.20260815/12/"^^xsd:anyURI ;
    prov:startedAtTime "2026-08-15T15:52:10Z"^^xsd:dateTime ;
    prov:endedAtTime "2026-08-15T15:52:11Z"^^xsd:dateTime .

lex:Copy-12Z a fm:RetrievedCopy ;""",
        """    prov:wasAssociatedWith lex:IngestJob ;
    fm:retrievedFrom "https://nomads.ncep.noaa.gov/pub/data/nccf/com/gens/prod/gefs.20260815/12/"^^xsd:anyURI ;
    prov:startedAtTime "2026-08-15T15:20:00Z"^^xsd:dateTime ;
    prov:endedAtTime "2026-08-15T15:20:01Z"^^xsd:dateTime .

lex:Copy-12Z a fm:RetrievedCopy ;
    fm:isOutputOf lex:Retrieval-12Z ;""",
        "ended at 2026-08-15T15:20:01+00:00, before",
    ),
```

- [ ] **Step 5: Run them to confirm they fail**

Run: `poetry run python3 scripts/test_validate.py 2>&1 | grep -A2 -E "retrieval|late fetch"`
Expected: each case prints `FAIL [...]: validate.py passed but should have failed` or `message missing`.

- [ ] **Step 6: Implement.** In `scripts/validate.py`, add `from datetime import datetime` to the top-level imports. Put the constants next to `PROV`, and the helper and check after `check_timestamp_offsets`:

```python
ENDED_AT = URIRef(PROV + "endedAtTime")
RETRIEVAL = URIRef(FM + "Retrieval")
RETRIEVED_COPY = URIRef(FM + "RetrievedCopy")
RETRIEVED_FROM = URIRef(FM + "retrievedFrom")
IS_OUTPUT_OF = URIRef(FM + "isOutputOf")
CARRIER_OF = URIRef(BFO + "BFO_0000101")
```

```python
def aware_instant(value: Node) -> datetime:
    """An instant with a UTC offset, or ValueError: naive and aware datetimes do not compare."""
    instant = datetime.fromisoformat(str(value))
    if instant.tzinfo is None:
        raise ValueError(f"{value!r} has no UTC offset")
    return instant


def outputs_of(g: Graph, process: Node) -> set:
    """What a process output, stated from either end."""
    return set(g.objects(process, HAS_OUTPUT)) | set(g.subjects(IS_OUTPUT_OF, process))


@check(takes=("data",))
def check_retrievals(g: Graph) -> None:
    """A retrieval says when and where it fetched, and cannot end before its content was issued.

    CQ9's staleness answer reads the fetch time. A missing one empties a row; a wrong
    one moves it, and neither makes the query fail.
    """
    retrievals = instances_of(g, RETRIEVAL)
    ordered = 0
    for retrieval in retrievals:
        ends = list(g.objects(retrieval, ENDED_AT))
        sources = list(g.objects(retrieval, RETRIEVED_FROM))
        copies = [c for c in outputs_of(g, retrieval) if RETRIEVED_COPY in types_of(g, c)]
        if len(sources) != 1:
            fail(f"{retrieval}: a retrieval needs exactly one fm:retrievedFrom, has {len(sources)}")
        if not copies:
            fail(f"{retrieval}: a retrieval has no fm:RetrievedCopy as output")
        if len(ends) != 1:
            fail(f"{retrieval}: a retrieval needs exactly one prov:endedAtTime, has {len(ends)}")
            continue
        try:
            ended = aware_instant(ends[0])
        except (ValueError, TypeError) as exc:
            fail(f"{retrieval}: cannot read prov:endedAtTime: {exc}")
            continue
        for copy in copies:
            for content in g.objects(copy, CARRIER_OF):
                for issued in g.objects(content, ISSUANCE):
                    try:
                        issued_at = aware_instant(issued)
                    except (ValueError, TypeError) as exc:
                        fail(f"{content}: cannot read wx:issuanceTime: {exc}")
                        continue
                    ordered += 1
                    if ended < issued_at:
                        fail(f"{retrieval} ended at {ended.isoformat()}, before {content} "
                             f"was issued at {issued_at.isoformat()}")
    coverage("retrievals", len(retrievals),
             "retrieval(s) checked for an end time, an endpoint and a copy",
             "no example asserts an fm:Retrieval")
    coverage("retrieval after issuance", ordered, "fetch/issuance pair(s) ordered",
             "no retrieved copy carries content with a wx:issuanceTime")
```

Extend `check_timestamp_offsets` to cover `xsd:dateTime` ranges as well (Review Focus 1). Replace its `props = ...` line, and update the docstring's last sentence to say "ranged xsd:dateTimeStamp or xsd:dateTime":

```python
    props = sorted({p for dt in (XSD.dateTimeStamp, XSD.dateTime)
                    for p in ex.subjects(RDFS.range, dt)}, key=str)
```

In the same check, change the coverage detail from `xsd:dateTimeStamp propert(ies)` to `timestamp propert(ies)`.

- [ ] **Step 7: Run the checks**

Run: `poetry run python3 scripts/validate.py && poetry run python3 scripts/test_validate.py 2>&1 | grep -E "retrieval|late fetch|FAIL"`
Expected: `retrievals: 3`, `retrieval after issuance: 2` and `OK`. The four cases print `ok`, and no `FAIL` line appears. If "a retrieval end time with no offset" reports a missing message, copy the exact line `check_timestamp_offsets` printed into the expected substring.

- [ ] **Step 8: Run the rest of the gate**

Run: `make meta shapes cq reason axioms diagram-check`
Expected: all pass. `make meta` sweeps `check_retrievals` against the schema alone and sees both of its coverage guards fire. For every new site `make axioms` reports, add an `exempt` entry. For existential restrictions use `"A modelling commitment about what the class involves, not a constraint well-formed data can violate. check_retrievals enforces presence on the data."`, and for named `subClassOf` sites use `"Grounding, not a constraint data can violate: check_bfo_grounding proves the path to bfo:entity."`. If `make cq` shows changed rows in an existing `.expected` because a query now sees `lex:Forecast-GEFS-12Z`, inspect the diff. Accept it with `make cq-update` only if the new rows are correct for that query's question.

- [ ] **Step 9: Commit**

```bash
git add src/core.ttl scripts/validate.py scripts/test_validate.py scripts/registry.py \
  examples/kxhighny-2026-08-15-lineage.ttl queries/axiom-expectations.json queries/*.expected
git commit -m "Add retrievals and retrieved copies, checked against issuance (FM-0022)"
```

---

### Task 4: Trading decision terms, `check_trading_decisions`, and the decisions in the example

**Files:**
- Modify: `src/kalshi.ttl` ("Trading processes" section, after `ksh:OrderPlacement`), `scripts/validate.py`, `scripts/test_validate.py`, `scripts/test_reason.py`, `examples/kxhighny-2026-08-15-lineage.ttl`, `queries/axiom-expectations.json`

**Interfaces:**
- Consumes: `aware_instant`, `outputs_of`, `ENDED_AT` and `RETRIEVED_COPY` from Task 3; `lex:Copy-06Z` and `lex:Copy-Quote-1200Z`.
- Produces: `ksh:TradingDecision`, `ksh:DecisionStatement`, `ksh:TradeInstruction`, `ksh:HoldStatement` and `ksh:holdReason`; individuals `lex:Decision-Trade`, `lex:Decision-Hold`, `lex:Statement-Trade` and `lex:Statement-Hold`.

- [ ] **Step 1: Add the terms** to `src/kalshi.ttl`, after `ksh:OrderPlacement`.

```turtle
ksh:TradingDecision a owl:Class ;
    rdfs:subClassOf fm:InformationProcess ;
    rdfs:label "trading decision" ;
    skos:definition "An information process in which a trader or a program acting for one reads copies of forecasts, observations or quotes and states whether to trade." ;
    rdfs:subClassOf [ a owl:Restriction ;
        owl:onProperty fm:hasInput ; owl:someValuesFrom fm:RetrievedCopy ] ,
                    [ a owl:Restriction ;
        owl:onProperty fm:hasOutput ; owl:someValuesFrom ksh:DecisionStatement ] ;
    skos:scopeNote "Inputs are the copies read, not the content alone: two fetches of one forecast are the same content, and only the copy says which fetch the decision saw. Holds are decisions too, so a backtest that joins on them is not limited to the days that traded." ;
    skos:editorialNote "check_trading_decisions in scripts/validate.py requires a cited copy, one statement and one end time. CQ9 walks the lineage." .

ksh:DecisionStatement a owl:Class ;
    rdfs:subClassOf fm:DirectiveInformationEntity ;
    rdfs:label "decision statement" ;
    skos:definition "A directive information entity that is the output of a trading decision and states whether to trade." ;
    rdfs:subClassOf [ a owl:Class ; owl:unionOf ( ksh:TradeInstruction ksh:HoldStatement ) ] .

ksh:TradeInstruction a owl:Class ;
    rdfs:subClassOf ksh:DecisionStatement ;
    owl:disjointWith ksh:HoldStatement ;
    rdfs:label "trade instruction" ;
    skos:definition "A decision statement directing that an order be placed." ;
    skos:scopeNote "The input to the ksh:OrderPlacement that follows it. Not ksh:Trade, which is the exchange matching two orders." .

ksh:HoldStatement a owl:Class ;
    rdfs:subClassOf ksh:DecisionStatement ;
    rdfs:label "hold statement" ;
    skos:definition "A decision statement directing that no order be placed, and saying why." .

ksh:holdReason a owl:DatatypeProperty ;
    rdfs:label "hold reason" ;
    rdfs:domain ksh:HoldStatement ;
    rdfs:range xsd:string ;
    skos:definition "Why a trading decision directed that no order be placed, as the deciding program stated it." ;
    skos:scopeNote "Prose rather than a controlled vocabulary: the reasons are the deciding program's own code paths and change with it." .
```

- [ ] **Step 2: Add the decisions** to the end of `examples/kxhighny-2026-08-15-lineage.ttl`:

```turtle
################################################################
# 4. Two decisions: a fresh trade and a stale hold
################################################################

lex:Decision-Trade a ksh:TradingDecision ;
    rdfs:label "strategy decides to buy yes on 82-83F" ;
    fm:hasInput lex:Copy-06Z , ex:ForecastProb-82-83 ;
    fm:hasOutput lex:Statement-Trade ;
    prov:wasAssociatedWith lex:Strategy ;
    prov:endedAtTime "2026-08-15T11:59:30Z"^^xsd:dateTime .

lex:Statement-Trade a ksh:TradeInstruction ;
    rdfs:label "buy yes on 82-83F" .

tex:Placement-A fm:hasInput lex:Statement-Trade .

# Reads the 06Z copy although the 12Z forecast was issued at 15:40Z and fetched at 15:52Z.
lex:Decision-Hold a ksh:TradingDecision ;
    rdfs:label "strategy holds on 82-83F" ;
    fm:hasInput lex:Copy-06Z , lex:Copy-Quote-1200Z ;
    fm:hasOutput lex:Statement-Hold ;
    prov:wasAssociatedWith lex:Strategy ;
    prov:endedAtTime "2026-08-15T16:30:00Z"^^xsd:dateTime .

lex:Statement-Hold a ksh:HoldStatement ;
    rdfs:label "hold on 82-83F" ;
    ksh:holdReason "position limit reached for KXHIGHNY-26AUG15" .
```

- [ ] **Step 3: Write the failing negative tests.** Append to `CASES` in `scripts/test_validate.py`:

```python
    (
        # Exercises check_trading_decisions.
        "a decision dated before a fetch it cites",
        LINEAGE,
        'prov:endedAtTime "2026-08-15T11:59:30Z"^^xsd:dateTime',
        'prov:endedAtTime "2026-08-15T09:00:00Z"^^xsd:dateTime',
        "fetched later",
    ),
    (
        "a decision citing no retrieved copy",
        LINEAGE,
        "    fm:hasInput lex:Copy-06Z , ex:ForecastProb-82-83 ;",
        "    fm:hasInput ex:ForecastProb-82-83 ;",
        "cites no fm:RetrievedCopy",
    ),
    (
        "a hold with no reason",
        LINEAGE,
        '    rdfs:label "hold on 82-83F" ;\n    ksh:holdReason "position limit reached for KXHIGHNY-26AUG15" .',
        '    rdfs:label "hold on 82-83F" .',
        "needs exactly one ksh:holdReason, has 0",
    ),
```

And to `CASES` in `scripts/test_reason.py`, after adding `LINEAGE = "examples/kxhighny-2026-08-15-lineage.ttl"` beside `TRADING`:

```python
    (
        "a decision statement typed both trade instruction and hold statement",
        LINEAGE,
        "lex:Statement-Hold a ksh:HoldStatement ;",
        "lex:Statement-Hold a ksh:HoldStatement , ksh:TradeInstruction ;",
        "inconsistent",
        ("src/fmo.ttl", EXAMPLE, TRADING, LINEAGE),
    ),
```

- [ ] **Step 4: Run them to confirm they fail**

Run: `poetry run python3 scripts/test_validate.py 2>&1 | grep -A2 -E "decision|hold"`
Expected: all three validator cases fail with "passed but should have failed". Running `poetry run python3 scripts/test_reason.py` shows the disjointness case firing already, since the axiom is in place. Confirm that deleting `owl:disjointWith ksh:HoldStatement ;` locally makes it report "accepted", then restore it.

- [ ] **Step 5: Implement** in `scripts/validate.py`, after `check_retrievals`:

```python
TRADING_DECISION = URIRef(KSH + "TradingDecision")
DECISION_STATEMENT = URIRef(KSH + "DecisionStatement")
HOLD_STATEMENT = URIRef(KSH + "HoldStatement")
HOLD_REASON = URIRef(KSH + "holdReason")


@check(takes=("data",))
def check_trading_decisions(g: Graph) -> None:
    """A decision cites the copies it read, states one verdict, and follows every fetch it cites.

    Cardinality in OWL entails identity rather than rejecting absence, so the lineage
    the ontology promises is enforced here or not at all.
    """
    decisions = instances_of(g, TRADING_DECISION)
    holds = instances_of(g, HOLD_STATEMENT)
    cited = 0
    for decision in decisions:
        ends = list(g.objects(decision, ENDED_AT))
        copies = [c for c in g.objects(decision, HAS_INPUT) if RETRIEVED_COPY in types_of(g, c)]
        statements = [s for s in outputs_of(g, decision) if DECISION_STATEMENT in types_of(g, s)]
        if not copies:
            fail(f"{decision}: a trading decision cites no fm:RetrievedCopy, "
                 f"so nothing it read can be traced")
        if len(statements) != 1:
            fail(f"{decision}: a trading decision needs exactly one ksh:DecisionStatement "
                 f"as output, has {len(statements)}")
        if len(ends) != 1:
            fail(f"{decision}: a trading decision needs exactly one prov:endedAtTime, has {len(ends)}")
            continue
        try:
            decided = aware_instant(ends[0])
        except (ValueError, TypeError) as exc:
            fail(f"{decision}: cannot read prov:endedAtTime: {exc}")
            continue
        for copy in copies:
            retrievals = set(g.subjects(HAS_OUTPUT, copy)) | set(g.objects(copy, IS_OUTPUT_OF))
            for retrieval in retrievals:
                for fetched in g.objects(retrieval, ENDED_AT):
                    try:
                        fetched_at = aware_instant(fetched)
                    except (ValueError, TypeError):
                        continue  # check_retrievals reports it
                    cited += 1
                    if fetched_at > decided:
                        fail(f"{decision} decided at {decided.isoformat()} on {copy}, which "
                             f"{retrieval} fetched later, at {fetched_at.isoformat()}")
    for hold in holds:
        reasons = list(g.objects(hold, HOLD_REASON))
        if len(reasons) != 1:
            fail(f"{hold}: a hold statement needs exactly one ksh:holdReason, has {len(reasons)}")
    coverage("trading decisions", len(decisions),
             "decision(s) checked for a cited copy, one statement and one end time",
             "no example asserts a ksh:TradingDecision")
    coverage("decision after retrieval", cited, "cited fetch(es) ordered before their decision",
             "no decision cites a copy whose retrieval has an end time")
    coverage("hold reasons", len(holds), "hold statement(s) checked for one reason",
             "no example asserts a ksh:HoldStatement")
```

- [ ] **Step 6: Run the checks**

Run: `poetry run python3 scripts/validate.py && poetry run python3 scripts/test_validate.py 2>&1 | grep -E "decision|hold|FAIL"`
Expected: `trading decisions: 2`, `decision after retrieval: 3`, `hold reasons: 1` and `OK`. The three cases print `ok`, and no `FAIL` line appears.

- [ ] **Step 7: Classify the axioms, then run the gate.** In `queries/axiom-expectations.json`:
  - Pin `kalshi.ttl: ksh:TradeInstruction disjointWith ksh:HoldStatement` (exact key from `make axioms`) to `"a decision statement typed both trade instruction and hold statement"`.
  - Exempt the covering union with `"A covering axiom under the open-world assumption: a statement typed only ksh:DecisionStatement is inferred to be one of the two, never rejected."`.
  - Exempt the two existential restrictions on `ksh:TradingDecision` with `"A modelling commitment about what the class involves, not a constraint well-formed data can violate. check_trading_decisions enforces presence on the data."`.

Run: `make meta reason reason-negative axioms shapes cq diagram-check`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add src/kalshi.ttl scripts/validate.py scripts/test_validate.py scripts/test_reason.py \
  examples/kxhighny-2026-08-15-lineage.ttl queries/axiom-expectations.json
git commit -m "Add trading decisions with trade and hold statements, traced to retrieved copies (FM-0022)"
```

---

### Task 5: CQ9, decision lineage

**Files:**
- Create: `queries/cq09-decision-lineage.rq`, `queries/cq09-decision-lineage.expected` (generated, then reviewed)

**Interfaces:**
- Consumes: every term and individual from Tasks 2–4.

- [ ] **Step 1: Write the query** at `queries/cq09-decision-lineage.rq`:

```sparql
# CQ9. What did each trading decision read, and was a newer issuance out when it decided?
#
# Inputs are reached through rdfs:subPropertyOf* prov:used, not fm:hasInput by
# name, so this answering at all is what shows the alignment holds. A copy of
# content with no issuance time -- a quote -- still returns its row.

SELECT ?decision ?verdict ?copy ?endpoint ?fetchedAt ?issuedAt ?newerIssuance
WHERE {
    ?decision a/rdfs:subClassOf* ksh:TradingDecision ;
              prov:endedAtTime ?decidedAt ;
              fm:hasOutput ?statement .
    ?statement a ?verdict .
    ?verdict rdfs:subClassOf ksh:DecisionStatement .

    ?decision ?uses ?copy .
    ?uses rdfs:subPropertyOf* prov:used .
    ?copy a/rdfs:subClassOf* fm:RetrievedCopy ;
          bfo:BFO_0000101 ?content .
    ?retrieval fm:hasOutput ?copy ;
               prov:endedAtTime ?fetchedAt ;
               fm:retrievedFrom ?endpoint .

    OPTIONAL { ?content wx:issuanceTime ?issuedAt }
    OPTIONAL {
        ?content wx:forecastFor ?target .
        ?newerIssuance wx:forecastFor ?target ;
                       wx:issuanceTime ?newerAt .
        FILTER (?newerIssuance != ?content && ?newerAt > ?issuedAt && ?newerAt < ?decidedAt)
    }
}
ORDER BY ?decision ?copy ?newerIssuance
```

- [ ] **Step 2: Run it to see that it fails without an expected file**

Run: `poetry run python3 scripts/run_competency.py 2>&1 | grep cq09`
Expected: a failure for `cq09-decision-lineage.rq` about the missing `.expected`.

- [ ] **Step 3: Generate and review the expected rows**

Run: `make cq-update && cat queries/cq09-decision-lineage.expected`
Expected:
- Three rows.
- `lex:Decision-Hold` with `lex:Copy-06Z` has `?newerIssuance` = `lex:Forecast-GEFS-12Z`.
- `lex:Decision-Hold` with `lex:Copy-Quote-1200Z` has `?issuedAt` and `?newerIssuance` as `-`.
- `lex:Decision-Trade` with `lex:Copy-06Z` has `?newerIssuance` as `-`.

If another forecast for `ex:Target-HighTemp` in the existing examples appears as a newer issuance, check its issuance time against the decision instant. It belongs in the answer only if it falls between the two. Run `git diff queries/` and confirm that only `cq09` changed.

- [ ] **Step 4: Confirm the alignment is what the query rides on.** Delete `rdfs:subPropertyOf prov:used ;` from `fm:hasInput` in a scratch copy of `src/core.ttl`, then run `poetry run python3 scripts/run_competency.py`. Expected: `cq09` fails as empty. Restore the file.

- [ ] **Step 5: Commit**

```bash
git add queries/cq09-decision-lineage.rq queries/cq09-decision-lineage.expected
git commit -m "Add CQ9: decision lineage and stale inputs (FM-0022)"
```

---

### Task 6: Version bump, vocabulary and documentation

**Files:**
- Modify: `src/core.ttl`, `src/weather.ttl`, `src/kalshi.ttl`, `src/fmo.ttl` (headers), `README.md`, `CONTEXT.md`, `docs/design-notes.md`, `src/imports/` README row

- [ ] **Step 1: Bump every module.** In each of the four module headers, set `owl:versionIRI <…/<module>/0.21.0>`, `owl:priorVersion <…/<module>/0.20.0>` and `owl:versionInfo "0.21.0"`, and add `owl:incompatibleWith <…/<module>/0.20.0>`. In `README.md`, change the status line's `0.20.0` to `0.21.0`.

Run: `make lineage`
Expected: passes. The prior version resolves to 0.20.0 and no released IRI went dark.

- [ ] **Step 2: Add vocabulary** to `CONTEXT.md`, in the section that holds `**Record**`, after the `**Correction**` entry:

```markdown
**Retrieval** (`fm:Retrieval`) / **retrieved copy** (`fm:RetrievedCopy`): fetching
content makes a new carrier of the same information content entity, never new
content. The copy is ours; the content is the issuer's. A decision cites the copy.
_Avoid_: "record" for the copy (see **Record**), and "the data" for either.

**Data handling process** (`fm:DataHandlingProcess`): what the system does to
content for its own use. Its parent is not `fm:InformationProcess`, because a
retrieval produces no new content.

**Trading decision** (`ksh:TradingDecision`) / **decision statement**
(`ksh:DecisionStatement`): a decision always has a statement, a
**trade instruction** (`ksh:TradeInstruction`) or a **hold statement**
(`ksh:HoldStatement`). A hold is a decision, not the absence of one.
_Avoid_: "trade" for the instruction — `ksh:Trade` is the exchange matching orders.
_Avoid_ also "outcome" for the verdict, which is the market side's word.
```

In the **Correction** entry's _Avoid_ line, append: `` `prov:wasRevisionOf` is PROV's name for supersedes; "revision" stays out of prose. `` In the example-prefix list near line 315, add `` `lex:` (lineage) ``.

- [ ] **Step 3: Add the design note** to `docs/design-notes.md`, after "CF standard names, and not SOSA":

```markdown
## PROV-O, and not SOSA

Added in FM-0022. SOSA was declined because it duplicated an observation pattern FMO
already had and would have been a second model to argue with. PROV-O fills a gap
instead: FMO could say who issued a document and which one a settlement read, but
not how content reached ThermalEdge or what a decision read. That is lineage, which
is what PROV-O is for.

**A subset, grounded.** `src/imports/prov-subset.ttl` is generated from the pinned
W3C file. `prov:Entity` sits under continuant, so PROV-DM's entity/activity
disjointness is BFO's own, and an occurrent used as an input is a HermiT
inconsistency. `prov:Agent` is under continuant rather than `fm:Agent`, because
`fm:Agent` is material and the agent of a fetch is usually software.

**Aligned, not replaced.** `fm:hasInput`, `fm:isOutputOf`, `fm:issuedBy`,
`fm:hasAgent` and `wx:supersedes` are sub-properties of their PROV counterparts, so
a PROV query walks FMO data unchanged. `wx:issuanceTime` is deliberately not
`prov:generatedAtTime`: issuance is publication, not creation.

**Copies, not records.** A retrieval's output is a carrier of the issuer's content,
not new content, which is why `fm:DataHandlingProcess` is not an information
process. A later transformation step will be, and will sit beside retrieval.
```

- [ ] **Step 4: Update the README file table.** Add the row `` | `src/imports/prov-subset.ttl` | 4 classes + 8 properties extracted from PROV-O (generated) | `` after the QUDT subset row, and `` | `scripts/extract_prov_subset.py` | regenerates the PROV-O subset from the pinned W3C file | `` after the QUDT extractor row. Add `make prov` wherever the README lists `make qudt`.

- [ ] **Step 5: Run the whole suite**

Run: `make test`
Expected: every target passes, including `validate` (prose checks resolve every new backticked term, path and check), `lineage`, `meta`, `axioms` and `competency`.

- [ ] **Step 6: Commit**

```bash
git add src/*.ttl README.md CONTEXT.md docs/design-notes.md
git commit -m "Release 0.21.0: PROV-O import and decision lineage (FM-0022)"
```
