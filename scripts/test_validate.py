#!/usr/bin/env python3
"""Negative tests for scripts/validate.py and scripts/run_competency.py.

A check that has only ever been seen to pass is not known to work. Each case here
introduces one specific defect into a copy of the tree, runs the checker, and asserts it
fails with the expected message. The source tree is never modified.

Run: python3 scripts/test_validate.py
"""

from __future__ import annotations

import contextlib
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from typing import NamedTuple

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
        # The guard is ledger.load()'s now, not check_class_coverage's, so a fourth
        # ledger inherits it rather than needing someone to remember it.
        "has categories nothing reads: schema-instantiated",
    ),
    (
        # One underscore wide. ledger.load() strips the `_comment` header, and
        # stripping every underscore key instead -- which looks like tidier
        # de-duplication -- hides the block from the guard above entirely, which is
        # exactly the escape hatch that guard exists to close.
        "the ledger parking a category behind an underscore",
        "queries/class-coverage-expectations.json",
        '  "unlisted": {',
        '  "_schema-instantiated": {\n    "ksh:Market": {\n      "reason": "An injected'
        ' entry hidden behind the comment prefix."\n    }\n  },\n\n  "unlisted": {',
        "has categories nothing reads: _schema-instantiated",
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


def ledger_cases() -> list[str]:
    """Direct assertions on scripts/ledger.py, in process.

    check_axioms.py is the one call site no target can run here -- it skips
    without ROBOT, so a subprocess case expecting failure would see exit 0 and
    fail for the wrong reason. Review found a real defect in exactly that blind
    spot: audit() is category-blind, so a blank `pinned` value emitted
    BLANK_REASON and check_axioms rendered it as "exempt with no reason given"
    for an entry that is pinned.
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    import ledger as L  # noqa: PLC0415

    out: list[str] = []

    def want(label: str, kinds: set[str], findings: list) -> None:
        got = {f.kind for f in findings}
        if got != kinds:
            out.append(f"ledger.audit {label}: expected {sorted(kinds)}, got {sorted(got)}")
        else:
            print(f"  ok   [ledger] {label}")

    rows = [L.Entry("a", "one", "why"), L.Entry("b", "two", "why")]
    want("clean", set(), L.audit({"a", "b"}, rows, handles=L.KINDS))
    want("uncovered", {L.UNCOVERED}, L.audit({"a", "b", "c"}, rows, handles=L.KINDS))
    want("stale", {L.STALE_UNKNOWN}, L.audit({"a"}, rows, handles=L.KINDS))
    want("duplicate", {L.DUPLICATE},
         L.audit({"a"}, [L.Entry("a", "one", "w"), L.Entry("a", "two", "w")], handles=L.KINDS))
    want("blank reason", {L.BLANK_REASON}, L.audit({"a"}, [L.Entry("a", "one", "  ")], handles=L.KINDS))
    want("empty population", {L.EMPTY_POPULATION, L.STALE_UNKNOWN}, L.audit(set(), rows, handles=L.KINDS))
    want("universe splits staleness", {L.STALE_LEFT},
         L.audit({"b"}, rows, universe={"a", "b"}, handles=L.KINDS))
    want("universe, gone entirely", {L.STALE_UNKNOWN, L.UNCOVERED},
         L.audit({"z"}, [L.Entry("a", "one", "w")], universe={"z"}, handles=L.KINDS))

    # A blank reason on a row whose name is stale is reported once, as stale --
    # the population is fully covered here so nothing else can account for it.
    want("stale beats blank", {L.STALE_UNKNOWN},
         L.audit({"a"}, [L.Entry("a", "one", "w"), L.Entry("x", "one", "")], handles=L.KINDS))

    # The check_axioms regression: a blank `pinned` value must not be rendered as
    # an exempt-with-no-reason, because a pinned value is a case name.
    blank_pinned = [f for f in L.audit({"a"}, [L.Entry("a", "pinned", "")], handles=L.KINDS)
                    if f.kind == L.BLANK_REASON and f.category == "exempt"]
    if blank_pinned:
        out.append("a blank `pinned` value renders as an exempt-with-no-reason")
    else:
        print("  ok   [ledger] a blank pinned value is not reported as exempt")

    # KINDS is exercised in full, so a kind added without a case fails here.
    seen_kinds = set()
    for pop, rows_, uni in (
        ({"a", "b", "c"}, rows, None),
        ({"a"}, [L.Entry("a", "one", ""), L.Entry("a", "two", "w")], None),
        (set(), rows, None),
        ({"b"}, rows, {"a", "b"}),
    ):
        seen_kinds |= {f.kind for f in L.audit(pop, rows_, universe=uni, handles=L.KINDS)}
    if seen_kinds != set(L.KINDS):
        out.append(f"ledger cases exercise {sorted(seen_kinds)}, not all of {sorted(L.KINDS)}")
    else:
        print("  ok   [ledger] every finding kind is exercised")

    # load() strips the comment header and nothing else.
    import json as _json  # noqa: PLC0415
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "l.json"
        path.write_text(_json.dumps({"_comment": "x", "_hidden": {}, "real": {}}))
        keys = set(L.load(path))
        if keys != {"_hidden", "real"}:
            out.append(f"ledger.load stripped the wrong keys: {sorted(keys)}")
        else:
            print("  ok   [ledger] load strips _comment and keeps other underscore keys")
        missing = Path(tmp) / "nope.json"
        try:
            L.load(missing)
            out.append("ledger.load accepted a missing file")
        except L.LedgerError:
            print("  ok   [ledger] a missing ledger raises LedgerError, not SystemExit")
        except SystemExit:
            out.append("ledger.load raised SystemExit, which validate.py cannot catch")

        # A category the caller never reads, refused by load() rather than by one
        # call site remembering to. This is the hole that let an entry parked under
        # `deferred` in axiom-expectations.json pass check_axioms with OK.
        parked = Path(tmp) / "parked.json"
        parked.write_text(_json.dumps({"pinned": {}, "deferred": {"x": "parked"}}))
        try:
            L.load(parked, ("pinned", "exempt"))
            out.append("ledger.load accepted a category the caller does not read")
        except L.LedgerError as exc:
            if "categories nothing reads" not in str(exc):
                out.append(f"the unread-category refusal is the wrong error: {exc}")
            else:
                print("  ok   [ledger] load refuses a category the caller does not read")

    # A kind the caller says nothing about must raise, not be dropped: an absent
    # `elif` computes the finding and discards it, which is the defect this kernel
    # was extracted to stop wearing the kernel's own clothes.
    try:
        L.audit({"a"}, [L.Entry("b", "one", "w")], handles=(L.UNCOVERED,))
        out.append("audit() dropped a finding kind the caller does not handle")
    except L.LedgerError as exc:
        if "says nothing about that kind" not in str(exc):
            out.append(f"the undecided-kind refusal is the wrong error: {exc}")
        else:
            print("  ok   [ledger] a kind the caller does not handle raises, not drops")

    out += axiom_cases()
    return out


def axiom_cases() -> list[str]:
    """check_axioms.verify()'s own rendering, in process.

    This is the one call site no target on a JDK-less machine can run: without
    ROBOT it SKIPS, so a subprocess case expecting failure sees exit 0 and passes
    for the wrong reason. That is precisely where the BLANK_REASON defect lived --
    audit() is category-blind, and check_axioms rendered a blank `pinned` value as
    "exempt with no reason given" for an entry that is pinned.

    ledger_cases() above proves audit() carries the category through. These prove
    check_axioms RENDERS it, which is a different claim: the scoping fix is one
    `and f.category == "exempt"` clause, and dropping it would leave every target
    green. Two module globals are stubbed -- fires_without is the only Java-touching
    call, and load_ledger's replacement is what puts a mutated ledger in front of it.
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    import check_axioms as C  # noqa: PLC0415
    import ledger as L  # noqa: PLC0415
    import axioms  # noqa: PLC0415
    import test_reason as T  # noqa: PLC0415
    import reasoner as R  # noqa: PLC0415

    out: list[str] = []
    sites = sorted(axioms.all_sites())
    if not sites:
        return ["axiom_cases found no axiom sites, so it verified nothing"]
    real = L.load(C.LEDGER, C.CATEGORIES)
    pinned, exempt = real.get("pinned", {}), real.get("exempt", {})

    def verdict(label: str, ledger: dict, expect: str) -> None:
        buf = io.StringIO()
        saved_load, saved_fires = L.load, C.fires_without
        try:
            # setattr, not `L.load = ...`: a type checker declares a module
            # function as its own type and refuses any rebinding of it, so the
            # doubles below cannot be spelled as plain assignments. The restore
            # in `finally` is an assignment because it puts the real one back.
            setattr(L, "load", lambda *a, **k: ledger)
            setattr(C, "fires_without", lambda *a, **k: False)  # every pin holds; no Java
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                rc = C.verify([])
        finally:
            L.load, C.fires_without = saved_load, saved_fires
        output = buf.getvalue()
        if rc == 0:
            out.append(f"check_axioms [{label}]: exited 0; the ledger defect passed")
        elif expect not in output:
            out.append(f"check_axioms [{label}]: wrong message, wanted {expect!r}")
        else:
            print(f"  ok   [check_axioms] {label}")

    gone = "core.ttl: an axiom that was deleted three releases ago"
    verdict("a ledger naming an axiom that no longer exists",
            {"pinned": pinned, "exempt": {**exempt, gone: "stale"}},
            "ledger names an axiom that no longer exists")
    verdict("an axiom in neither block",
            {"pinned": pinned, "exempt": {k: v for k, v in exempt.items()
                                          if k != sorted(exempt)[0]}},
            "axiom in neither pinned nor exempt")
    verdict("an axiom in both blocks",
            {"pinned": {**pinned, sorted(exempt)[0]: sorted(pinned.values())[0]},
             "exempt": exempt},
            "in both pinned and exempt")
    verdict("an exempt entry with no reason",
            {"pinned": pinned, "exempt": {**exempt, sorted(exempt)[0]: "   "}},
            "exempt with no reason given")
    # The regression itself: a blank `pinned` value is a case name that does not
    # exist, and must not be rendered as an exempt-with-no-reason.
    blank_pin = sorted(exempt)[0]
    verdict("a pinned entry whose case name is blank",
            {"pinned": {**pinned, blank_pin: "   "},
             "exempt": {k: v for k, v in exempt.items() if k != blank_pin}},
            "pinned by a case that does not exist")
    buf = io.StringIO()
    saved_load, saved_fires = L.load, C.fires_without
    try:
        setattr(L, "load", lambda *a, **k: {"pinned": {**pinned, blank_pin: "   "},
                                            "exempt": {k: v for k, v in exempt.items()
                                                       if k != blank_pin}})
        setattr(C, "fires_without", lambda *a, **k: False)
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            C.verify([])
    finally:
        L.load, C.fires_without = saved_load, saved_fires
    if "exempt with no reason given" in buf.getvalue():
        out.append("a blank `pinned` value is still rendered as exempt-with-no-reason")
    else:
        print("  ok   [check_axioms] a blank pinned value is not called exempt")

    out += reasoner_silence_cases(C, T, R)
    return out


def reasoner_silence_cases(C, T, R) -> list[str]:
    """A reasoner that cannot answer must not be read as answering "no".

    These are the two halves of one defect. Detection said a JVM was there because
    /usr/bin/java exists on every Mac and exits 1; scoring then read every failed run
    as "the case stopped firing", which is what a pinned axiom looks like. Together
    they made `make axioms` print `9 pinned (9 verified)` and OK with HermiT never
    started, output a reader cannot tell from a real run.

    They belong here rather than in test_reason.py because that file skips without a
    working ROBOT -- a case about being unable to reason cannot live behind a guard
    that needs to reason. Nothing below starts a JVM or touches the real robot.jar.
    """
    out: list[str] = []
    out += _detection_cases(R)
    out += _outcome_cases(T)
    out += _scoring_cases(C, T)
    out += _derivation_cases()
    out += _recipe_cases()
    out += _inferred_type_cases()
    return out


def _detection_cases(R: ModuleType) -> list[str]:
    """robot_command answers about a reasoner that runs, not one that exists."""
    out: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        fake = Path(tmp)
        (fake / "src").mkdir()
        # A ROOT of our own holding a robot.jar of our own. The real one is
        # gitignored, so a fresh clone that has not run `make setup` would otherwise
        # send every probe below down the robot-on-PATH branch and these cases would
        # answer about the machine rather than about the code.
        (fake / "robot.jar").write_text("not a jar; the fake java never opens it")
        java = fake / "java"
        java.write_text("#!/bin/sh\necho 'Unable to locate a Java Runtime.' >&2\nexit 1\n")
        java.chmod(0o755)
        saved_path, saved_root = os.environ.get("PATH", ""), R.ROOT
        saved_jar = os.environ.pop("ROBOT_JAR", None)
        try:
            os.environ["PATH"] = f"{fake}{os.pathsep}{saved_path}"
            setattr(R, "ROOT", fake)
            broken, why = R.robot_command()
            # A named reasoner that does not run is a typo, not an absence, and used
            # to fail loudly on first use. Probing must not turn that into a skip.
            os.environ["ROBOT_JAR"] = str(fake / "robot.jar")
            try:
                R.robot_command()
                named = "returned instead of raising"
            except R.ReasonerBroken as exc:
                named = str(exc)
            del os.environ["ROBOT_JAR"]
            # The positive control. Without it a robot_command that returned None
            # unconditionally -- say, a typo in the probe -- would pass every case
            # above and every reasoner target would skip forever.
            java.write_text("#!/bin/sh\nexit 0\n")
            working, _ = R.robot_command()
        finally:
            os.environ["PATH"] = saved_path
            if saved_jar is not None:
                os.environ["ROBOT_JAR"] = saved_jar
            else:
                os.environ.pop("ROBOT_JAR", None)
            setattr(R, "ROOT", saved_root)

    for ok, problem, label in (
        (broken is None,
         "robot_command accepted a java that exits non-zero, so presence is still "
         "being read as usability",
         "a java that does not run is not a reasoner"),
        ("Unable to locate a Java Runtime" in why,
         f"the skip reason drops what the runtime said, leaving {why!r}",
         "the skip says what the runtime said, not just that it said something"),
        ("returned instead of raising" not in named,
         "a ROBOT_JAR that does not run skipped rather than failed, which turns a "
         "typo into a green run",
         "a named reasoner that does not run fails rather than skipping"),
        (working is not None,
         "robot_command rejected a java that exits 0, so every case above passes "
         "for the wrong reason",
         "a java that runs is accepted"),
    ):
        if ok:
            print(f"  ok   [test_reason] {label}")
        else:
            out.append(problem)
    return out


def _outcome_cases(T: ModuleType) -> list[str]:
    """run_case names all three situations, which is the half a stub cannot prove.

    The scoring cases below replace run_case wholesale, so on their own they leave
    the branch that *produces* UNREADABLE untested -- collapse it to ACCEPTED and the
    original false green comes back with the whole suite still green. That is the bug
    being fixed wearing the fix's own clothes, so it gets a case.

    Driven by a fake ROBOT over a ROOT holding one real module: the anchors have to be
    the genuine ones, but nothing here needs the ontology or a JVM.
    """
    out: list[str] = []
    name, rel, find, replace = T.CASES[0][:4]
    with tempfile.TemporaryDirectory() as tmp:
        fake = Path(tmp)
        (fake / Path(rel).parent).mkdir(parents=True)
        shutil.copy(ROOT / rel, fake / rel)
        saved_root = T.ROOT
        try:
            setattr(T, "ROOT", fake)
            for behaviour, expected, label in (
                ("exit 1",
                 T.UNREADABLE, "a reasoner failing without the expected report is unreadable"),
                ("exit 0",
                 T.ACCEPTED, "a reasoner accepting the ontology is not a case firing"),
                ("echo inconsistent; exit 1",
                 T.FIRED, "a reasoner reporting what the case expects is a case firing"),
            ):
                robot = fake / "robot.sh"
                robot.write_text(f"#!/bin/sh\n{behaviour}\n")
                robot.chmod(0o755)
                got = T.run_case(["/bin/sh", str(robot)], name, rel, find, replace,
                                 quiet=True)
                if got != expected:
                    out.append(f"run_case called it {got!r}, not {expected!r}: {label}")
                else:
                    print(f"  ok   [test_reason] {label}")
        finally:
            setattr(T, "ROOT", saved_root)
    return out


def _inferred_type_cases() -> list[str]:
    """CQ3's verdict skips without a reasoner, and refuses to pass without a file.

    The second is the guard worth having. Lifting the check out of the Makefile gave
    it a way to be run when the reasoner had skipped, and "the file is not there" must
    read as a broken recipe rather than as a machine without Java -- otherwise the
    target that proves a class is a working defined class passes by not looking.
    """
    out: list[str] = []
    check = str(ROOT / "scripts" / "check_inferred_type.py")
    with tempfile.TemporaryDirectory() as tmp:
        fake = Path(tmp)
        good = fake / "reasoned.ttl"
        good.write_text("<http://example.org/M> a <http://example.org/WeatherMarket> .\n")

        def run(reasoner_exit: int, path: Path) -> tuple[int, str]:
            for name in ("java", "robot"):
                (fake / name).write_text(f"#!/bin/sh\nexit {reasoner_exit}\n")
                (fake / name).chmod(0o755)
            env = dict(os.environ,
                       PATH=f"{fake}{os.pathsep}{os.environ.get('PATH', '')}")
            env.pop("ROBOT_JAR", None)
            proc = subprocess.run(
                [sys.executable, check, str(path), "http://example.org/M", "WeatherMarket"],
                cwd=fake, capture_output=True, text=True, env=env)
            return proc.returncode, proc.stdout + proc.stderr

        missing = run(reasoner_exit=0, path=fake / "never-written.ttl")
        skipped = run(reasoner_exit=1, path=fake / "never-written.ttl")
        passing = run(reasoner_exit=0, path=good)

    for (code, output), want_code, want_text, label in (
        (missing, 1, "was not written", "a reasoned file that was never written fails"),
        (skipped, 0, "SKIP", "no reasoner is a skip, not a verdict"),
        (passing, 0, "PASS", "an inferred type still passes"),
    ):
        if code != want_code:
            out.append(f"check_inferred_type exited {code}, wanted {want_code}: {label}"
                       f" -- {output.strip()[:100]}")
        elif want_text not in output:
            out.append(f"check_inferred_type said {output.strip()[:80]!r}, wanted "
                       f"{want_text!r}: {label}")
        else:
            print(f"  ok   [competency] {label}")
    return out


# Excluded from the sweep by name, with the reason, because the sweep runs targets for
# real. Nothing verifies a reason, so a new entry is the thing to argue about in review.
UNSWEEPABLE_TARGETS = {
    "setup": "runs poetry install and downloads a 79MB jar",
}


# Handed to make so target names come back with a marker the sweep can replace with a
# scratch directory. The database expands names, so `$(BUILD)/merged.owl` arrives
# already resolved and there is nothing left to substitute otherwise.
MAKE_BUILD = "@@FMO_BUILD@@"


class Derived(NamedTuple):
    """What make's own database says, with each classification path counted apart."""
    found: list[str]
    direct: int
    viascript: int
    raw: int
    recipes: dict[str, str]
    phony: set[str]
    patterns: list[str]
    errored: bool
    unread: list[str]


def _make_database(directory: Path) -> tuple[str, int]:
    """make's parse of its own makefile, which beats any parse written here.

    `-p` prints the database, `-q` stops it running a single recipe, `-Rr` drop the
    builtin rules and variables that would otherwise bury the file's own.

    Question mode returns 0 for up to date and 1 for out of date, which is the normal
    case here and says nothing; it reserves 2 for an error, which says everything. An
    earlier version keyed on a missing "# Files" section instead and that guard could
    not fire: make prints the section header for a makefile with a syntax error, and
    for no makefile at all. The status is the only signal that distinguishes them.

    MAKEFLAGS is dropped for the same reason the sweep drops it -- an outer `make -j`
    propagates a jobserver a child cannot join. Here the warning only reaches stderr,
    which nothing reads, so this is symmetry rather than a fix.
    """
    env = {k: v for k, v in os.environ.items() if k not in ("MAKEFLAGS", "MFLAGS")}
    proc = subprocess.run(["make", "-pqRr", f"BUILD={MAKE_BUILD}"], env=env,
                          cwd=directory, capture_output=True, text=True)
    return proc.stdout, proc.returncode


class Entry(NamedTuple):
    name: str
    recipe: str
    phony: bool
    # The block announced a recipe. Kept apart from `recipe` being non-empty, because
    # the two coming apart is how a recipe goes missing without anything noticing:
    # make 4.x .RECIPEPREFIX prints recipe lines under a character other than tab, and
    # this reader would hand back a target whose recipe silently vanished.
    announced: bool


def _entries(section: str) -> list[Entry]:
    """One Entry per target the database describes.

    Blocks are blank-line separated, and that is safe rather than lucky: make drops
    blank lines from a recipe at parse time and prints an empty command as a lone tab,
    so no "\n\n" can appear inside one.

    "# Not a target:" marks a file make knows about but has no rule for. The recipe
    follows a marker whose wording changed between make 3.81 ("commands to execute")
    and 4.x ("recipe to execute") -- matched on the part they share, which also
    excludes the "(built-in)" variant.

    A name can appear twice: make prints each half of a double-colon rule as its own
    block. Both halves belong to the target, so the caller joins them -- overwriting
    dropped whichever came first, and a `::` target left the sweep with no finding.
    """
    out: list[Entry] = []
    for block in section.split("\n\n"):
        lines = block.splitlines()
        if not lines or any(line.startswith("# Not a target:") for line in lines):
            continue
        head = next((line for line in lines if line and not line.startswith(("#", "\t"))), None)
        m = re.match(r"^([^\s:#][^:]*)\s*:(?!=)", head or "")
        if not m:
            continue
        recipe, collecting = [], False
        for line in lines:
            if "to execute (from" in line:
                collecting = True
            elif collecting and line.startswith("\t"):
                recipe.append(line)
            elif collecting and not line.startswith("\t"):
                collecting = False
        phony = any("Phony target" in line for line in lines)
        announced = any("to execute (from" in line for line in lines)
        out.append(Entry(m.group(1).strip(), "\n".join(recipe), phony, announced))
    return out


def _reasoner_targets(directory: Path | None = None,
                      users: set[str] | None = None) -> Derived:
    """Make targets that need a reasoner, taken from make's database rather than a list.

    A hand-kept list is the same failure this sweep exists to catch, one level up: a new
    reasoner target left off it is never swept, and its missing skip is discovered on
    someone's JDK-less laptop. Same argument as validate.CHECKS -- enumerate the real
    set and fail on what it does not account for.

    What make prints is its parse, not its expansion: a recipe reads `$(BODY)` if that
    is how it was written, so a body hidden behind a `define` is invisible to all three
    classifications below. That was equally true of reading the file and is not fixed
    here; the classifications are string matches on recipe text either way.

    Enumerated by asking make, not by reading the Makefile. A regex over the text got
    two shapes wrong and had to refuse them by name: a target line continued with a
    backslash parsed and then discarded every recipe line under it, and a multi-target
    rule kept only the first name. make joins the continuation and expands `a b:` into
    two entries before the database is printed, so both are simply correct here, and
    the four construct refusals that stood in for handling them are gone.

    A target qualifies three ways, and each covers what the others miss. Its recipe may
    call $(call robot_cmd,...), which is how a recipe asks. Or it may run a script that
    imports reasoner, which is how reason-negative and axioms ask -- their recipes never
    mention ROBOT at all, and a sweep grepping only for robot_cmd would miss exactly the
    targets that were already correct. Or it may simply name java or robot, which
    contributes nothing today and is the case that matters most: a target added later
    that calls `java -jar robot.jar` without asking is precisely the bug this branch
    removed, and it would otherwise be invisible for the same reason it was invisible in
    the Makefile -- nobody greps for what is absent.

    Recipes only, deliberately. `merge`, `test` and `all` are reasoner-dependent through
    their prerequisites and have no recipe of their own; they are aggregates that
    delegate, their members are swept individually, and the property holds through them.
    The database lists prerequisites too, so following them is available and declined:
    it would have the sweep run `make test` from inside `make test`.
    """
    if shutil.which("make") is None:
        return Derived([], 0, 0, 0, {}, set(), [], True, [])
    text, status = _make_database(directory or ROOT)
    if users is None:
        # reasoner itself counts: a recipe invoking it directly -- `make setup`, asking
        # whether to print its install note -- depends on it as surely as one running a
        # script that imports it. Leaving it out made setup invisible here, which made
        # its entry in UNSWEEPABLE_TARGETS dead configuration.
        users = {"reasoner"} | {
            p.stem for p in (ROOT / "scripts").glob("*.py")
            if re.search(r"^(?:import reasoner|from reasoner import)", p.read_text(), re.M)
        }

    # Pattern rules print above "# Files", in the implicit-rules section, and are
    # reported rather than swept: `make %.out` is not a thing you can run. Scoped to
    # that section rather than to everything above it, because everything above it
    # includes the whole variable dump -- the process environment among it, printed
    # uncommented. If a header ever moves, the pattern case in _derivation_cases fails
    # rather than this quietly finding nothing.
    _, _, below = text.partition("# Implicit Rules")
    implicit, _, files = below.partition("\n# Files")
    patterns = [e.name for e in _entries(implicit)
                if "%" in e.name
                and re.search(r"\brobot\b|\bjava\b|robot_cmd", e.recipe)]

    recipes: dict[str, str] = {}
    phony: set[str] = set()
    unread: list[str] = []
    for e in _entries(files):
        # Joined, not assigned: make prints each half of a double-colon rule as its own
        # block under the same name, and both halves are that target's.
        recipes[e.name] = (recipes.get(e.name, "") + "\n" + e.recipe).strip()
        if e.phony:
            phony.add(e.name)
        if e.announced and not e.recipe:
            unread.append(e.name)

    direct = [t for t, body in recipes.items() if "robot_cmd" in body]
    viascript = [t for t, body in recipes.items()
                 if any(f"{u}.py" in body for u in users) and "robot_cmd" not in body]
    # No "and not in the others": a raw mention is worth sweeping wherever it appears,
    # and set() below deduplicates. A target here that is not also in direct will not
    # skip, and the sweep says so by name rather than by absence. Both alternatives are
    # \b-bounded: robot_cmd is already direct's business, so this needs to match
    # `robot.jar` and a bare `robot` without also matching every word starting "robot".
    raw = [t for t, body in recipes.items() if re.search(r"\brobot\b|\bjava\b", body)]
    return Derived(sorted(set(direct + viascript + raw)), len(direct), len(viascript),
                   len(raw), recipes, phony, patterns, status == 2, sorted(set(unread)))


def _scan_findings(found: Derived, phony_declared: set[str]) -> list[str]:
    """Reasons to distrust a scan, separate from what it found.

    Every one of these is the scan reporting a clean Makefile because it stopped
    reading properly, which is the failure this file exists to make loud.
    """
    out: list[str] = []
    if found.errored:
        # make reserves exit 2 for an error. Everything below would be zero or short for
        # a reason that has nothing to do with what the Makefile asks for.
        return ["make exited 2 reading its own makefile, so nothing here was derived "
                "from anything; run `make -pqRr` by hand to see why"]
    if found.unread:
        # A block that announced a recipe and yielded none. make 4.x .RECIPEPREFIX is
        # the way this happens: recipe lines print under a character this reader does
        # not expect, and the target comes back looking like it does no work.
        out.append(f"the scan read no recipe for {found.unread}, though make said each "
                   f"has one; a recipe printed under something other than a tab reads "
                   f"here as a target that needs no reasoner")

    # Re-entry, named rather than discovered by running it. The sentinel in
    # _recipe_cases bounds the damage at one level, but it reports the child as a
    # target that would not skip, which is not what went wrong. This says what did.
    selfrun = sorted(t for t in found.found
                     if Path(__file__).name in found.recipes.get(t, ""))
    if selfrun:
        out.append(f"the scan derives {selfrun}, whose recipe runs this file: sweeping "
                   f"it makes `make validate-negative` spawn itself. Something put this "
                   f"file's module scope in reach of the reasoner import -- a lint pass "
                   f"lifting the PLC0415 suppression will do it")

    # A path going quiet, which is a classification that stopped classifying rather
    # than a Makefile that stopped needing a reasoner.
    if not found.direct or not found.viascript:
        out.append(f"the target scan found {found.direct} recipe(s) calling robot_cmd "
                   f"and {found.viascript} running a reasoner-importing script; both "
                   f"should be non-zero, so the scan is broken rather than the Makefile")

    # .PHONY off the source, the phony set off the database, so this is a second
    # opinion on this file's reading of make rather than on make's reading of the
    # Makefile. Two limits worth knowing, since neither is obvious: it compares NAMES,
    # so a block whose recipe is lost but whose name survives passes it -- that is what
    # `unread` above and the double-colon join exist for -- and it covers phony targets
    # only, so the two $(BUILD) file targets sit outside it.
    missed = sorted(phony_declared - found.phony)
    if missed:
        out.append(f"the scan did not see {missed} as targets, which .PHONY declares; "
                   f"make described them and this file failed to read the description")

    # A pattern rule needing a reasoner cannot be swept -- there is no concrete target
    # to run -- so it is named instead of being quietly outside the net.
    if found.patterns:
        out.append(f"pattern rule(s) {found.patterns} need a reasoner and cannot be "
                   f"swept, since `make` cannot be asked for a pattern; give the rule a "
                   f"concrete target, or exclude it deliberately")

    # The ledger rule this repo applies to its three JSON ledgers: an entry naming
    # something the population no longer holds reads as a decision about today and is
    # not one. An exclusion that excludes nothing is worse than none.
    stale = sorted(set(UNSWEEPABLE_TARGETS) - set(found.found))
    if stale:
        out.append(f"UNSWEEPABLE_TARGETS names {stale}, which the scan does not find; "
                   f"either the scan broke or the entry is stale")
    return out


def _phony_declared(makefile: Path) -> set[str]:
    """Every name .PHONY lists, read off the source as an independent second opinion.

    finditer, not search: .PHONY may be stated more than once and appended to with
    +=, and taking only the first would quietly shrink the very check that notices
    this file misreading make.
    """
    names: set[str] = set()
    for m in re.finditer(r"^\.PHONY\s*\+?=?:?((?:[^\n\\]*\\\n)*[^\n]*)",
                         makefile.read_text(), re.M):
        names |= set(m.group(1).replace("\\\n", " ").split())
    return names


# Set by the sweep in the environment of every make it spawns. _recipe_cases refuses to
# run when it is already set, because the derived set is what decides who gets swept:
# hoist `import reasoner` in this file to module scope -- exactly what a lint pass does
# to a PLC0415 suppression -- and validate-negative joins that set, whereupon
# `make validate-negative` spawns `make validate-negative` without bound.
SWEEP_SENTINEL = "FMO_REASONER_SWEEP"


def _derivation_cases() -> list[str]:
    """The scan itself, against real makefiles, because its docstring is not a test.

    The sweep can only be as good as the set it derives. Snippets are written to a
    scratch directory and put through the same `make -pqRr` the real scan uses, so what
    is under test is this file's reading of make's database rather than a guess about
    it. The `raw` path especially: it contributes no targets today, so a break in it
    would go unnoticed for exactly as long as it took someone to add the target it
    exists for.

    The last two cases are the shapes the previous regex scan could not parse and had to
    refuse by name. They are now expected to be *found*, which is the whole reason for
    asking make instead of reading the file.
    """
    if shutil.which("make") is None:
        return ["make not found, so the target scan went unverified"]
    out: list[str] = []
    users = {"reasoner", "importer"}

    def scan(text: str) -> Derived:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "Makefile").write_text(text)
            return _reasoner_targets(directory=Path(tmp), users=users)

    for name, text, expected, label in (
        ("robot_cmd", "a:\n\t@$(call robot_cmd,a); $$cmd merge\n", ["a"],
         "a recipe calling robot_cmd is found"),
        ("script", "a:\n\t$(PY) scripts/importer.py\n", ["a"],
         "a recipe running a reasoner-importing script is found"),
        ("raw", "a:\n\tjava -jar robot.jar --version\n", ["a"],
         "a recipe calling java directly is found, which is the path with no users yet"),
        ("unrelated", "a:\n\t$(PY) scripts/validate.py\n", [],
         "a recipe that needs no reasoner is not swept"),
        ("robotics", "a:\n\techo robotics roboticist\n", [],
         "a word merely starting with robot is not a reasoner"),
        ("assignment", "PY := poetry run\nROBOT_JAR ?= x\na:\n\techo hi\n", [],
         "a variable assignment is not a target"),
        ("build", "a: $(BUILD)/x\n$(BUILD)/x:\n\tjava -jar robot.jar\n",
         [f"{MAKE_BUILD}/x"],
         "a target named through $(BUILD) comes back with the sweep's own marker"),
        # The two the regex scan got wrong. Both are now simply right.
        ("continuation",
         "a: dep \\\n  other\n\t@$(call robot_cmd,a); $$cmd merge\ndep other:\n\t@true\n",
         ["a"],
         "a target line continued with a backslash keeps its recipe"),
        ("multi-target", "a b:\n\t@$(call robot_cmd,x); $$cmd merge\n", ["a", "b"],
         "a multi-target rule yields both targets, not just the first"),
        ("double-colon",
         "a::\n\t@$(call robot_cmd,a); $$cmd merge\na::\n\t@echo second\n", ["a"],
         "both halves of a double-colon rule belong to the target, not just the last"),
    ):
        got = scan(text).found
        if got != expected:
            out.append(f"the {name} scan found {got}, wanted {expected}: {label}")
        else:
            print(f"  ok   [scan] {label}")

    # make exiting 2 is the only thing separating a makefile it could not read from
    # one that asks for nothing: it prints the "# Files" header either way, and for
    # no makefile at all, which is why keying on that header could never fire.
    findings = _scan_findings(scan("a:\n\tfoo\nmissing separator here\n"), set())
    if not any("exited 2" in f for f in findings):
        out.append(f"a makefile make cannot read produced {findings or 'no findings'}, "
                   f"so a scan of nothing would report a clean Makefile")
    else:
        print("  ok   [scan] a makefile make exits 2 on is reported, not read as empty")

    # A recipe make announced and this file did not read. make 4.x .RECIPEPREFIX is
    # how that happens for real; the Derived is built by hand because 3.81 has no
    # such variable and the finding has to be pinned on whichever make is here.
    announced = Derived([], 1, 1, 0, {}, set(), [], False, ["ghost"])
    if not any("read no recipe" in f for f in _scan_findings(announced, set())):
        out.append("a target whose recipe make announced and the scan did not read "
                   "went unreported, so it reads as a target that needs no reasoner")
    else:
        print("  ok   [scan] a recipe make announced but the scan could not read is reported")

    # A pattern rule needing a reasoner has no concrete target to run, so it is named
    # rather than left silently outside the net.
    findings = _scan_findings(scan("real:\n\t@echo hi\n%.out: %.in\n\tjava -jar robot.jar\n"), set())
    if not any("pattern rule" in f for f in findings):
        out.append(f"a reasoner-needing pattern rule produced {findings or 'no findings'}, "
                   f"so it would sit outside the sweep unremarked")
    else:
        print("  ok   [scan] a pattern rule needing a reasoner is reported, not ignored")

    # The audit on the exclusion list, which is what makes a total scan failure loud
    # rather than clean.
    findings = _scan_findings(scan("a:\n\t@echo nothing\n"), set())
    if not any("UNSWEEPABLE_TARGETS names" in f for f in findings):
        out.append(f"a scan finding none of the exclusions produced {findings}, so a "
                   f"broken scan can still report a clean Makefile")
    else:
        print("  ok   [scan] an exclusion the scan cannot find is refused")

    # And the .PHONY second opinion, which is what notices this file misreading a block
    # that make described perfectly well.
    findings = _scan_findings(scan("a:\n\t@echo nothing\n"), {"a", "ghost"})
    if not any("ghost" in f for f in findings):
        out.append("a .PHONY name the scan never saw went unreported, so a block this "
                   "file fails to read looks like a Makefile that does not have it")
    else:
        print("  ok   [scan] a .PHONY name the scan did not see is reported")
    return out


