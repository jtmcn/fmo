#!/usr/bin/env python3
"""Generate a synthetic forecast-verification dataset for CQ6.

Calibration is a statistical claim, so it needs a sample. One day of forecasts
demonstrates nothing: the observed frequency in every probability bin is 0 or 1.
This emits 40 days of the KXHIGHNY bracket structure forecast by two models at two
lead times -- 640 probability assignments -- enough for a reliability table with
non-degenerate rows, though still thin per bin: see the note in
queries/cq06a-calibration-reliability.rq about reading the aggregate instead.

THE DATA IS FABRICATED. No real observation, quote, or model output appears here,
and the two models are deliberately fictional so that nothing in this file can be
read as a claim about the skill of GEFS, ECMWF, or any other real system.

The construction, so the expected result is checkable by hand rather than taken on
trust:

  * A "true" daily maximum T is drawn per day, T ~ round(Normal(84, 3.5)).
  * Both models see the same noisy signal mu = T + e, e ~ Normal(0, sigma_lead),
    with sigma_lead = 2.0 at 24h and 3.5 at 72h. Sharing the draw means the two
    models differ ONLY in how confident they claim to be.
  * Bracket probabilities come from the POSTERIOR for T given mu, not from
    Normal(mu, sigma_lead). This matters and the first version of this script got
    it wrong: T has a climatological prior, so seeing mu shifts belief toward
    climatology and narrows it. Forecasting Normal(mu, sigma_lead) over-predicts
    whichever bracket mu lands in, and a Monte Carlo showed it producing
    calibration gaps up to +0.17 in the high bins -- a "calibrated" model that
    was not. With the posterior, simulated gaps are within 0.003 of zero.
      ModelCalibrated    states the true posterior spread          (honest)
      ModelOverconfident states 0.55 x that                        (too sharp)
  * So ModelCalibrated should show observed frequency tracking mean forecast
    probability in each bin, and ModelOverconfident should show observed frequency
    BELOW mean forecast in the high bins and ABOVE it in the low bins -- the
    signature of overconfidence, and the thing CQ6 exists to surface.

Deterministic: fixed seed, no wall-clock input. Re-running reproduces the file
byte for byte, so a diff means the generator changed.

Usage:  python3 scripts/generate_verification_data.py   (or: make verification-data)
"""

from __future__ import annotations

import argparse
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "examples" / "verification-synthetic.ttl"

SEED = 20260815
N_DAYS = 40
START_DATE = datetime(2026, 7, 1, tzinfo=timezone(timedelta(hours=-4)))  # EDT
LEADS = [24, 72]
SIGMA_BY_LEAD = {24: 2.0, 72: 3.5}
OVERCONFIDENCE = 0.55
CLIM_MEAN = 84.0     # climatological mean of the daily maximum
CLIM_SD = 3.5        # and its spread

# Same ladder as the KXHIGHNY example: <=81, [82,83], [84,85], >=86.
# (key, local-name suffix, comparator, floor, cap)
BRACKETS = [
    ("le81", "LE81", "fm:LessThanOrEqual", None, 81),
    ("b82", "B82", "fm:Between", 82, 83),
    ("b84", "B84", "fm:Between", 84, 85),
    ("ge86", "GE86", "fm:GreaterThanOrEqual", 86, None),
]

MODELS = [
    ("ModelCalibrated", "Synthetic model A (states its true posterior spread)", 1.0),
    ("ModelOverconfident", "Synthetic model B (states a spread 45% too small)", OVERCONFIDENCE),
]


