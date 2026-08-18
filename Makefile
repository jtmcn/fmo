# Wantology build and check targets.
#
# `make setup` installs everything. ROBOT is optional: set ROBOT_JAR=/path/to/robot.jar,
# drop robot.jar in this directory, or put `robot` on PATH. Without it, `validate` still
# runs; reasoner targets skip with a notice.

SRC     := src
BUILD   := build
CATALOG := $(SRC)/catalog-v001.xml
TOP     := $(SRC)/wantology.ttl
EXAMPLES := $(wildcard examples/*.ttl)

PY      := poetry run python3

ifdef ROBOT_JAR
ROBOT := java -jar $(ROBOT_JAR)
else ifneq ($(wildcard robot.jar),)
ROBOT := java -jar robot.jar
else
ROBOT := $(shell command -v robot 2>/dev/null)
endif

.PHONY: all setup test validate validate-negative cq cq-update reason competency merge qudt verification-data verification-data-check clean

all: validate

## One-time setup: Python deps via poetry, plus robot.jar if it is not already around.
setup:
	poetry install
	@command -v robot >/dev/null || [ -f robot.jar ] || \
		curl -fsSL -o robot.jar https://github.com/ontodev/robot/releases/latest/download/robot.jar
	@command -v java >/dev/null || echo "NOTE: no java found; \`brew install openjdk\` to enable make reason"
	@$(MAKE) --no-print-directory validate

## Structural checks: parsing, BFO grounding, disjointness, unit coherence, docs. No Java.
validate:
	$(PY) scripts/validate.py

## Negative tests: prove the validator actually fails on each defect it claims to catch.
validate-negative:
	$(PY) scripts/test_validate.py

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
m=URIRef('https://w3id.org/wantology/examples/kxhighny-2026-08-15#Market-B82'); \
t=[str(x) for x in g.objects(m, RDF.type)]; \
sys.exit('FAIL: ksh:WeatherMarket not inferred; got %s' % t) if not any('WeatherMarket' in x for x in t) \
else print('PASS: ksh:WeatherMarket inferred from the proposition-subject chain')"
endif

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
test: validate validate-negative verification-data-check cq reason competency

clean:
	rm -rf $(BUILD)
