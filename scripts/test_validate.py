#!/usr/bin/env python3
"""Negative tests for scripts/validate.py and scripts/run_competency.py.

A check that has only ever been seen to pass is not known to work. Each case here
introduces one specific defect into a copy of the tree, runs the checker, and asserts it
fails with the expected message. The source tree is never modified.

Run: python3 scripts/test_validate.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = "examples/kxhighny-2026-08-15.ttl"
BRACKETS = "examples/kxhighny-2026-08-15-bracketset.ttl"
CORRECTION = "examples/kxhighny-2026-08-15-correction.ttl"
VERIFICATION = "examples/verification-synthetic.ttl"
TRADING = "examples/kxhighny-2026-08-15-trading.ttl"

# (name, path-to-mutate, find, replace, substring expected in the failure output)
CASES = [
    (
        # The rename that strands the vocabulary file: nothing but validate.py reads
        # CONTEXT.md, so a term renamed in src/ leaves its prose mention dangling and
        # every other check stays green.
        # Exercises check_context_terms.
        "CONTEXT.md naming a term that no longer exists",
        "CONTEXT.md",
        "`fm:MarketImpliedProbability`",
        "`fm:MarketImpliedProbability_renamed`",
        "CONTEXT.md names an undeclared term: fm:MarketImpliedProbability_renamed",
    ),
    (
        # The escape hatch is narrow: strikethrough exempts a rejected name, plain
        # backticks do not, or "never write bare event" could smuggle any typo through.
        "a rejected name in CONTEXT.md written without its strikethrough",
        "CONTEXT.md",
        "**event, ~~`ksh:Event`~~ \u2192 `ksh:EventGrouping`.**",
        "**event, `ksh:Event` \u2192 `ksh:EventGrouping`.**",
        "CONTEXT.md names an undeclared term: ksh:Event",
    ),
    (
        # Retirement the OWL way: declaration dropped, tombstone kept. Subject of plenty
        # of triples still, so "mentioned somewhere in src/" read it as alive.
        "CONTEXT.md naming a term left behind as a deprecated tombstone",
        "src/kalshi.ttl",
        "ksh:Payout a owl:Class ;",
        "ksh:Payout owl:deprecated true ;",
        "CONTEXT.md names a deprecated term: ksh:Payout",
    ),
    (
        "CONTEXT.md naming an example individual that does not exist",
        "CONTEXT.md",
        "`tex:` (trading)",
        "`tex:NoSuchLot` (trading)",
        "CONTEXT.md names an undefined individual: tex:NoSuchLot",
    ),
    (
        # §4 is repo mechanics end to end, so paths, make targets and check names rot
        # the same way a renamed term does and were the half nothing watched.
        "CONTEXT.md naming a source path that does not exist",
        "CONTEXT.md",
        "`src/weather.ttl`",
        "`src/weather-side.ttl`",
        "CONTEXT.md names a missing path: src/weather-side.ttl",
    ),
    (
        "CONTEXT.md naming a make target that does not exist",
        "CONTEXT.md",
        "from `make diagram`",
        "from `make diagrams`",
        "CONTEXT.md names a missing make target: diagrams",
    ),
    (
        "CONTEXT.md naming a validator check that does not exist",
        "CONTEXT.md",
        "`check_current_assessments`",
        "`check_current_assessment`",
        "CONTEXT.md names a missing check: check_current_assessment",
    ),
    (
        # The other direction, and the reason §4's traversals are counted: with no
        # check name backticked, the guard against "CONTEXT.md names a missing check"
        # matches nothing and passes. Emptied through the regex rather than by
        # unbackticking, like the three cases below -- CONTEXT.md named exactly one
        # check when this was written and now names two, and a case that has to be
        # re-anchored every time §4 gains a sentence is a case that will be deleted.
        "CONTEXT.md naming no validator check at all",
        "scripts/validate.py",
        """CONTEXT_CHECK = re.compile(r"`(check_""",
        """CONTEXT_CHECK = re.compile(r"`zz(check_""",
        "prose checks: nothing to check",
    ),
    (
        "CONTEXT.md backticking no term at all",
        "scripts/validate.py",
        """CONTEXT_TERM = re.compile(rf"(?<!~)`({'|'.join(CONTEXT_PREFIXES)}):""",
        """CONTEXT_TERM = re.compile(rf"(?<!~)`zz({'|'.join(CONTEXT_PREFIXES)}):""",
        "prose terms: nothing to check",
    ),
    (
        "CONTEXT.md backticking no repo path at all",
        "scripts/validate.py",
        """CONTEXT_PATH = re.compile(r"`((?:src""",
        """CONTEXT_PATH = re.compile(r"`zz((?:src""",
        "prose paths: nothing to check",
    ),
    (
        "CONTEXT.md naming no make target at all",
        "scripts/validate.py",
        """CONTEXT_MAKE = re.compile(r"`make """,
        """CONTEXT_MAKE = re.compile(r"`makezz """,
        "prose make targets: nothing to check",
    ),
    (
        # Exercises check_dimensions.
        "Celsius threshold against a Fahrenheit target",
        EXAMPLE,
        """    fm:capValue "83"^^xsd:decimal ;
    fm:hasUnit unit:DEG_F ;""",
        """    fm:capValue "83"^^xsd:decimal ;
    fm:hasUnit unit:DEG_C ;""",
        "unit mismatch (proposition threshold vs target)",
    ),
    (
        "length unit on a temperature target",
        EXAMPLE,
        """    wx:underProtocol ex:TWCDailyTempProtocol ;
    fm:hasUnit unit:DEG_F .""",
        """    wx:underProtocol ex:TWCDailyTempProtocol ;
    fm:hasUnit unit:IN .""",
        "dimension mismatch (proposition threshold vs target)",
    ),
    (
        "datum reported in Celsius for a Fahrenheit target",
        EXAMPLE,
        """    fm:realizedValue "82"^^xsd:decimal ;
    fm:hasUnit unit:DEG_F .""",
        """    fm:realizedValue "82"^^xsd:decimal ;
    fm:hasUnit unit:DEG_C .""",
        "unit mismatch (datum vs target)",
    ),
    (
        "a target with no measurement protocol at all",
        EXAMPLE,
        """    wx:underProtocol ex:TWCDailyTempProtocol ;
    fm:hasUnit unit:DEG_F .

################################################################
# 4. The proposition""",
        """    fm:hasUnit unit:DEG_F .

################################################################
# 4. The proposition""",
        "does not name exactly one protocol",
    ),
    (
        # F1 as a modelling error: the exchange settles on one determination while
        # the proposition names another. Nothing related the two before ksh:sourceProtocol.
        "settlement source publishing under a protocol the target does not name",
        EXAMPLE,
        "    ksh:sourceProtocol ex:TWCDailyTempProtocol ;",
        "    ksh:sourceProtocol ex:NWSDailyClimateProtocol ;",
        "settles on a different protocol than its proposition names",
    ),
    (
        # Precedence, not union: a grouping overriding its series is a correct model
        # (it is the 2026-08-14 migration), so the check must resolve to the grouping
        # source and compare it -- not reject the market for reaching two sources.
        "a grouping overriding its series with a disagreeing settlement source",
        EXAMPLE,
        """ex:KXHIGHNY-26AUG15 a ksh:EventGrouping ;
    rdfs:label "Kalshi: NYC high on 2026-08-15" ;
    ksh:eventTicker "KXHIGHNY-26AUG15" ;
    ksh:inSeries ex:KXHIGHNY ;""",
        """ex:NWSSettlementSource a ksh:SettlementSource ;
    rdfs:label "NWS daily climate report for CLINYC" ;
    ksh:sourceProtocol ex:NWSDailyClimateProtocol ;
    fm:issuedBy ex:NWS .

ex:KXHIGHNY-26AUG15 a ksh:EventGrouping ;
    rdfs:label "Kalshi: NYC high on 2026-08-15" ;
    ksh:eventTicker "KXHIGHNY-26AUG15" ;
    ksh:inSeries ex:KXHIGHNY ;
    ksh:settlementSource ex:NWSSettlementSource ;""",
        "settles on a different protocol than its proposition names",
    ),
    (
        # Zero-coverage guard for the target half of check_protocols. Mutated in the
        # checker per the settlement-value template: every example target carries the
        # type, so no single-anchor data edit can empty the traversal -- and a retyped
        # target would otherwise reduce the check to "0 targets checked, OK".
        "the target-protocol check traverses nothing",
        "scripts/validate.py",
        """WEATHER_TARGET = URIRef(WX + "WeatherObservationTarget")""",
        """WEATHER_TARGET = URIRef(WX + "WeatherObservationTarget_renamed")""",
        "the wx:WeatherObservationTarget typing is broken",
    ),
    (
        # The bug this check exists for: re-pointing the settlement source renamed
        # ex:NWSDailyClimateProtocol, and verification-synthetic.ttl went on
        # referencing it for all 40 days. Every other check stayed green.
        # Exercises check_defined_terms.
        "a referenced individual no longer exists",
        EXAMPLE,
        """    wx:underProtocol ex:TWCDailyTempProtocol ;""",
        """    wx:underProtocol ex:RenamedAwayProtocol ;""",
        "undefined term referenced in examples",
    ),
    (
        # The same defect one namespace over: this PR deleted ksh:Settled, and the
        # check only looked at example-namespace IRIs, so a stale reference passed.
        # rdfs:range means HermiT infers the type rather than objecting.
        "a referenced schema individual no longer exists",
        EXAMPLE,
        """    ksh:hasStatus ksh:Finalized ;""",
        """    ksh:hasStatus ksh:Settled ;""",
        "undefined term referenced in examples",
    ),
    (
        # The misalignment the bridge relation exists to make detectable: score the
        # forecast against the NWS determination while the market settles on TWC.
        # Both targets are real and declared alternative determinations, so nothing
        # is dangling and nothing is unrooted -- only the authorities differ.
        "forecast scored against a different authority than the market settles on",
        EXAMPLE,
        """    wx:forecastFor ex:Target-HighTemp ;""",
        """    wx:forecastFor ex:Target-HighTemp-NWS ;""",
        "forecast target is not the subject of the proposition",
    ),
    (
        # Zero-coverage guard for check 6b. Mutated in the checker rather than the
        # data because the synthetic set repeats the has-part link 160 times, so no
        # single-anchor edit can empty the traversal -- and a renamed BFO IRI is the
        # refactor that would silently reduce the check to "0 pairs checked, OK".
        "check_forecast_targets traverses nothing",
        "scripts/validate.py",
        """    has_part = URIRef(BFO + "BFO_0000178")""",
        """    has_part = URIRef(BFO + "BFO_0000178_renamed")""",
        "the has-part or assignsProbabilityTo chain is broken",
    ),
    (
        # Exercises check_declared_properties. Never had a negative test: the rule
        # is "new check => new negative test", and this was an inline body in
        # main() rather than a check, so nothing bound it.
        "an example using a property no module declares",
        EXAMPLE,
        """    wx:underProtocol ex:TWCDailyTempProtocol ;""",
        """    wx:underProtocol ex:TWCDailyTempProtocol ;
    wx:undeclaredProbe "probe" ;""",
        # The filename, not just the message: reading each example file separately
        # is why the meta sweep empties this one through EXAMPLES rather than the
        # graph, and a rewrite onto the merged graph would still say "uses
        # undeclared property".
        "kxhighny-2026-08-15.ttl uses undeclared property: "
        "https://w3id.org/forecast-market-ontology/weather#undeclaredProbe",
    ),
    (
        # Exercises check_bfo_grounding.
        "class unrooted from BFO",
        "src/kalshi.ttl",
        """ksh:Position a owl:Class ;
    rdfs:subClassOf fm:InformationContentEntity ;""",
        """ksh:Position a owl:Class ;""",
        "not grounded in BFO",
    ),
    (
        # check_forecast_market_join. Was reachable by downgrading the temperature
        # example's only forecast probability. The rain example adds a second, independent join, so that
        # mutation now leaves one proposition joined rather than zero. Mutated in
        # the checker instead, like the zero-coverage guard above: renaming the
        # class the join check looks for empties with_forecast regardless of how
        # many examples contribute.
        "the join check no longer finds any forecast probability",
        "scripts/validate.py",
        """        p for s in g.subjects(RDF.type, URIRef(FM + "ForecastProbability"))""",
        """        p for s in g.subjects(RDF.type, URIRef(FM + "ForecastProbability_renamed"))""",
        "the forecast/market join is not demonstrated",
    ),
    (
        # A stored derived value that no longer matches its inputs. Silent without
        # this check, and CQ6 would bucket the forecast by the wrong lead time.
        "lead time no longer matches issuance and interval start",
        EXAMPLE,
        """    wx:leadTimeHours "-4.667"^^xsd:decimal ;""",
        """    wx:leadTimeHours "24"^^xsd:decimal ;""",
        "wx:leadTimeHours says",
    ),
    (
        # The guard nobody wrote. Every other traversal had a hand-written
        # zero-coverage guard and this one did not, so a graph where every forecast
        # lost its lead time reported "0 checked" and passed. coverage() now issues
        # the guard, and test_meta.py proves every check has one.
        "the lead-time check traverses nothing",
        "scripts/validate.py",
        """    for forecast, stated in g.subject_objects(LEAD_HOURS):""",
        """    for forecast, stated in g.subject_objects(URIRef("https://example.invalid/none")):""",
        "lead times: nothing to check",
    ),
    (
        # Exercises check_branch_disjointness.
        "information artifact misfiled as a process",
        "src/kalshi.ttl",
        """ksh:Resolution a owl:Class ;
    rdfs:subClassOf fm:InformationContentEntity ;""",
        """ksh:Resolution a owl:Class ;
    rdfs:subClassOf fm:InformationContentEntity , bfo:BFO_0000015 ;""",
        "both continuant and occurrent",
    ),
    (
        # Finding: a missing unit used to be `continue`d, so deleting one made the
        # comparison vanish rather than fail -- an omission is as likely a slip as
        # a wrong unit, and only the wrong-unit case had coverage.
        "threshold with a numeric value but no unit at all",
        EXAMPLE,
        """    fm:capValue "83"^^xsd:decimal ;
    fm:hasUnit unit:DEG_F ;""",
        """    fm:capValue "83"^^xsd:decimal ;""",
        "carries a numeric value but no fm:hasUnit",
    ),
    (
        # fm:hasUnit is functional, so HermiT catches this -- but `make reason` is
        # the Java-optional path, and unit_of used to take units[0] from an
        # unordered list, which is precisely the Celsius/Fahrenheit defect above.
        "two units on one term, so the unit check picks one arbitrarily",
        EXAMPLE,
        """    fm:capValue "83"^^xsd:decimal ;
    fm:hasUnit unit:DEG_F ;""",
        """    fm:capValue "83"^^xsd:decimal ;
    fm:hasUnit unit:DEG_F , unit:DEG_C ;""",
        "ambiguous unit",
    ),
    (
        # Used to raise an uncaught TypeError (naive minus aware), which killed
        # every later check and report() with it, so the operator got a traceback
        # instead of the file and term at fault.
        "issuance time written without a UTC offset",
        EXAMPLE,
        """    wx:issuanceTime "2026-08-15T09:40:00Z"^^xsd:dateTime ;""",
        """    wx:issuanceTime "2026-08-15T09:40:00"^^xsd:dateTime ;""",
        "cannot measure lead time from issuance",
    ),
    (
        # forecastFor is not functional, so a second target left the lead time
        # checked against whichever one rdflib yielded first.
        "forecast covering a second target, making its lead time ambiguous",
        EXAMPLE,
        """    bfo:BFO_0000178 ex:ForecastProb-82-83 .     # has continuant part""",
        """    wx:forecastFor ex:Target-LowTemp ;
    bfo:BFO_0000178 ex:ForecastProb-82-83 .     # has continuant part

ex:Target-LowTemp a wx:ObservationTarget ;
    rdfs:label "min temperature at KNYC" ;
    fm:overTemporalInterval ex:ClimDay-2026-08-15 ;
    fm:hasUnit unit:DEG_F .""",
        "lead time is ambiguous",
    ),
    (
        # Exercises check_documentation, which only ever appended to notes, so
        # eight live terms had no definition while CLAUDE.md promised the
        # validator failed without one.
        "a term left without a skos:definition",
        "src/weather.ttl",
        """    skos:definition "The atmospheric quality corresponding to the compass bearing from which a portion of air is moving." .""",
        """    skos:scopeNote "Reported as the bearing the wind blows FROM." .""",
        "no skos:definition: https://w3id.org/forecast-market-ontology/weather#WindDirection",
    ),
    (
        # The disjointness blocks are hand-written enumerations, and fm:ScoringRule
        # was missing from the first one. A vocabulary outside them lets one
        # individual be typed into two at once, which is legal OWL that every other
        # check reads as fine.
        # Exercises check_designation_disjointness.
        "a designation vocabulary left out of every disjointness block",
        "src/kalshi.ttl",
        "                 ksh:MarketStatus ) .",
        "                 ) .",
        "designation vocabulary in no owl:AllDisjointClasses block: "
        "https://w3id.org/forecast-market-ontology/kalshi#MarketStatus",
    ),
    (
        # Exercises check_bridged_grounding, which hard-coded two QUDT IRIs, so
        # the third class the generator adds floated under owl:Thing -- the
        # exact defect it exists to catch.
        "a bridged QUDT class left unrooted",
        "src/core.ttl",
        """qudt:QuantityKindDimensionVector rdfs:subClassOf fm:Designation .""",
        """""",
        "bridged external class not grounded in BFO",
    ),
    (
        # our_classes was built from `a owl:Class` alone, so a class introduced by
        # subClassOf only was invisible to every check rather than merely unrooted.
        # Exercises check_documentation.
        "a class introduced by rdfs:subClassOf without being declared",
        "src/kalshi.ttl",
        """ksh:Position a owl:Class ;""",
        """ksh:UndeclaredPosition rdfs:subClassOf ksh:Position .

ksh:Position a owl:Class ;""",
        "no rdfs:label: https://w3id.org/forecast-market-ontology/kalshi#UndeclaredPosition",
    ),
    (
        # ksh:settlementValue is a sub-property of fm:realizedValue, and rdflib
        # does no reasoning, so the unit rules did not reach the one number the
        # exchange actually pays out on.
        "settlement value recorded in Celsius against a Fahrenheit target",
        EXAMPLE,
        """    ksh:resolvesTo ksh:ResolvedYes ;
    ksh:settlementValue "82"^^xsd:decimal ;
    fm:hasUnit unit:DEG_F .""",
        """    ksh:resolvesTo ksh:ResolvedYes ;
    ksh:settlementValue "82"^^xsd:decimal ;
    fm:hasUnit unit:DEG_C .""",
        "unit mismatch (settlement value vs target)",
    ),
    (
        "settlement value with no unit at all",
        EXAMPLE,
        """    ksh:settlementValue "82"^^xsd:decimal ;
    fm:hasUnit unit:DEG_F .""",
        """    ksh:settlementValue "82"^^xsd:decimal .""",
        "missing unit: https://w3id.org/forecast-market-ontology/examples/kxhighny-2026-08-15#Resolution-B82",
    ),
    (
        # Zero-coverage guard for the settlement-value check. Mutated in the checker
        # rather than the data because the four resolutions live in two files, so no
        # single-anchor edit can empty the traversal -- and a renamed property IRI is
        # the refactor that would silently reduce the check to "0 pairs checked, OK".
        "the settlement-value check traverses nothing",
        "scripts/validate.py",
        """RESOLUTION_OF = URIRef(KSH + "resolutionOf")""",
        """RESOLUTION_OF = URIRef(KSH + "resolutionOf_renamed")""",
        "the resolutionOf or expressesProposition chain is broken",
    ),
    (
        # Demonstrated on 0.7.0: one duplicate assessment moved CQ6b's n from 160
        # to 161 and shifted every calibration statistic, while validate.py said OK.
        "a proposition carries two assessments of the current record",
        VERIFICATION,
        """vex:A-20260701-LE81 a fm:TruthAssessment ;
    fm:assessesProposition vex:P-20260701-LE81 ;""",
        """vex:A-20260701-LE81-DUPLICATE a fm:TruthAssessment ;
    fm:assessesProposition vex:P-20260701-LE81 ;
    fm:assessedTruthValue fm:False ;
    fm:basedOnRecord vex:Report-20260701 ;
    fm:referenceTime "2026-07-02T10:59:59-04:00"^^xsd:dateTime .

vex:A-20260701-LE81 a fm:TruthAssessment ;
    fm:assessesProposition vex:P-20260701-LE81 ;""",
        "more than one current assessment",
    ),
    (
        # Zero-coverage guard for check_current_assessments. Mutated in the
        # checker rather than the data, per the settlement-value template: the
        # verification set alone carries 160 assessments, so no single-anchor
        # data edit can empty the traversal.
        "the assessment check traverses nothing",
        "scripts/validate.py",
        """ASSESSES = URIRef(FM + "assessesProposition")""",
        """ASSESSES = URIRef(FM + "assessesProposition_renamed")""",
        "the assessesProposition chain is broken",
    ),
    (
        # A stored derived value with nothing checking it is the lead-time
        # problem again: it goes stale the moment either input moves.
        "Brier score no longer matches the probability and outcome it scores",
        CORRECTION,
        """    fm:scoreValue "0.2704"^^xsd:decimal ;""",
        """    fm:scoreValue "0.1024"^^xsd:decimal ;""",
        "Brier score mismatch",
    ),
    (
        # Scoring against the settlement-era assessment measures what the exchange
        # did, not what the record says. The whole point of fm:scoredAgainst.
        "score points at an assessment of a superseded record",
        CORRECTION,
        """    fm:scoredAgainst ex:Reassessment-82-83 ;""",
        """    fm:scoredAgainst ex:Assessment-82-83-at-settlement ;""",
        "score rests on a superseded record",
    ),
    (
        # The arithmetic used to treat every non-True value as false, so an
        # indeterminate outcome silently certified probability^2 as correct. A
        # Brier score against an undetermined outcome is undefined, not zero.
        "score points at an assessment with an indeterminate truth value",
        CORRECTION,
        """    fm:assessesProposition ex:Prop-82-83 ;
    fm:assessedTruthValue fm:False ;""",
        """    fm:assessesProposition ex:Prop-82-83 ;
    fm:assessedTruthValue fm:Indeterminate ;""",
        "not fm:True or fm:False",
    ),
    (
        # Zero-coverage guard for check_scores. Mutated in the checker rather than
        # the data, per the settlement-value template: renaming the constant that
        # gates "is this a Brier score" empties the traversal for every score.
        "the score check traverses nothing",
        "scripts/validate.py",
        """BRIER_SCORE = URIRef(FM + "BrierScore")""",
        """BRIER_SCORE = URIRef(FM + "BrierScore_renamed")""",
        "the usesScoringRule or scoresAssignment chain is broken",
    ),
    (
        "a market expresses a proposition about a target its grouping does not cover",
        EXAMPLE,
        """    ksh:expressesProposition ex:Prop-82-83 ;
    ksh:hasStatus ksh:Finalized ;""",
        """    ksh:expressesProposition ex:Prop-82-83-NWS ;
    ksh:hasStatus ksh:Finalized ;""",
        "market covers a different target than its grouping",
    ),
    (
        "two brackets of one mutually exclusive ladder overlap",
        BRACKETS,
        """    fm:hasComparator fm:Between ;
    fm:floorValue "84"^^xsd:decimal ;""",
        """    fm:hasComparator fm:Between ;
    fm:floorValue "83"^^xsd:decimal ;""",
        "overlapping brackets",
    ),
    (
        # interval()'s docstring promises None -- not a traceback -- for a
        # threshold not stated; fm:Between needs both floor and cap.
        "a Between proposition missing its capValue",
        EXAMPLE,
        """    fm:hasSubject ex:Target-HighTemp ;
    fm:hasComparator fm:Between ;
    fm:floorValue "82"^^xsd:decimal ;
    fm:capValue "83"^^xsd:decimal ;""",
        """    fm:hasSubject ex:Target-HighTemp ;
    fm:hasComparator fm:Between ;
    fm:floorValue "82"^^xsd:decimal ;""",
        "its comparator needs a threshold value that is not stated",
    ),
    (
        # Zero-coverage guard for check_grouping_coherence. Mutated in the
        # checker rather than the data, per the settlement-value template: the
        # ladder relationship is repeated across multiple example files, so no
        # single-anchor data edit can empty the traversal.
        "the grouping check traverses nothing",
        "scripts/validate.py",
        """IN_EVENT_GROUPING = URIRef(KSH + "inEventGrouping")""",
        """IN_EVENT_GROUPING = URIRef(KSH + "inEventGrouping_renamed")""",
        "the inEventGrouping or expressesProposition chain is broken",
    ),
    (
        # rdflib Literal truthiness is value-based, so bool(Literal(0)) is False.
        # A settlement of zero read as no settlement at all and skipped the unit
        # comparison this check exists for -- an ordinary value for degF or mm.
        "settlement of zero recorded in Celsius against a Fahrenheit target",
        EXAMPLE,
        """    ksh:settlementValue "82"^^xsd:decimal ;
    fm:hasUnit unit:DEG_F .""",
        """    ksh:settlementValue "0"^^xsd:decimal ;
    fm:hasUnit unit:DEG_C .""",
        "unit mismatch (settlement value vs target)",
    ),
    (
        # Same truthiness bug one function over: a zero value carrying no unit
        # dodged the missing-unit failure entirely.
        "settlement of zero carries no unit at all",
        EXAMPLE,
        """    ksh:settlementValue "82"^^xsd:decimal ;
    fm:hasUnit unit:DEG_F .""",
        """    ksh:settlementValue "0"^^xsd:decimal .""",
        "missing unit",
    ),
    (
        # check_lead_times guards its float() and check_scores did not, so a
        # non-numeric score raised out of main() and every later check was lost.
        "Brier score stated as something non-numeric",
        CORRECTION,
        """    fm:scoreValue "0.2704"^^xsd:decimal ;""",
        """    fm:scoreValue "n/a" ;""",
        "is not numeric",
    ),
    (
        # Absence used to be a skip: the grouping check quietly matched nothing
        # while the counter still reported the pairs as checked.
        "grouping covers no target at all",
        EXAMPLE,
        """    ksh:coversTarget ex:Target-HighTemp ;""",
        """""",
        "does not cover exactly one target",
    ),
    (
        # ksh:coversTarget is not functional, so two targets satisfied the old
        # membership test either way -- and overlaps() then compares brackets on
        # two different determinations as if they were on one.
        "grouping covers two targets",
        EXAMPLE,
        """    ksh:coversTarget ex:Target-HighTemp ;""",
        """    ksh:coversTarget ex:Target-HighTemp , ex:Target-HighTemp-NWS ;""",
        "does not cover exactly one target",
    ),
    (
        # An inverted bracket can never resolve yes, and its overlap results
        # against its neighbours are meaningless rather than merely wrong.
        "bracket whose floor sits above its cap",
        BRACKETS,
        """    fm:floorValue "84"^^xsd:decimal ;""",
        """    fm:floorValue "88"^^xsd:decimal ;""",
        "is above cap",
    ),
    (
        # The trading layer's whole reason for existing is that it says what
        # settles. Paying the side that lost is the one way to get that backwards
        # while every other check stays green: the arithmetic still works, the
        # market still matches, and a trader is still paid.
        "payout to the side the market resolved against",
        TRADING,
        "    fm:hasInput ex:Resolution-B82 , tex:Lot-Yes-A ;",
        "    fm:hasInput ex:Resolution-B82 , tex:Lot-No-B ;",
        "pays the losing side",
    ),
    (
        "payout amount that does not match the lot it pays for",
        TRADING,
        "    ksh:payoutAmountCents 10000 .",
        "    ksh:payoutAmountCents 6000 .",
        "disagrees with what it pays for",
    ),
    (
        # A lot in a different market than the resolution settles. ex:Market-T81 is
        # a sibling bracket in the same grouping, so nothing but this check notices.
        "payout settling one market's contracts on another's determination",
        TRADING,
        """tex:Lot-Yes-A a ksh:YesContract ;
    rdfs:label "100 yes contracts in B82.5, held by A" ;
    ksh:contractInMarket ex:Market-B82 ;""",
        """tex:Lot-Yes-A a ksh:YesContract ;
    rdfs:label "100 yes contracts in B82.5, held by A" ;
    ksh:contractInMarket ex:Market-T81 ;""",
        "payout crosses markets",
    ),
    (
        # A lot with no side at all reached the side comparison and came out as
        # "pays the losing side", which is the wrong diagnosis and sends the reader
        # after the wrong triple. Reachable because nothing but the reasoner stops
        # a lot being typed as the bare contract.
        "a payout on a lot that states no side",
        TRADING,
        """tex:Lot-Yes-A a ksh:YesContract ;
    rdfs:label "100 yes contracts in B82.5, held by A" ;""",
        """tex:Lot-Yes-A a ksh:BinaryContract ;
    rdfs:label "100 yes contracts in B82.5, held by A" ;""",
        "side is not determinate",
    ),
    (
        # Right amount, right side, wrong party. The lot names its holder and the
        # payout reaches one only through the obligation it realizes, so nothing
        # else compares them -- CQ8 reads the trader off the lot and would keep
        # reporting A.
        "a payout realizing the obligation of the trader who did not hold the lot",
        TRADING,
        """tex:Obligation-A a ksh:ContractHolderObligation ;
    rdfs:label "A's contract holder obligation on the yes side of B82.5" ;
    bfo:BFO_0000197 tex:TraderA .""",
        """tex:Obligation-A a ksh:ContractHolderObligation ;
    rdfs:label "A's contract holder obligation on the yes side of B82.5" ;
    bfo:BFO_0000197 tex:TraderB .""",
        "pays the wrong party",
    ),
    (
        # One match made both lots, so they cannot be different sizes. The losing
        # lot never reaches check_payouts -- it has no payout -- so its quantity
        # was read by nothing at all before this check.
        "a match whose two lots are different sizes",
        TRADING,
        """tex:Lot-No-B a ksh:NoContract ;
    rdfs:label "100 no contracts in B82.5, held by B" ;
    ksh:contractInMarket ex:Market-B82 ;
    ksh:contractQuantity 100 ;""",
        """tex:Lot-No-B a ksh:NoContract ;
    rdfs:label "100 no contracts in B82.5, held by B" ;
    ksh:contractInMarket ex:Market-B82 ;
    ksh:contractQuantity 50 ;""",
        "state different quantities",
    ),
    (
        # The coverage guard. The check is a walk over inputs, so a payout that
        # names neither stops matching instead of failing -- which is how the
        # trading layer went unexercised for four versions in the first place.
        "a payout that names no resolution or lot at all",
        TRADING,
        "    fm:hasInput ex:Resolution-B82 , tex:Lot-Yes-A ;",
        "",
        "trading layer is unexercised again",
    ),
    (
        # CONTEXT.md was guarded and README was not, though README backticks 22
        # minted terms and rots from a rename in exactly the same way. The guard
        # was written for one file because that is the file that had just been
        # added, not because the others were safe.
        "README.md naming a term that no longer exists",
        "README.md",
        "`wx:conventionalUnit` is deliberately\n**not** a sub-property of `fm:hasUnit`",
        "`wx:conventionalUnit_renamed` is deliberately\n**not** a sub-property of `fm:hasUnit`",
        "README.md names an undeclared term: wx:conventionalUnit_renamed",
    ),
    (
        # A check that raises used to abort the run, so every check after it was
        # never executed and the output ended in a traceback rather than a verdict.
        # A crash is a failure of that check and nothing more.
        "a check raising an unexpected exception",
        "scripts/validate.py",
        """def check_trades(g: Graph) -> None:""",
        """def check_trades(g: Graph) -> None:
    raise RuntimeError("injected")""",
        "check_trades raised RuntimeError: injected",
    ),
    (
        # The ledger's whole point: a newly minted class that no example reaches
        # must not join the unexercised set silently. Every other check stays green
        # while it happens, which is how the set grew to 36 unnoticed.
        # Exercises check_class_coverage.
        "a minted class that no example instantiates and the ledger does not classify",
        "src/weather.ttl",
        "wx:DewPoint a owl:Class ;",
        """wx:Nephology a owl:Class ;
    rdfs:subClassOf wx:AtmosphericQuality ;
    rdfs:label "nephology" ;
    skos:definition "An injected class, unexercised and unclassified." .

wx:DewPoint a owl:Class ;""",
        "unexercised and not classified: wx:Nephology",
    ),
    (
        # The ledger is required to shrink. An entry left behind after an example
        # starts exercising the class reads as an authoritative claim that nobody
        # has, which is how the axiom ledger's stale exemptions were caught too.
        "the ledger classifying a class the examples do exercise",
        "queries/class-coverage-expectations.json",
        """  "unwritten": {
    "fm:InformationBearingEntity": {""",
        """  "unwritten": {
    "ksh:Market": {
      "reason": "An injected entry for a class the worked examples instantiate."
    },
    "fm:InformationBearingEntity": {""",
        "classified but exercised: ksh:Market",
    ),
    (
        # A rename in src/ leaves the entry pointing at nothing. The reason stays
        # readable and authoritative while describing a class the model no longer
        # has -- the same defect check_axioms catches on its own ledger.
        "the ledger naming a class that no longer exists",
        "queries/class-coverage-expectations.json",
        '"wx:Thunderstorm": {',
        '"wx:Thunderstorm_renamed": {',
        "ledger names a class that does not exist: wx:Thunderstorm_renamed",
    ),
    (
        # unassertable is the only category asserting the ontology REFUSES a class,
        # and one scope note carries that argument for the whole quality group. Reword
        # it away and nine entries keep citing a justification that is no longer written
        # anywhere, while every one of them still reads as settled.
        "the scope note an unassertable entry rests on being removed",
        "src/weather.ttl",
        """    skos:scopeNote "Instances are quality instances that vary continuously.""",
        """    skos:altLabel "Instances are quality instances that vary continuously.""",
        "justification carries no scope note: wx:AirTemperature",
    ),
    (
        # The other half of the pin: a justification that never resolves at all. A typo
        # here is quieter than a reword, because nothing in the file looks wrong.
        "an unassertable entry whose justification names no declared term",
        "queries/class-coverage-expectations.json",
        '"justified_by": "wx:WindSpeed"',
        '"justified_by": "wx:WindSpeed_typo"',
        "unassertable entry names no declared justification: wx:WindSpeed",
    ),
    (
        # unlisted is the one category resting on the world rather than on the model,
        # and the date is the entire claim: 354 series read on one day says nothing
        # about the listings a month later.
        "an unlisted entry with no date saying when the listings were read",
        "queries/class-coverage-expectations.json",
        '"checked": "2026-08-23"',
        '"checked_by": "2026-08-23"',
        "unlisted entry carries no check date: wx:AirMotion",
    ),
    (
        # Two categories flattened into one map: the second silently won, so a class
        # could be recorded as refused by the ontology AND merely unwritten, and the
        # ledger would report whichever category was read last.
        "a class classified under two categories at once",
        "queries/class-coverage-expectations.json",
        '"wx:Snowfall": {',
        '"wx:WindSpeed": {\n      "reason": "An injected duplicate of an unassertable entry."\n    },\n    "wx:Snowfall": {',
        "classified twice: wx:WindSpeed",
    ),
    (
        # A key nothing reads swallowed its entries whole. The block this injects is
        # the one four documents say is derived and never written -- and parking a
        # stale entry under it escaped both staleness guards, so it read as
        # authoritative forever while the run stayed green.
        "the ledger carrying a category nothing reads",
        "queries/class-coverage-expectations.json",
        '  "unlisted": {',
        '  "schema-instantiated": {\n    "ksh:Market": {\n      "reason": "An injected entry under the one category that must never be written."\n    }\n  },\n\n  "unlisted": {',
        "ledger has categories nothing reads: schema-instantiated",
    ),
    (
        # The reason is the entry: every other field is metadata about it. An entry
        # with none still classifies the class and silences the guard, which is a
        # ledger recording that someone once opened the file.
        "a ledger entry classifying a class with no reason given",
        "queries/class-coverage-expectations.json",
        '"reason": "Inherits the unresolved argument on wx:Storm."\n    },\n    "wx:TropicalCyclone"',
        '"reason": "   "\n    },\n    "wx:TropicalCyclone"',
        "classified with no reason given: wx:Thunderstorm in unwritten",
    ),
]


