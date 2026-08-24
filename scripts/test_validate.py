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
        "the forecast-target check traverses nothing",
        "scripts/validate.py",
        """    has_part = URIRef(BFO + "BFO_0000178")""",
        """    has_part = URIRef(BFO + "BFO_0000178_renamed")""",
        "the has-part or assignsProbabilityTo chain is broken",
    ),
    (
        "class unrooted from BFO",
        "src/kalshi.ttl",
        """ksh:Position a owl:Class ;
    rdfs:subClassOf fm:InformationContentEntity ;""",
        """ksh:Position a owl:Class ;""",
        "not grounded in BFO",
    ),
    (
        "the only forecast probability downgraded, breaking the join",
        EXAMPLE,
        """ex:ForecastProb-82-83 a fm:ForecastProbability ;""",
        """ex:ForecastProb-82-83 a fm:ProbabilityAssignment ;""",
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
        # Check 5 only ever appended to notes, so eight live terms had no
        # definition while CLAUDE.md promised the validator failed without one.
        "a term left without a skos:definition",
        "src/weather.ttl",
        """    skos:definition "The atmospheric quality corresponding to the compass bearing from which a portion of air is moving." .""",
        """    skos:scopeNote "Reported as the bearing the wind blows FROM." .""",
        "no skos:definition: https://w3id.org/forecast-market-ontology/weather#WindDirection",
    ),
    (
        # Check 2b hard-coded two QUDT IRIs, so the third class the generator adds
        # floated under owl:Thing -- the exact defect 2b exists to catch.
        "a bridged QUDT class left unrooted",
        "src/core.ttl",
        """qudt:QuantityKindDimensionVector rdfs:subClassOf fm:Designation .""",
        """""",
        "bridged external class not grounded in BFO",
    ),
    (
        # our_classes was built from `a owl:Class` alone, so a class introduced by
        # subClassOf only was invisible to every check rather than merely unrooted.
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
]


# Defects that must break a competency question rather than quietly changing its answer.
COMPETENCY_CASES = [
    (
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
        "returned 0 rows",
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
        # mode is a differing result rather than an empty one. The empty-result path
        # is still covered by the broken-join case above.
        "settlement no longer records the document it read",
        EXAMPLE,
        """    fm:hasInput ex:TWCRecord-2026-08-16 ;""",
        """""",
        "differs from",
    ),
]


def run_case(name: str, rel: str, find: str, replace: str, expect: str,
             script: str = "scripts/validate.py") -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "fmo"
        shutil.copytree(
            ROOT, work,
            ignore=shutil.ignore_patterns(".git", "build", "__pycache__", "*.pyc"),
        )
        target = work / rel
        text = target.read_text()
        if text.count(find) != 1:
            print(f"  SETUP FAIL [{name}]: anchor found {text.count(find)} times in {rel}")
            return False
        target.write_text(text.replace(find, replace))

        proc = subprocess.run(
            [sys.executable, *script.split()],
            cwd=work, capture_output=True, text=True,
        )
        output = proc.stdout + proc.stderr

        if proc.returncode == 0:
            print(f"  FAIL [{name}]: {Path(script).name} passed but should have failed")
            return False
        if expect not in output:
            print(f"  FAIL [{name}]: exited non-zero but message missing")
            print(f"         expected substring: {expect!r}")
            return False
        print(f"  ok   [{name}]")
        return True


def main() -> int:
    # Baseline: the unmodified tree must pass both checkers, or the negative
    # results below mean nothing.
    baseline_ok = True
    for script in ("scripts/validate.py", "scripts/run_competency.py"):
        proc = subprocess.run(
            [sys.executable, script], cwd=ROOT, capture_output=True, text=True,
        )
        if proc.returncode != 0:
            print(f"BASELINE FAIL: {script} does not pass on the unmodified tree")
            print(proc.stdout + proc.stderr)
            baseline_ok = False
        else:
            print(f"  ok   [baseline: {Path(script).name} passes on clean tree]")
    if not baseline_ok:
        return 1

    print("\n  -- validator --")
    results = [run_case(*case) for case in CASES]
    print("\n  -- competency questions --")
    results += [
        run_case(*case, script="scripts/run_competency.py")
        for case in COMPETENCY_CASES
    ]

    # --update used to return 0 unconditionally. A query that errors or returns
    # nothing skips its write, so the stale .expected survives and `make cq-update`
    # reported success with no diff for exactly the query that was broken.
    print("\n  -- cq-update --")
    results.append(run_case(
        *COMPETENCY_CASES[0][:4],
        "returned 0 rows",
        script="scripts/run_competency.py --update",
    ))

    passed, total = sum(results) + 2, len(results) + 2
    print(f"\n{passed}/{total} checks passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