def phi(x: float) -> float:
    """Standard normal CDF."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bracket_probabilities(mu: float, sigma: float) -> dict[str, float]:
    """Mass in each bracket under Normal(mu, sigma), using half-degree cut points."""
    p_le81 = phi((81.5 - mu) / sigma)
    p_b82 = phi((83.5 - mu) / sigma) - p_le81
    p_b84 = phi((85.5 - mu) / sigma) - phi((83.5 - mu) / sigma)
    p_ge86 = 1.0 - phi((85.5 - mu) / sigma)
    probs = {"le81": p_le81, "b82": p_b82, "b84": p_b84, "ge86": p_ge86}
    total = sum(probs.values())
    # Renormalise against float drift so each day's ladder sums to exactly 1 at
    # the stored precision; CQ5's coherence check would otherwise flag it.
    return {k: round(v / total, 3) for k, v in probs.items()}


def holds(key: str, t: int) -> bool:
    if key == "le81":
        return t <= 81
    if key == "b82":
        return 82 <= t <= 83
    if key == "b84":
        return 84 <= t <= 85
    return t >= 86


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S%z")[:-2] + ":" + dt.strftime("%z")[-2:]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=OUT,
        help="where to write the dataset; defaults to examples/verification-synthetic.ttl. "
             "A separate path is how `make verification-data-check` diffs the checked-in "
             "file against a fresh generation without touching the working tree.",
    )
    args = parser.parse_args()

    rng = random.Random(SEED)
    out: list[str] = []
    w = out.append

    w(f"""# Synthetic forecast-verification dataset -- GENERATED, DO NOT HAND-EDIT.
#
# Produced by scripts/generate_verification_data.py (seed {SEED}).
# Regenerate with: make verification-data
#
# ALL VALUES ARE FABRICATED. No real observation or model output appears here.
# The two models are fictional by design: nothing in this file should be read as
# a claim about the skill of any real forecasting system.
#
# {N_DAYS} days x 4 brackets x 2 models x 2 lead times = {N_DAYS * 4 * 2 * 2} probability
# assignments, which is what makes CQ6's reliability table non-degenerate. Model A
# states its true error spread; model B states one {int((1 - OVERCONFIDENCE) * 100)}% too small, so B should
# show observed frequency below mean forecast probability in the high bins.

@prefix vex:  <https://w3id.org/forecast-market-ontology/examples/verification#> .
@prefix ex:   <https://w3id.org/forecast-market-ontology/examples/kxhighny-2026-08-15#> .
@prefix fm:   <https://w3id.org/forecast-market-ontology/core#> .
@prefix wx:   <https://w3id.org/forecast-market-ontology/weather#> .
@prefix bfo:  <http://purl.obolibrary.org/obo/> .
@prefix owl:  <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .
@prefix unit: <http://qudt.org/vocab/unit/> .

<https://w3id.org/forecast-market-ontology/examples/verification>
    a owl:Ontology ;
    owl:imports <https://w3id.org/forecast-market-ontology/examples/kxhighny-2026-08-15> ;
    rdfs:label "Synthetic verification dataset for CQ6" .
""")

    for name, label, _ in MODELS:
        w(f"""vex:{name} a wx:NumericalWeatherPredictionModel ;
    rdfs:label "{label}" .
""")

    for i in range(N_DAYS):
        day = START_DATE + timedelta(days=i)
        tag = day.strftime("%Y%m%d")
        start = day.replace(hour=1, minute=0, second=0)
        end = start + timedelta(days=1) - timedelta(seconds=1)

        t = round(rng.gauss(84.0, 3.5))

        w(f"""################  {day.strftime('%Y-%m-%d')}: observed high {t} F  ################

vex:ClimDay-{tag} a wx:ClimatologicalDay ;
    rdfs:label "climatological day {day.strftime('%Y-%m-%d')} at Central Park" ;
    bfo:BFO_0000222 vex:Start-{tag} ; bfo:BFO_0000224 vex:End-{tag} .
vex:Start-{tag} a bfo:BFO_0000203 ; fm:instantDateTime "{iso(start)}"^^xsd:dateTime .
vex:End-{tag}   a bfo:BFO_0000203 ; fm:instantDateTime "{iso(end)}"^^xsd:dateTime .