def _recipe_cases() -> list[str]:
    """Every reasoner target skips when the reasoner does not run.

    The claim the extraction exists for, and it is a claim about make, so it is checked
    by running make. Sweeping the whole set rather than one target is the lesson of the
    bug itself: the prose said `make axioms` and `make reason` behaved alike and they
    did not, and no amount of rewriting the prose would have found it. Uniform
    behaviour is worth asserting only if something asserts it.

    Fakes go on PATH for both `java` and `robot`, so whichever branch resolution takes
    -- robot.jar in the repo root, or robot on PATH -- the answer comes from the
    fixture and not from the machine. The repo's own robot.jar is gitignored, so a case
    that let the machine answer would pass on this checkout and skip vacuously on a
    fresh clone. $(BUILD) is redirected at a scratch directory, so a sweep never writes
    to the real one and never reads a stale artifact as up to date.

    Targets run in ROOT rather than in a copy, and write nothing: every swept recipe
    stops at its guard. A copy would be safer in principle and much worse in practice,
    because `poetry run` in a tree without a virtualenv builds a new one.
    """
    out: list[str] = []
    if shutil.which("make") is None:
        return ["make not found, so the reasoner recipes went unverified"]
    if os.environ.get(SWEEP_SENTINEL):
        return [f"the reasoner sweep re-entered itself: a swept target runs this file. "
                f"Whatever put it in the derived set has to come out, or {SWEEP_SENTINEL} "
                f"is load-bearing rather than a backstop"]

    found = _reasoner_targets()
    out += _scan_findings(found, _phony_declared(ROOT / "Makefile"))
    if out:
        # A scan that cannot be trusted makes every case below meaningless, so none run.
        return out
    for target, why in sorted(UNSWEEPABLE_TARGETS.items()):
        # Rendered, because deciding not to sweep something is a decision, and one
        # nobody sees is one nobody argues about in review.
        print(f"  --   [make] {target} not swept: {why}")
    targets = [t for t in found.found if t not in UNSWEEPABLE_TARGETS]

    def run(goal: str, java_exit: int, robot_exit: int) -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "bin"
            fake.mkdir()
            build = Path(tmp) / "build"
            for name, code in (("java", java_exit), ("robot", robot_exit)):
                (fake / name).write_text(f"#!/bin/sh\nexit {code}\n")
                (fake / name).chmod(0o755)
            env = dict(os.environ, PATH=f"{fake}{os.pathsep}{os.environ.get('PATH', '')}")
            env.pop("ROBOT_JAR", None)
            env[SWEEP_SENTINEL] = "1"
            # An outer `make -j` propagates a jobserver these runs cannot join, and the
            # warning lands in the output the assertions read.
            for inherited in ("MAKEFLAGS", "MFLAGS"):
                env.pop(inherited, None)
            proc = subprocess.run(
                ["make", goal.replace(MAKE_BUILD, str(build)), f"BUILD={build}"],
                cwd=ROOT, env=env, capture_output=True, text=True)
        return proc.returncode, proc.stdout + proc.stderr

    for target in targets:
        code, output = run(target, java_exit=1, robot_exit=1)
        label = target.replace(MAKE_BUILD, "build")
        if code != 0:
            out.append(f"make {label} exited {code} with a reasoner that does not run, "
                       f"rather than skipping: {output.strip()[-160:]}")
        elif "SKIP" not in output:
            out.append(f"make {label} exited 0 without saying it skipped, so it is "
                       f"green over a step nothing performed")
        elif "exited 1" not in output:
            # Separates "probed and failed" from "found nothing". The second would mean
            # the fakes were never consulted and the case proved nothing.
            out.append(f"make {label} skipped without probing: {output.strip()[:120]}")
        else:
            print(f"  ok   [make] {label} skips when the reasoner does not run")

    # The positive control, on the one target whose recipe is pure ROBOT calls. Its
    # subject is derived like everything else: hardcoding the name let a `reason` that
    # had dropped out of the scan still be run and still report ok.
    if "reason" not in targets:
        out.append("the scan no longer finds `reason`, so the positive control has no "
                   "subject and the skip cases above are unopposed")
        return out
    code, output = run("reason", java_exit=0, robot_exit=0)
    if code != 0:
        out.append(f"make reason exited {code} with a reasoner that runs: "
                   f"{output.strip()[-160:]}")
    elif "SKIP" in output:
        out.append("make reason skipped even though its reasoner runs")
    elif "reason --input" not in output:
        # Exit 0 and no SKIP is also what a recipe that does nothing looks like. The
        # recipe runs its ROBOT calls under `set -x`, so the invocation itself is the
        # witness -- the counterpart of "exited 1" in the skip direction.
        out.append(f"make reason exited 0 without invoking the reasoner it resolved, "
                   f"so the control passed over a target that does no reasoning: "
                   f"{output.strip()[:120]}")
    else:
        print("  ok   [make] reason runs the reasoner when the reasoner runs")
    return out