EXPORT = "examples/export/thermaledge-kxhighaus-2026-08-22.ttl"
MISMATCH = "examples/negative/thermaledge-target-mismatch.ttl"

# Defects the SHACL shapes must reject. Run against the examples union, like
# `make shapes`: a shape checked on one file alone fires on absences that are not
# real, because the correction and bracketset files reference a target and
# propositions the base file defines.
#
# Without these the shapes were a checker nobody had watched fail -- and a shape
# that matches no focus node conforms, so a mistargeted sh:targetClass would have
# looked exactly like a clean run.
SHAPES_CASES = [
    (
        # The rule the whole ontology turns on: the target carries the protocol.
        "a target stripped of its measurement protocol",
        EXAMPLE,
        """    wx:underProtocol ex:TWCDailyTempProtocol ;""",
        """""",
        "a target without a protocol is not identified",
    ),
    (
        # sh:minInclusive/sh:maxInclusive on the probability, which nothing else
        # checks: validate.py reads probabilities but never bounds them.
        "a probability outside 0..1",
        EXAMPLE,
        """fm:probabilityValue "0.52"^^xsd:decimal""",
        """fm:probabilityValue "1.52"^^xsd:decimal""",
        "Value is not <=",
    ),
    (
        # ksh:Market asserts owl:cardinality 1 on expressesProposition, but OWL
        # cardinality under the open-world assumption does not reject a second
        # value -- it infers the two are the same individual. SHACL closes it.
        "a market expressing two propositions",
        EXAMPLE,
        """    ksh:expressesProposition ex:Prop-82-83 ;""",
        """    ksh:expressesProposition ex:Prop-82-83 , ex:Prop-82-83-NWS ;""",
        "every market expresses exactly one proposition",
    ),
    (
        # The same rule, on export-shaped data rather than the worked examples.
        # The examples are a superset of any export -- they carry sites, day
        # boundaries and model runs the export omits -- so conformance there did
        # not show the shapes were satisfiable by the thing they describe, only
        # by something richer. This case fails if the shapes stop biting on the
        # shape of data ThermalEdge actually sends.
        "an export target stripped of its measurement protocol",
        EXPORT,
        """    wx:underProtocol <https://thermal-edge.dev/id/protocol/weather_co> ;""",
        """""",
        "a target without a protocol is not identified",
    ),
    (
        # The mistargeted-sh:targetClass trap, made into a test. A shape whose
        # targetClass matches NO focus node conforms -- so when MarketShape
        # targeted ksh:WeatherMarket, an export typing its markets as plain
        # ksh:Market was checked for nothing at all and passed with no
        # proposition and no ticker. Retyping here must still be rejected.
        "an export market typed as a plain market, with no proposition",
        EXPORT,
        """    a ksh:WeatherMarket ;
    ksh:marketTicker "KXHIGHAUS-26AUG22-B88" ;
    ksh:expressesProposition <https://thermal-edge.dev/id/prop/KXHIGHAUS-26AUG22-B88> .""",
        """    a ksh:Market ;
    fm:statedAs "typed as a plain market, with no proposition and no ticker" .""",
        "every market expresses exactly one proposition",
    ),
    (
        # The same mistargeting trap as the case above, on the probability side.
        # ProbabilityShape targeted the two leaf classes, so retyping to their
        # parent matched no focus node and a probability of 7.41 conformed.
        "an export probability retyped to its parent class, with a value of 7.41",
        EXPORT,
        """    a fm:ForecastProbability ;
    fm:assignsProbabilityTo <https://thermal-edge.dev/id/prop/KXHIGHAUS-26AUG22-B88> ;
    fm:probabilityValue "0.41"^^xsd:decimal .""",
        """    a fm:ProbabilityAssignment ;
    fm:assignsProbabilityTo <https://thermal-edge.dev/id/prop/KXHIGHAUS-26AUG22-B88> ;
    fm:probabilityValue "7.41"^^xsd:decimal .""",
        "Value is not <=",
    ),
    (
        # A dangling protocol IRI. sh:class wx:MeasurementProtocol could not catch
        # this -- rdfs range entailment types the object before SHACL looks -- so
        # the check is a literal the entailment cannot fabricate.
        "an export target pointing at a protocol IRI that carries no rules",
        EXPORT,
        """    wx:underProtocol <https://thermal-edge.dev/id/protocol/weather_co> ;""",
        """    wx:underProtocol <https://ex.test/dangling-protocol> ;""",
        "a protocol must state its rules",
    ),
]