vex:Target-{tag} a wx:WeatherObservationTarget ;
    rdfs:label "max air temperature, Central Park, {day.strftime('%Y-%m-%d')}" ;
    wx:targetVariable wx:MaximumAirTemperature ;
    wx:atSite ex:CentralParkSite ;
    fm:overTemporalInterval vex:ClimDay-{tag} ;
    wx:underProtocol ex:TWCDailyTempProtocol ;
    fm:hasUnit unit:DEG_F .

vex:Report-{tag} a wx:DailyClimatologicalReport ;
    rdfs:label "CLINYC record for {day.strftime('%Y-%m-%d')}" ;
    fm:issuedBy ex:TWC ;
    fm:overTemporalInterval vex:ClimDay-{tag} ;
    bfo:BFO_0000178 vex:Datum-{tag} .
vex:Datum-{tag} a wx:WeatherObservationDatum ;
    wx:reportsValueFor vex:Target-{tag} ;
    fm:realizedValue "{t}"^^xsd:decimal ;
    fm:hasUnit unit:DEG_F .
""")

        for key, suffix, comparator, floor, cap in BRACKETS:
            thresholds = ""
            if floor is not None:
                thresholds += f'    fm:floorValue "{floor}"^^xsd:decimal ;\n'
            if cap is not None:
                thresholds += f'    fm:capValue "{cap}"^^xsd:decimal ;\n'
            truth = "fm:True" if holds(key, t) else "fm:False"
            w(f"""vex:P-{tag}-{suffix} a fm:Proposition ;
    fm:hasSubject vex:Target-{tag} ;
    fm:hasComparator {comparator} ;
{thresholds}    fm:hasUnit unit:DEG_F .
vex:A-{tag}-{suffix} a fm:TruthAssessment ;
    fm:assessesProposition vex:P-{tag}-{suffix} ;
    fm:assessedTruthValue {truth} ;
    fm:basedOnRecord vex:Report-{tag} ;
    fm:referenceTime "{iso(end + timedelta(hours=10))}"^^xsd:dateTime .
""")

        for lead in LEADS:
            sigma_true = SIGMA_BY_LEAD[lead]
            mu = t + rng.gauss(0.0, sigma_true)   # shared by both models
            # Posterior for T given mu, under the climatological prior. See the
            # module docstring: using Normal(mu, sigma_true) directly is wrong.
            precision = 1.0 / CLIM_SD ** 2 + 1.0 / sigma_true ** 2
            post_sd = 1.0 / math.sqrt(precision)
            post_mean = (CLIM_MEAN / CLIM_SD ** 2 + mu / sigma_true ** 2) / precision
            issued = start - timedelta(hours=lead)
            for name, _, factor in MODELS:
                probs = bracket_probabilities(post_mean, post_sd * factor)
                parts = " , ".join(
                    f"vex:FP-{name}-{lead}-{tag}-{s}" for _, s, _, _, _ in BRACKETS
                )
                w(f"""vex:F-{name}-{lead}-{tag} a wx:ProbabilisticForecast ;
    wx:forecastFor vex:Target-{tag} ;
    wx:producedByModel vex:{name} ;
    wx:leadTimeHours "{lead}"^^xsd:decimal ;
    wx:issuanceTime "{iso(issued)}"^^xsd:dateTime ;
    bfo:BFO_0000178 {parts} .
""")
                for key, suffix, _, _, _ in BRACKETS:
                    w(f"""vex:FP-{name}-{lead}-{tag}-{suffix} a fm:ForecastProbability ;
    fm:assignsProbabilityTo vex:P-{tag}-{suffix} ;
    fm:probabilityValue "{probs[key]:.3f}"^^xsd:decimal ;
    fm:referenceTime "{iso(issued)}"^^xsd:dateTime .
""")

    args.output.write_text("\n".join(out))
    n_assign = N_DAYS * len(BRACKETS) * len(MODELS) * len(LEADS)
    print(f"wrote {args.output}")
    print(f"  {N_DAYS} days, {len(MODELS)} models, {len(LEADS)} lead times, "
          f"{n_assign} probability assignments")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
