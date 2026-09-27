"""
logic_engine.py
----------------
Pure Python decision-logic functions. NO Streamlit, NO ChromaDB, NO LLM calls
here — sirf math aur boolean rules. Ye isliye taaki har function independently
test ho sake, aur numbers kahan se aa rahe hain ye 100% traceable rahe.
"""

# ---------------------------------------------------------------------------
# Reference tables (crop-specific constants)
# ---------------------------------------------------------------------------

# Crop coefficient (Kc) — kitna paani crop apne current stage par "use" karta hai
KC_TABLE = {
    "wheat":  {"initial": 0.4, "development": 0.7, "mid": 1.15, "late": 0.4,
               "flowering": 1.15, "grain-fill": 1.1},
    "tomato": {"initial": 0.6, "development": 0.85, "mid": 1.15, "late": 0.8,
               "flowering": 1.15, "grain-fill": 1.1},
}

# MAD (Management Allowed Depletion) — kitna % soil moisture gir sakta hai
# irrigation trigger hone se pehle. Flowering/grain-fill mein tighter rakha
# hai kyunki ye water-sensitive stages hain.
MAD_TABLE = {
    "wheat":  {"initial": 0.55, "development": 0.55, "mid": 0.50, "late": 0.60,
               "flowering": 0.35, "grain-fill": 0.40},
    "tomato": {"initial": 0.50, "development": 0.50, "mid": 0.45, "late": 0.55,
               "flowering": 0.30, "grain-fill": 0.35},
}

WATER_SENSITIVE_STAGES = {"flowering", "grain-fill"}
RAIN_EFFICIENCY_FACTOR = 0.75          # forecast rain ka kitna % soil mein actually use hota hai
RAIN_PROBABILITY_HOLD_THRESHOLD = 60.0  # % — isse zyada probability ho to irrigate mat karo


# ---------------------------------------------------------------------------
# FUNCTION 1: calculate_irrigation
# ---------------------------------------------------------------------------

def calculate_irrigation(soil_moisture, FC, ET0, rain_48h, crop_stage,
                          crop="wheat", rain_probability_pct=50.0,
                          capillary_correction_mm=0.0):
    """
    soil_moisture : current volumetric soil moisture (mm)
    FC            : field capacity (mm)
    ET0           : reference evapotranspiration (mm/day)
    rain_48h      : forecasted rainfall in next 48 hours (mm)
    crop_stage    : "initial" | "development" | "mid" | "late" | "flowering" | "grain-fill"

    Returns a dict with the decision + full working (for the "Inspect Reasoning" panel).
    """
    crop = crop.lower()
    crop_stage = crop_stage.lower()

    kc = KC_TABLE.get(crop, KC_TABLE["wheat"]).get(crop_stage, 1.0)
    mad = MAD_TABLE.get(crop, MAD_TABLE["wheat"]).get(crop_stage, 0.5)

    etc = ET0 * kc                                   # crop water use today
    p_eff = rain_48h * RAIN_EFFICIENCY_FACTOR          # usable rain
    nir = max(0.0, etc - p_eff - capillary_correction_mm)  # net irrigation requirement

    swd = FC - soil_moisture                           # soil water deficit
    depletion_threshold_mm = FC * mad                  # kitna deficit allowed hai

    is_sensitive_stage = crop_stage in WATER_SENSITIVE_STAGES

    # --- Boolean decision tree (same as your Section 1.1 blueprint) ---
    if swd >= depletion_threshold_mm and p_eff < nir and rain_probability_pct < RAIN_PROBABILITY_HOLD_THRESHOLD:
        action = "IRRIGATE"
        reason_code = "DEFICIT_EXCEEDS_MAD"
    elif p_eff >= nir:
        action = "HOLD"
        reason_code = "RAIN_COMPENSATES"
    elif is_sensitive_stage and swd >= depletion_threshold_mm * 0.7:
        action = "IRRIGATE"
        reason_code = "SENSITIVE_STAGE_OVERRIDE"
    else:
        action = "HOLD"
        reason_code = "WITHIN_SAFE_DEFICIT"

    quantity_mm = round(max(0.0, nir - p_eff), 2) if action == "IRRIGATE" else 0.0
    quantity_liters_per_acre = round(quantity_mm * 4046.86, 1)  # 1mm over 1 acre = 4046.86 L

    return {
        "action": action,
        "quantity_mm": quantity_mm,
        "quantity_liters_per_acre": quantity_liters_per_acre,
        "swd_mm": round(swd, 2),
        "nir_mm": round(nir, 2),
        "p_eff_mm": round(p_eff, 2),
        "reason_code": reason_code,
    }