# Defects that must break a competency question rather than quietly changing its answer.
COMPETENCY_CASES = [
    (
        # Was "returned 0 rows" when the temperature example was cq02's only
        # joined proposition. The rain example adds a second, independent join,
        # so severing the temperature one leaves one row rather than zero, and
        # the failure mode is a differing result. Empty-result coverage lives in
        # the correction case below and in the cq-update case at the bottom of
        # this file -- NOT in the settlement case, which also expects a differing
        # result now.
        "forecast and market probabilities no longer share a proposition",
        EXAMPLE,
        """ex:ForecastProb-82-83 a fm:ForecastProbability ;
    rdfs:label "GEFS 06Z P(82-83F)" ;
    fm:assignsProbabilityTo ex:Prop-82-83 ;""",
        """ex:Prop-decoy a fm:Proposition ;
    rdfs:label "decoy proposition" ;
    fm:hasSubject ex:Target-HighTemp .

ex:ForecastProb-82-83 a fm:ForecastProbability ;
    rdfs:label "GEFS 06Z P(82-83F)" ;
    fm:assignsProbabilityTo ex:Prop-decoy ;""",
        "differs from",
    ),
    (
        "a probability value silently changed",
        EXAMPLE,
        """    fm:probabilityValue "0.52"^^xsd:decimal ;""",
        """    fm:probabilityValue "0.41"^^xsd:decimal ;""",
        "differs from",
    ),
    (
        "a bracket drops out of the ladder",
        BRACKETS,
        """    ksh:marketTicker "KXHIGHNY-26AUG15-T86" ;
    ksh:inEventGrouping ex:KXHIGHNY-26AUG15 ;""",
        """    ksh:marketTicker "KXHIGHNY-26AUG15-T86" ;""",
        "differs from",
    ),
    (
        "ladder priced so the whole set costs under a dollar",
        EXAMPLE,
        """    ksh:yesAskCents 62 ;""",
        """    ksh:yesAskCents 30 ;""",
        "differs from",
    ),
    (
        # Restores empty-result coverage: with no supersedes link there is no
        # correction to check against, so CQ7 has nothing to report.
        "correction no longer supersedes the report it replaces",
        CORRECTION,
        """    wx:supersedes ex:TWCRecord-2026-08-16 ;""",
        """""",
        "returned 0 rows",
    ),
    (
        "corrected value changed, so the contradiction verdicts flip",
        CORRECTION,
        """    fm:realizedValue "84"^^xsd:decimal ;""",
        """    fm:realizedValue "81"^^xsd:decimal ;""",
        "differs from",
    ),
    (
        "an outcome flipped in the verification sample",
        VERIFICATION,
        """vex:A-20260701-LE81 a fm:TruthAssessment ;
    fm:assessesProposition vex:P-20260701-LE81 ;
    fm:assessedTruthValue fm:False ;""",
        """vex:A-20260701-LE81 a fm:TruthAssessment ;
    fm:assessesProposition vex:P-20260701-LE81 ;
    fm:assessedTruthValue fm:True ;""",
        "differs from",
    ),
    (
        # Discriminating on purpose: an assessment that was fm:False scores 0
        # either way, so only a query that DROPS fm:Indeterminate changes its
        # answer. Counting it as an observed "no" leaves every statistic intact
        # and the defect invisible.
        "an assessment becomes indeterminate rather than false",
        VERIFICATION,
        """vex:A-20260701-LE81 a fm:TruthAssessment ;
    fm:assessesProposition vex:P-20260701-LE81 ;
    fm:assessedTruthValue fm:False ;""",
        """vex:A-20260701-LE81 a fm:TruthAssessment ;
    fm:assessesProposition vex:P-20260701-LE81 ;
    fm:assessedTruthValue fm:Indeterminate ;""",
        "differs from",
    ),
    (
        # Was "returned 0 rows" when the example held a single settlement. With the
        # full ladder there are four, so dropping one leaves three and the failure
        # mode is a differing result rather than an empty one. Empty-result coverage
        # is the correction case above and the cq-update case at the bottom of this
        # file; the broken-join case no longer provides it.
        "settlement no longer records the document it read",
        EXAMPLE,
        """    fm:hasInput ex:TWCRecord-2026-08-16 ;""",
        """""",
        "differs from",
    ),
]


