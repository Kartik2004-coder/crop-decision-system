"""
priority_engine.py
-------------------
Collapses 3 separate decisions (irrigation, pest, market) into ONE ranked
lead recommendation with a red/yellow/green urgency color — instead of
showing all 3 at once. Also implements the escalation rule: when confidence
is low or signals conflict, don't guess — route to a human expert.
"""

from dataclasses import dataclass
from typing import List


@dataclass
class RankedAction:
    category: str          # "irrigation" | "pest" | "market"
    urgency_score: float   # 0.0 - 1.0, higher = more urgent
    color: str              # "red" | "yellow" | "green"
    headline: str            # the ONE sentence the farmer sees first


def _score_to_color(score: float) -> str:
    if score >= 0.7:
        return "red"
    if score >= 0.4:
        return "yellow"
    return "green"


def score_irrigation_urgency(irrigation_result: dict, field_capacity_mm: float) -> float:
    if irrigation_result["action"] != "IRRIGATE":
        return 0.1
    # How deep into the depletion is the field, relative to field capacity?
    return min(1.0, irrigation_result["swd_mm"] / field_capacity_mm)


def score_pest_urgency(pest_result: dict) -> float:
    if pest_result["action"] == "NO_SAFE_OPTION":
        return 0.9  # unresolved pest risk is inherently urgent
    if pest_result["action"] in ("SPRAY", "ORGANIC_FALLBACK"):
        # Closer PHI deadline = more time pressure to act correctly
        phi = pest_result.get("phi_days") or 10
        return min(1.0, 1.0 - (phi / 20))
    return 0.1


def score_market_urgency(market_result: dict) -> float:
    if market_result["action"] != "SELL_NOW":
        return 0.2  # holding is rarely time-critical today
    ev_now = market_result["expected_value_sell_now"]
    ev_hold = market_result["expected_value_hold"]
    if ev_now == 0:
        return 0.3
    gap = abs(ev_hold - ev_now) / ev_now
    return min(1.0, 0.3 + gap)  # bigger the gap, the more it matters to act today


def rank_actions(irrigation_result: dict, pest_result: dict, market_result: dict,
                  field_capacity_mm: float,
                  irrigation_headline: str, pest_headline: str, market_headline: str) -> List[RankedAction]:
    scores = [
        RankedAction("irrigation", score_irrigation_urgency(irrigation_result, field_capacity_mm),
                     "", irrigation_headline),
        RankedAction("pest", score_pest_urgency(pest_result), "", pest_headline),
        RankedAction("market", score_market_urgency(market_result), "", market_headline),
    ]
    for a in scores:
        a.color = _score_to_color(a.urgency_score)
    return sorted(scores, key=lambda a: a.urgency_score, reverse=True)


# ---------------------------------------------------------------------------
# ESCALATION — when the system should say "I'm not sure" instead of guessing
# ---------------------------------------------------------------------------

LOW_CONFIDENCE_THRESHOLD = 0.6


def should_escalate(data_confidence: float, has_conflicting_signals: bool = False) -> bool:
    return data_confidence < LOW_CONFIDENCE_THRESHOLD or has_conflicting_signals


def escalation_message() -> str:
    return ("⚠️ Confidence is low or signals conflict today — rather than guess, "
            "please check with your local Krishi Vigyan Kendra (KVK) or extension officer "
            "before acting on this recommendation.")