# ---------------------------------------------------------------------------
# FUNCTION 2: calculate_market_hold
# ---------------------------------------------------------------------------

def calculate_market_hold(current_price, projected_price, days_hold,
                           quality_decay_rate, shelf_life,
                           storage_cost_rate=0.01, risk_premium=0.08,
                           current_quality_grade=1.0):
    """
    current_price       : aaj ka mandi price (₹/quintal)
    projected_price     : N din baad expected price (₹/quintal)
    days_hold           : kitne din hold karne ka plan hai (N)
    quality_decay_rate  : crop-specific daily quality loss (e.g. 0.06 = 6%/day for tomato)
    shelf_life          : max viable holding days is crop ke liye (spoilage limit)
    storage_cost_rate   : daily storage/holding cost (fraction)
    risk_premium        : farmer risk-aversion buffer (0.05-0.15)

    Returns dict with HOLD or SELL_NOW decision + expected values.
    """
    # Hard safety cap — shelf life se zyada din hold karna physically invalid hai
    days_hold = min(days_hold, shelf_life)

    ev_sell_now = current_price * current_quality_grade

    quality_decay = max(0.0, 1 - quality_decay_rate * days_hold)
    storage_cost_factor = max(0.0, 1 - storage_cost_rate * days_hold)
    # spoilage risk simple monotonic model — jitne zyada din, utna zyada risk
    p_spoilage_risk = min(0.95, 0.02 * days_hold)

    ev_hold = projected_price * quality_decay * storage_cost_factor * (1 - p_spoilage_risk)

    if ev_hold > ev_sell_now * (1 + risk_premium):
        action = "HOLD"
        reason_code = "PROJECTED_VALUE_EXCEEDS_RISK_PREMIUM"
    else:
        action = "SELL_NOW"
        reason_code = "HOLD_DOES_NOT_CLEAR_RISK_PREMIUM"

    return {
        "action": action,
        "days_hold_used": days_hold,
        "expected_value_sell_now": round(ev_sell_now, 2),
        "expected_value_hold": round(ev_hold, 2),
        "quality_decay_pct": round(quality_decay_rate * days_hold * 100, 1),
        "reason_code": reason_code,
    }


# ---------------------------------------------------------------------------
# FUNCTION 3: filter_pest_treatment
# ---------------------------------------------------------------------------

# Sprayer type ke hisaab se dosage concentration adjustment
SPRAYER_ADJUSTMENT = {
    "knapsack": 1.0,
    "power_sprayer": 0.9,   # zyada fine mist, thoda kam concentration chahiye
    "drone": 0.8,
}