SHAPE_PIN = "shapes/thermaledge-export.pin.json"

# The hole the pin exists to close. Before it, widening this range passed
# all eleven non-Java targets: the classifier was written and pointed at nothing.
# The bound is chosen to stay inside what the negative fixtures probe -- they inject
# 1.52 and 7.41, so a grosser widening like -99..99 fails two of them and proves
# nothing about the pin. Note the expected rule -- a loosened numeric range is
# CHANGED, not WEAKENED, so an audit failing only on weakenings would still miss it.
PIN_CASES = [
    (
        "a weakened export contract against an unchanged pin",
        "shapes/thermaledge-export.ttl",
        """sh:minInclusive 0 ; sh:maxInclusive 1 ;""",
        """sh:minInclusive -1 ; sh:maxInclusive 1.5 ;""",
        "value-changed",
    ),
]


def copy_tree(tmp: str) -> Path:
    work = Path(tmp) / "fmo"
    shutil.copytree(
        ROOT, work,
        ignore=shutil.ignore_patterns(".git", "build", "__pycache__", "*.pyc"),
    )
    return work


def _checker_name(script: str) -> str:
    """The checker's filename, from a string that may carry its arguments.

    `Path(script).name` takes the last token, so a script string like
    `shape_signatures.py --audit shapes/thermaledge-export.pin.json` names the pin
    rather than the checker that read it.
    """
    return Path(script.split()[0]).name


