# FMO build and check targets.
#
# `make setup` installs everything. ROBOT is optional: set ROBOT_JAR=/path/to/robot.jar,
# drop robot.jar in this directory, or put `robot` on PATH. Without it, `validate` still
# runs; reasoner targets skip with a notice.

SRC     := src
BUILD   := build
CATALOG := $(SRC)/catalog-v001.xml
TOP     := $(SRC)/fmo.ttl
EXAMPLES := $(wildcard examples/*.ttl)
PYSCRIPTS := $(wildcard scripts/*.py)
MISMATCH := examples/negative/thermaledge-target-mismatch.ttl
SHAPEPIN := shapes/thermaledge-export.pin.json

PY_BIN  := poetry run
PY      := $(PY_BIN) python3

ifdef ROBOT_JAR
ROBOT := java -jar $(ROBOT_JAR)
else ifneq ($(wildcard robot.jar),)
ROBOT := java -jar robot.jar
else
ROBOT := $(shell command -v robot 2>/dev/null)
endif

.PHONY: all setup test typecheck typecheck-negative validate validate-negative meta shapes shapes-negative export-check cq cq-update reason reason-negative axioms signatures shape-signatures shape-signatures-update competency merge qudt verification-data verification-data-check diagram diagram-check clean

all: validate

## One-time setup: Python deps via poetry, plus robot.jar if it is not already around.
setup:
	poetry install
	@command -v robot >/dev/null || [ -f robot.jar ] || \
		curl -fsSL -o robot.jar https://github.com/ontodev/robot/releases/latest/download/robot.jar
	@command -v java >/dev/null || echo "NOTE: no java found; \`brew install openjdk\` to enable make reason"
	@$(MAKE) --no-print-directory validate

## Static types over the checking scripts. ty is pinned exactly in the dev group:
## it is 0.0.x and says diagnostics may change between any two versions, so an
## unpinned bump would redden a clean tree for reasons outside this repo.
## Files are passed explicitly rather than left to discovery -- `ty check` over
## nothing prints "All checks passed!" and exits 0.
typecheck:
	@[ -n "$(PYSCRIPTS)" ] || { echo "FAIL: no scripts/*.py to type check"; exit 1; }
	$(PY_BIN) ty check $(PYSCRIPTS)

## Negative tests for the target above: prove ty fails on the narrowings this repo
## made, on an error nobody has made yet, and that the target refuses to check nothing.
typecheck-negative:
	$(PY) scripts/test_typecheck.py

## Structural checks: parsing, BFO grounding, disjointness, unit coherence, docs. No Java.
validate:
	$(PY) scripts/validate.py

## Negative tests: prove the validator actually fails on each defect it claims to catch.
validate-negative:
	$(PY) scripts/test_validate.py

## Tests about the checks themselves: every check must fail with nothing to check.
meta:
	$(PY) scripts/test_meta.py

## SHACL conformance: does the data satisfy the ThermalEdge export contract?
## Runs the examples as ONE graph -- they import each other, so a file checked
## alone reports absences that are not real. Pure Python, no Java.
shapes:
	$(PY) scripts/validate_shapes.py --examples
	$(PY) scripts/validate_shapes.py --exports

## Tests about the shapes themselves: no shape may match nothing, no shape may
## fail to catch a missing required property on a node typed as its own
## targetClass, and no sh:class may be dead under rdfs range entailment.
shapes-negative:
	$(PY) scripts/test_shapes.py

## Production CQ mode, both directions. Every export fixture must pass, every
## negative fixture must be rejected, and the target-mismatch fixture must fail
## on CQ2 specifically -- it also fails cq04, so a generic rejection would hide a
## lost cq02 floor.
export-check:
	$(PY) scripts/run_competency.py --exports
	$(PY) scripts/run_competency.py --negatives
	@out=$$($(PY) scripts/run_competency.py --data $(MISMATCH) 2>&1); \
	echo "$$out" | grep -q 'FAIL \[cq02-probability-gap.rq\]' || { \
		echo "FAIL: the mismatch fixture did not fail on cq02 specifically."; \
		echo "$$out" | tail -3; \
		exit 1; }
	@echo "OK: exports pass, negatives are rejected, the mismatch fails on cq02"

## Regenerate the vendored QUDT subset. Needs a qudt-public-repo checkout:
##   git clone --depth 1 https://github.com/qudt/qudt-public-repo.git /tmp/qudt
##   make qudt QUDT_REPO=/tmp/qudt
QUDT_REPO ?= /tmp/qudt
qudt:
	$(PY) scripts/extract_qudt_subset.py $(QUDT_REPO)

## Regenerate the synthetic verification dataset for CQ6. Deterministic (fixed
## seed), so a diff means the generator changed, not the data.
verification-data:
	$(PY) scripts/generate_verification_data.py

## Fail if the checked-in synthetic dataset no longer matches its generator.
## The file is 7000 generated lines; nothing else would notice a hand-edit.
verification-data-check:
	@mkdir -p $(BUILD)
	@$(PY) scripts/generate_verification_data.py --output $(BUILD)/verification-synthetic.ttl >/dev/null
	@cmp -s examples/verification-synthetic.ttl $(BUILD)/verification-synthetic.ttl || { \
		echo "FAIL: examples/verification-synthetic.ttl does not match its generator."; \
		echo "      Run 'make verification-data' and review the diff."; \
		exit 1; }
	@echo "OK: synthetic dataset matches its generator"

## Competency questions 1, 2, 4, 5, 6 and 7: run queries/*.rq against checked-in results.
## An empty result set fails -- a query matching nothing is how a broken check looks fine.
##   make cq-update   regenerates the .expected files; review the diff before committing.
cq:
	$(PY) scripts/run_competency.py

cq-update:
	$(PY) scripts/run_competency.py --update

## HermiT consistency over the schema, then over schema plus examples.
reason: $(BUILD)/merged.owl $(BUILD)/full.owl
ifeq ($(strip $(ROBOT)),)
	@echo "SKIP reason: ROBOT not found. Set ROBOT_JAR or put robot on PATH."
	@echo "  https://github.com/ontodev/robot/releases"
else
	@echo "== reasoning over schema =="
	$(ROBOT) reason --input $(BUILD)/merged.owl --reasoner HermiT --output $(BUILD)/reasoned.owl
	@echo "== reasoning over schema + examples =="
	$(ROBOT) reason --input $(BUILD)/full.owl --reasoner HermiT --output $(BUILD)/full-reasoned.owl
	@echo "consistent"
endif

## Prove the reasoner-only guards fire: the axioms validate.py cannot check.
## Skips with a notice when ROBOT or Java is missing or does not run. Unlike
## `make reason`, which detects ROBOT here by presence and so fails on a stub java.
reason-negative:
	$(PY) scripts/test_reason.py

## Every axiom is pinned by a reasoner case or exempt with a reason, and every
## `pinned` claim is re-verified by deleting the axiom. Skips without a ROBOT that
## runs; a $ROBOT_JAR that does not run fails instead, since naming one is a decision.
axioms:
	$(PY) scripts/check_axioms.py

## Per-term semantic digests for downstream consumers to pin against. --check
## proves they are reproducible; a signature that churns is not a pin.
signatures:
	$(PY) scripts/term_signatures.py --check

## Per-shape structured signatures for downstream consumers to pin against, FMO's
## own pin on the export contract, and the classifier behind both. Audit last:
## an unreproducible signature or a broken classifier makes its verdict meaningless,
## so both are proved before the verdict is believed.
shape-signatures:
	$(PY) scripts/shape_signatures.py --check
	$(PY) scripts/test_shape_drift.py
	$(PY) scripts/shape_signatures.py --audit $(SHAPEPIN)

## Re-pin the export contract after an intended shapes change. Review the diff
## before committing, like cq-update.
shape-signatures-update:
	$(PY) scripts/shape_signatures.py --update $(SHAPEPIN)

## Competency question 3: weaken an assertion and confirm the reasoner re-derives it.
## Proves ksh:WeatherMarket is a working defined class, not decoration. Needs a
## reasoner, unlike `make cq`, because the answer is inferred rather than asserted.
competency:
ifeq ($(strip $(ROBOT)),)
	@echo "SKIP competency: ROBOT not found."
else
	@mkdir -p $(BUILD)
	@sed 's/ex:Market-B82 a ksh:WeatherMarket ;/ex:Market-B82 a ksh:Market ;/' \
		examples/kxhighny-2026-08-15.ttl > $(BUILD)/ex-weak.ttl
	@cmp -s examples/kxhighny-2026-08-15.ttl $(BUILD)/ex-weak.ttl && { \
		echo "FAIL: the sed anchor no longer matches, so nothing was weakened;"; \
		echo "      the reasoner would be handed the asserted type and 'pass'."; \
		exit 1; } || true
	$(ROBOT) merge --input $(TOP) --input $(BUILD)/ex-weak.ttl --catalog $(CATALOG) \
		reason --reasoner HermiT --axiom-generators "ClassAssertion" \
		--output $(BUILD)/weak-reasoned.ttl
	@$(PY) -c "import sys; from rdflib import Graph, RDF, URIRef; \
g=Graph(); g.parse('$(BUILD)/weak-reasoned.ttl'); \
m=URIRef('https://w3id.org/forecast-market-ontology/examples/kxhighny-2026-08-15#Market-B82'); \
t=[str(x) for x in g.objects(m, RDF.type)]; \
sys.exit('FAIL: ksh:WeatherMarket not inferred; got %s' % t) if not any('WeatherMarket' in x for x in t) \
else print('PASS: ksh:WeatherMarket inferred from the proposition-subject chain')"
endif

## Build the interactive map: build/ontology.html, self-contained, opens by
## double-clicking. Frontend sources live in viz/; this only injects the data.
## Always rebuilds; it takes under a second and the inputs span src/ and viz/.
diagram:
	$(PY) scripts/generate_diagram.py

## Assert the extraction still finds every stanza and the README's pivot edges.
## A viewer that quietly drops half the graph still renders a convincing picture.
diagram-check:
	$(PY) scripts/generate_diagram.py --check

merge: $(BUILD)/merged.owl $(BUILD)/full.owl

$(BUILD)/merged.owl: $(TOP) $(SRC)/core.ttl $(SRC)/weather.ttl $(SRC)/kalshi.ttl $(SRC)/imports/qudt-subset.ttl $(CATALOG)
	@mkdir -p $(BUILD)
ifeq ($(strip $(ROBOT)),)
	@echo "SKIP merge: ROBOT not found."
else
	$(ROBOT) merge --input $(TOP) --catalog $(CATALOG) --output $@
endif

$(BUILD)/full.owl: $(BUILD)/merged.owl $(EXAMPLES)
	@mkdir -p $(BUILD)
ifeq ($(strip $(ROBOT)),)
	@echo "SKIP merge: ROBOT not found."
else
	$(ROBOT) merge --input $(TOP) $(foreach e,$(EXAMPLES),--input $(e)) \
		--catalog $(CATALOG) --output $@
endif

## Everything.
test: typecheck typecheck-negative validate validate-negative meta shapes shapes-negative export-check verification-data-check diagram-check cq reason reason-negative axioms signatures shape-signatures competency

clean:
	rm -rf $(BUILD)