def filter_pest_treatment(candidates, days_to_harvest, sprayer_type, growth_stage):
    """
    candidates      : list of dicts, e.g.
        [{"name": "Mancozeb 75% WP", "label_rate_ml_per_liter": 2.5, "phi_days": 7,
          "phytotoxic_stages": [], "is_organic": False}, ...]
    days_to_harvest : kitne din baccha hai harvest mein
    sprayer_type    : "knapsack" | "power_sprayer" | "drone"
    growth_stage    : current crop stage (string)

    Returns dict: chosen treatment + dosage, ya NO_SAFE_OPTION agar kuch match nahi hua.
    """
    growth_stage = growth_stage.lower()
    flags = []

    if not candidates:
        return {"action": "NO_SAFE_OPTION", "treatment": None, "dosage_ml_per_liter": None,
                "phi_days": None, "flags": ["NO_CANDIDATES_PROVIDED"], "reason_code": "EMPTY_CANDIDATE_LIST"}

    # STEP 2: PHI hard filter — chemical ka asar harvest tak khatam ho jaana chahiye
    phi_safe = [c for c in candidates if days_to_harvest >= c["phi_days"]]

    if not phi_safe:
        flags.append("CHEMICAL_WINDOW_CLOSED_PHI")
        organic_options = [c for c in candidates if c.get("is_organic") and days_to_harvest >= c["phi_days"]]
        if organic_options:
            chosen = organic_options[0]
            adj = SPRAYER_ADJUSTMENT.get(sprayer_type, 1.0)
            dosage = round(chosen["label_rate_ml_per_liter"] * adj, 2)
            return {"action": "ORGANIC_FALLBACK", "treatment": chosen["name"],
                    "dosage_ml_per_liter": dosage, "phi_days": chosen["phi_days"],
                    "flags": flags, "reason_code": "PHI_VIOLATION_FALLBACK_TO_ORGANIC"}
        return {"action": "NO_SAFE_OPTION", "treatment": None, "dosage_ml_per_liter": None,
                "phi_days": None, "flags": flags + ["NO_ORGANIC_ALTERNATIVE"],
                "reason_code": "ALL_OPTIONS_VIOLATE_PHI"}

    # STEP 4: phytotoxicity filter — kuch chemicals kisi stage par plant ko nuksaan karte hain
    stage_safe = [c for c in phi_safe if growth_stage not in c.get("phytotoxic_stages", [])]

    if not stage_safe:
        flags.append("ALL_PHI_SAFE_OPTIONS_PHYTOTOXIC_AT_STAGE")
        return {"action": "NO_SAFE_OPTION", "treatment": None, "dosage_ml_per_liter": None,
                "phi_days": None, "flags": flags, "reason_code": "PHYTOTOXICITY_CONFLICT"}

    chosen = stage_safe[0]

    # STEP 3: dosage — sprayer-adjusted, but HARD CAPPED at label rate (kabhi bhi zyada nahi)
    adj = SPRAYER_ADJUSTMENT.get(sprayer_type, 1.0)
    dosage = min(chosen["label_rate_ml_per_liter"] * adj, chosen["label_rate_ml_per_liter"])

    return {"action": "SPRAY", "treatment": chosen["name"], "dosage_ml_per_liter": round(dosage, 2),
            "phi_days": chosen["phi_days"], "flags": flags, "reason_code": "TREATMENT_APPROVED"}


# ---------------------------------------------------------------------------
# Quick self-test — isko seedha `python logic_engine.py` se chala sakte ho
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("--- Test 1: Irrigation (Tomato, flowering, low moisture) ---")
    result1 = calculate_irrigation(
        soil_moisture=22, FC=40, ET0=5.5, rain_48h=2,
        crop_stage="flowering", crop="tomato", rain_probability_pct=20,
    )
    print(result1)

    print("\n--- Test 2: Market Hold (Tomato, rising price) ---")
    result2 = calculate_market_hold(
        current_price=1850, projected_price=2050, days_hold=4,
        quality_decay_rate=0.06, shelf_life=7,
    )
    print(result2)

    print("\n--- Test 3: Pest Treatment (PHI safe) ---")
    candidates = [
        {"name": "Mancozeb 75% WP", "label_rate_ml_per_liter": 2.5, "phi_days": 7,
         "phytotoxic_stages": [], "is_organic": False},
        {"name": "Chlorothalonil 75% WP", "label_rate_ml_per_liter": 2.0, "phi_days": 5,
         "phytotoxic_stages": ["flowering"], "is_organic": False},
        {"name": "Neem Oil (organic)", "label_rate_ml_per_liter": 5.0, "phi_days": 1,
         "phytotoxic_stages": [], "is_organic": True},
    ]
    result3 = filter_pest_treatment(candidates, days_to_harvest=10,
                                     sprayer_type="knapsack", growth_stage="vegetative")
    print(result3)

    print("\n--- Test 4: Pest Treatment (PHI VIOLATED — should fallback to organic) ---")
    result4 = filter_pest_treatment(candidates, days_to_harvest=3,
                                     sprayer_type="knapsack", growth_stage="vegetative")
    print(result4)