def expect_failure(work: Path, script: str, name: str, expect: str) -> bool:
    proc = subprocess.run(
        [sys.executable, *script.split()],
        cwd=work, capture_output=True, text=True,
    )
    output = proc.stdout + proc.stderr

    if proc.returncode == 0:
        print(f"  FAIL [{name}]: {_checker_name(script)} passed but should have failed")
        return False
    if expect not in output:
        print(f"  FAIL [{name}]: exited non-zero but message missing")
        print(f"         expected substring: {expect!r}")
        return False
    print(f"  ok   [{name}]")
    return True


def run_case(name: str, rel: str, find: str, replace: str, expect: str,
             script: str = "scripts/validate.py") -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        work = copy_tree(tmp)
        target = work / rel
        text = target.read_text()
        if text.count(find) != 1:
            print(f"  SETUP FAIL [{name}]: anchor found {text.count(find)} times in {rel}")
            return False
        target.write_text(text.replace(find, replace))
        return expect_failure(work, script, name, expect)


def run_sweep_case(name: str, src: str, dest_dir: str, expect: str, script: str) -> bool:
    """Misfile a fixture into the other sweep's directory; the sweep must object.

    The sweeps ARE the checking apparatus -- they decide which fixtures run at all --
    and nothing else here exercises them. Every other case mutates a fixture, so an
    inverted condition in a sweep would pass the whole suite.
    """
    with tempfile.TemporaryDirectory() as tmp:
        work = copy_tree(tmp)
        shutil.copy(work / src, work / dest_dir / Path(src).name)
        return expect_failure(work, script, name, expect)