def _scoring_cases(C: ModuleType, T: ModuleType) -> list[str]:
    """An unreadable run must not reach the ledger arithmetic as a verified pin."""
    out: list[str] = []
    for outcome, expect_zero, label in (
        (T.UNREADABLE, False, "a reasoner giving no verdict fails rather than verifying"),
        (T.ACCEPTED, True, "a case that stops firing still verifies its pin"),
    ):
        buf = io.StringIO()
        saved = T.run_case
        try:
            setattr(T, "run_case", lambda *a, **k: outcome)
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                rc = C.verify(["java", "-jar", "unused"])
        finally:
            setattr(T, "run_case", saved)
        output = buf.getvalue()
        if expect_zero and rc != 0:
            out.append(f"{label}: exited {rc}, so the UNREADABLE case above proves nothing")
        elif not expect_zero and rc == 0:
            out.append("check_axioms scored pins as verified while the reasoner "
                       "returned no verdict -- the original false green")
        elif not expect_zero and "no verdict" not in output:
            out.append(f"the silent-reasoner failure is worded wrong: {output.strip()[:80]}")
        elif not expect_zero and "verified)" in output:
            # Immediacy is the claim the comment in verify() makes. Appending the
            # failure instead of returning would still exit 1 with the right words,
            # and would still print a tally nothing earned.
            out.append("check_axioms printed a pinned/verified tally after finding "
                       "the reasoner silent")
        else:
            print(f"  ok   [check_axioms] {label}")
    return out


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

    print("\n  -- ledger --")
    ledger_problems = ledger_cases()
    for problem in ledger_problems:
        print(f"  FAIL [ledger]: {problem}")
    results.append(not ledger_problems)

    print("\n  -- meta --")
    # test_meta.py asserted `if V.failures:` -- "the check failed somehow", which any
    # unrelated guard inside it satisfies. Two checks passed that sweep on their own
    # retained guards, so their coverage() calls could have been deleted outright and
    # `make meta` stayed green. This mutation is that exact shape: a check with no
    # coverage() call and a failure from somewhere else.
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
