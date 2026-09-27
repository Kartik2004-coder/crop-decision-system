"""
field_context.py
-----------------
Real-world context modifiers that sit ON TOP of logic_engine.py's numbers.
These do NOT change the core SWD/NIR/market math — they adjust what
recommendation actually makes sense given ground realities (water source,
labor, government scheme windows). This is what stops "correct math" from
becoming "useless advice."
"""

from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# 1. WATER SOURCE CONTEXT — irrigation isn't just "yes/no", it has a cost
#    and an availability constraint that differs completely by source.
# ---------------------------------------------------------------------------

WATER_SOURCE_COST_PER_MM_PER_ACRE = {
    "borewell": 180.0,   # diesel/electricity cost estimate
    "canal": 40.0,       # heavily subsidized, but scheduled — not on-demand
    "rainfed": 0.0,      # no irrigation possible at all
}


@dataclass
class WaterSourceAdjustedResult:
    final_action: str            # what the farmer should actually do
    estimated_cost_rs: float
    availability_note: str
    original_action: str         # what logic_engine.py said, for the trace panel


def apply_water_source_context(irrigation_result: dict, water_source: str,
                                canal_days_until_available: int = 0) -> WaterSourceAdjustedResult:
    water_source = water_source.lower()
    original_action = irrigation_result["action"]

    if original_action == "HOLD":
        return WaterSourceAdjustedResult(
            final_action="HOLD", estimated_cost_rs=0.0,
            availability_note="No irrigation needed today.",
            original_action=original_action,
        )

    quantity_mm = irrigation_result["quantity_mm"]
    cost_per_mm = WATER_SOURCE_COST_PER_MM_PER_ACRE.get(water_source, 0.0)
    estimated_cost = round(quantity_mm * cost_per_mm, 0)

    if water_source == "rainfed":
        # The math says IRRIGATE, but there is physically no source.
        return WaterSourceAdjustedResult(
            final_action="WAIT_FOR_RAIN",
            estimated_cost_rs=0.0,
            availability_note="No irrigation source available (rainfed field) — monitor rain forecast closely.",
            original_action=original_action,
        )

    if water_source == "canal" and canal_days_until_available > 0:
        return WaterSourceAdjustedResult(
            final_action="IRRIGATE_WHEN_AVAILABLE",
            estimated_cost_rs=estimated_cost,
            availability_note=f"Canal water scheduled in {canal_days_until_available} day(s) — crop can wait this long safely.",
            original_action=original_action,
        )

    return WaterSourceAdjustedResult(
        final_action="IRRIGATE",
        estimated_cost_rs=estimated_cost,
        availability_note=f"Estimated cost: ₹{estimated_cost:.0f} via {water_source}.",
        original_action=original_action,
    )


# ---------------------------------------------------------------------------
# 2. LABOR / WAGE CONTEXT — a "sell now" call implies "harvest now", which
#    needs labor. No labor = the theoretically optimal call isn't executable.
# ---------------------------------------------------------------------------

DEFAULT_WORKERS_NEEDED_PER_ACRE = 2


@dataclass
class LaborAdjustedResult:
    final_action: str
    delay_cost_estimate_rs: Optional[float]
    note: str


def apply_labor_context(market_result: dict, labor_available: bool,
                         local_daily_wage_rs: float, acres: float = 1.0) -> LaborAdjustedResult:
    if market_result["action"] != "SELL_NOW":
        return LaborAdjustedResult(
            final_action=market_result["action"], delay_cost_estimate_rs=None,
            note="No harvest labor needed today.",
        )

    if labor_available:
        return LaborAdjustedResult(
            final_action="SELL_NOW", delay_cost_estimate_rs=None,
            note="Labor available — proceed with harvest as recommended.",
        )

    # Labor NOT available — the "optimal" sell-now call can't actually happen today.
    workers_needed = round(DEFAULT_WORKERS_NEEDED_PER_ACRE * acres)
    delay_cost = round(workers_needed * local_daily_wage_rs, 0)  # rough 1-day delay cost proxy
    return LaborAdjustedResult(
        final_action="DELAY_1_DAY_ARRANGE_LABOR",
        delay_cost_estimate_rs=delay_cost,
        note=f"No labor available today — arrange {workers_needed} worker(s) (~₹{delay_cost:.0f}/day) before harvest.",
    )


# ---------------------------------------------------------------------------
# 3. GOVERNMENT SCHEME / INSURANCE LAYER — a static, mock PMFBY-style window
#    check. In production this would query the actual state PMFBY portal API.
# ---------------------------------------------------------------------------

# Simplified enrollment windows (days-since-sowing) per crop — illustrative only.
PMFBY_ENROLLMENT_WINDOW_DSS = {
    "wheat": (0, 30),
    "tomato": (0, 20),
}


def check_pmfby_window(crop: str, days_since_sowing: int) -> Optional[str]:
    crop = crop.lower()
    window = PMFBY_ENROLLMENT_WINDOW_DSS.get(crop)
    if not window:
        return None
    start, end = window
    if start <= days_since_sowing <= end:
        days_left = end - days_since_sowing
        return f"📋 PMFBY crop insurance window is OPEN — {days_left} day(s) left to enroll."
    return None


# ---------------------------------------------------------------------------
# 4. LIGHT MULTI-CROP ROTATION TIP — a static suggestion, NOT part of the
#    daily decision engine. Shown once, separately, as a longer-horizon nudge.
# ---------------------------------------------------------------------------

ROTATION_SUGGESTIONS = {
    "wheat": "After wheat, consider a legume (moong/urad) in the off-season to restore soil nitrogen before the next wheat cycle.",
    "tomato": "After tomato, avoid replanting another nightshade crop (potato/chili) in the same plot next season to reduce soil-borne disease buildup.",
}


def get_rotation_tip(crop: str) -> str:
    return ROTATION_SUGGESTIONS.get(crop.lower(), "No rotation data available for this crop yet.")