def main() -> int:
    # Baseline: the unmodified tree must pass both checkers, or the negative
    # results below mean nothing.
    baseline_ok = True
    # validate_shapes.py is a third checker with its own negative cases below. Without
    # it in the baseline, a shapes edit that makes the CLEAN tree violate TargetShape
    # would let those cases "pass": non-zero exit, right message, wrong reason.
    # The audit is a fourth, and the same argument is sharper for it: a stale pin --
    # editing the shapes file and forgetting `make shape-signatures-update` -- already
    # fails the clean tree, and plausibly emits the very value-changed the pin case
    # greps for, so that case would report ok for the wrong reason.
    # test_meta.py is a fifth: two cases below run it, and a meta failure on the
    # clean tree would let both report ok on a non-zero exit they did not cause.
    for script in ("scripts/validate.py", "scripts/run_competency.py",
                   "scripts/validate_shapes.py --examples",
                   f"scripts/shape_signatures.py --audit {SHAPE_PIN}",
                   "scripts/test_meta.py"):
        proc = subprocess.run(
            [sys.executable, *script.split()], cwd=ROOT, capture_output=True, text=True,
        )
        if proc.returncode != 0:
            print(f"BASELINE FAIL: {script} does not pass on the unmodified tree")
            print(proc.stdout + proc.stderr)
            baseline_ok = False
        else:
            print(f"  ok   [baseline: {_checker_name(script)} passes on clean tree]")
    if not baseline_ok:
        return 1

    print("\n  -- validator --")
    results = [run_case(*case) for case in CASES]
    # Export cases go through --exports rather than naming the file, so the sweep
    # `make shapes` actually runs is the thing under test, not just main().
    print("\n  -- shapes --")
    results += [
        run_case(*case, script=(
            "scripts/validate_shapes.py --exports" if case[1] == EXPORT
            else "scripts/validate_shapes.py --examples"))
        for case in SHAPES_CASES
    ]

    print("\n  -- competency questions --")
    results += [
        run_case(*case, script="scripts/run_competency.py")
        for case in COMPETENCY_CASES
    ]

    print("\n  -- export contract pin --")
    results += [
        run_case(*case, script=f"scripts/shape_signatures.py --audit {SHAPE_PIN}")
        for case in PIN_CASES
    ]

    print("\n  -- production sweeps --")
    results.append(run_sweep_case(
        "a negative fixture that nothing rejects",
        EXPORT, "examples/negative",
        "but no query reported a failure",
        "scripts/run_competency.py --negatives",
    ))
    results.append(run_sweep_case(
        "an export fixture that fails a production floor",
        MISMATCH, "examples/export",
        "FAIL [cq02-probability-gap.rq]",
        "scripts/run_competency.py --exports",
    ))
    # Both other ledgers fail on an entry naming something gone; this one did not,
    # so a stale exemption sat there reading as a decision about today's query set.
    results.append(run_case(
        "a production expectation naming a query that does not exist",
        "queries/production-expectations.json",
        """  "cq02-probability-gap": {""",
        """  "cq99-retired": {
    "may_be_empty": true,
    "why": "a stale entry, left behind after its query was deleted"
  },
  "cq02-probability-gap": {""",
        "names a query that does not exist",
        script="scripts/run_competency.py --exports",
    ))

    # test_meta.py asserted `if V.failures:` -- "the check failed somehow", which any
    # unrelated guard inside it satisfies. Two checks passed that sweep on their own
    # retained guards, so their coverage() calls could have been deleted outright and
    # `make meta` stayed green. This mutation is that exact shape: a check with no
    # coverage() call and a failure from somewhere else.
    print("\n  -- meta --")
    results.append(run_case(
        "a check that fails for reasons unrelated to its coverage",
        "scripts/validate.py",
        """    coverage("trades", checked, "trade(s) checked for opposite sides and equal quantity",
             "the trading layer is unexercised again")""",
        """    fail("an unrelated guard, standing in for the coverage() call")""",
        "check_trades records no coverage()",
        script="scripts/test_meta.py",
    ))
    # Dispatch used to be hand-written tuples in main() while test_meta swept
    # dir(V), and nothing reconciled them: a well-formed check main() never called
    # passed `make meta` AND `make validate`. Deleting a registration is that bug
    # exactly -- the function still parses, still sweeps, and never runs.
    results.append(run_case(
        "a check that is defined but never registered for dispatch",
        "scripts/validate.py",
        """@check(takes=("data",))
def check_payouts(g: Graph) -> None:""",
        """def check_payouts(g: Graph) -> None:""",
        "check_payouts is not registered with @check",
        script="scripts/test_meta.py",
    ))
    # Deriving dispatch from the registry made an empty registry a clean exit 0 --
    # retyping it could not, because the tuples were literals. `make meta` catches
    # this, but that is a guard in another target, and validate.py reporting OK
    # having run nothing is the vacuity every coverage() call refuses.
    results.append(run_case(
        "a validate run with no checks registered at all",
        "scripts/validate.py",
        """        CHECKS.append(Check(fn, tuple(takes), population, reason))""",
        """        pass  # registration removed""",
        "no checks registered, so this run proved nothing",
    ))
    # test_shapes.py printed its assertion count without asserting it, so an
    # sh:minCount dropped from the export contract shrank the matrix from 14 to 13
    # and the suite still said OK -- the shape it exists to prove stopped being
    # proved, silently.
    results.append(run_case(
        "an sh:minCount dropped from the export contract",
        "shapes/thermaledge-export.ttl",
        """        sh:path ksh:marketTicker ;
        sh:minCount 1 ; sh:maxCount 1 ;""",
        """        sh:path ksh:marketTicker ;
        sh:maxCount 1 ;""",
        "the matrix changed size",
        script="scripts/test_shapes.py",
    ))

    # --update used to return 0 unconditionally. A query that errors or returns
    # nothing skips its write, so the stale .expected survives and `make cq-update`
    # reported success with no diff for exactly the query that was broken.
    # Deliberately not COMPETENCY_CASES[0]. That mutation breaks the temperature
    # example's forecast/market join, which emptied cq02 back when the temperature
    # example was the only one joining a forecast to a market. The rain example is
    # a second, so breaking one leaves the other and the result is short, not
    # empty. cq08 is single-sourced by the trading example, which no other example
    # feeds, so removing the execution price still empties it -- and emptiness is
    # the whole point of this case.
    print("\n  -- cq-update --")
    results.append(run_case(
        "cq-update reporting success on a query that returned nothing",
        TRADING,
        "    ksh:executionPriceCents 60 ;\n",
        "",
        "returned 0 rows",
        script="scripts/run_competency.py --update",
    ))

    passed, total = sum(results) + 3, len(results) + 3
    print(f"\n{passed}/{total} checks passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
