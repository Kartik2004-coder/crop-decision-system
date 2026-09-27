"""
test_scenarios.py
------------------
3 edge-case tests against logic_engine.py, run directly (no Streamlit needed).
Run: python test_scenarios.py
"""

from logic_engine import calculate_irrigation, filter_pest_treatment

PASS = "✅ PASS"
FAIL = "❌ FAIL"


def test_1_rain_override_holds_irrigation():
    """Edge case: heavy forecast rain (>15mm) should force HOLD even if soil is dry."""
    result = calculate_irrigation(
        soil_moisture=15,       # low soil moisture — would normally trigger IRRIGATE
        FC=40,
        ET0=5.0,
        rain_48h=20,             # heavy rain incoming
        crop_stage="vegetative",
        crop="tomato",
        rain_probability_pct=85,  # high confidence it will actually rain
    )
    ok = result["action"] == "HOLD" and result["reason_code"] == "RAIN_COMPENSATES"
    print(f"{PASS if ok else FAIL} — Test 1: Rain override (expected HOLD/RAIN_COMPENSATES)")
    print(f"    Got: action={result['action']}, reason={result['reason_code']}, "
          f"NIR={result['nir_mm']}mm, P_eff={result['p_eff_mm']}mm")
    return ok


def test_2_phi_violation_falls_back_to_organic():
    """Edge case: days_to_harvest < every chemical's PHI -> must fallback to organic, never chemical."""
    candidates = [
        {"name": "Mancozeb 75% WP", "label_rate_ml_per_liter": 2.5, "phi_days": 7,
         "phytotoxic_stages": [], "is_organic": False},
        {"name": "Chlorothalonil 75% WP", "label_rate_ml_per_liter": 2.0, "phi_days": 5,
         "phytotoxic_stages": ["flowering"], "is_organic": False},
        {"name": "Neem Oil (organic)", "label_rate_ml_per_liter": 5.0, "phi_days": 1,
         "phytotoxic_stages": [], "is_organic": True},
    ]
    result = filter_pest_treatment(
        candidates=candidates,
        days_to_harvest=3,       # less than Mancozeb's PHI (7) and Chlorothalonil's PHI (5)
        sprayer_type="knapsack",
        growth_stage="vegetative",
    )
    ok = (result["action"] == "ORGANIC_FALLBACK" and result["treatment"] == "Neem Oil (organic)"
          and "CHEMICAL_WINDOW_CLOSED_PHI" in result["flags"])
    print(f"{PASS if ok else FAIL} — Test 2: PHI violation fallback (expected ORGANIC_FALLBACK / Neem Oil)")
    print(f"    Got: action={result['action']}, treatment={result['treatment']}, flags={result['flags']}")

    # Extra safety check: dosage must NEVER exceed the label rate, no matter what
    if result["dosage_ml_per_liter"] is not None:
        dosage_ok = result["dosage_ml_per_liter"] <= 5.0  # Neem Oil's label rate
        print(f"    Dosage safety cap check: {PASS if dosage_ok else FAIL} "
              f"({result['dosage_ml_per_liter']} ml/L <= 5.0 ml/L)")
        ok = ok and dosage_ok
    return ok


def test_3_sensitive_stage_overrides_threshold():
    """Edge case: during flowering/grain-fill, irrigate even on a PARTIAL deficit —
    generic-stage logic would say HOLD here, but sensitive-stage logic must say IRRIGATE."""
    result = calculate_irrigation(
        soil_moisture=30,        # moisture looks "okay" at first glance
        FC=40,
        ET0=5.5,
        rain_48h=1,
        crop_stage="flowering",   # water-sensitive stage
        crop="tomato",
        rain_probability_pct=10,
    )
    ok = result["action"] == "IRRIGATE" and result["reason_code"] == "SENSITIVE_STAGE_OVERRIDE"
    print(f"{PASS if ok else FAIL} — Test 3: Sensitive-stage override (expected IRRIGATE/SENSITIVE_STAGE_OVERRIDE)")
    print(f"    Got: action={result['action']}, reason={result['reason_code']}, SWD={result['swd_mm']}mm")
    return ok


if __name__ == "__main__":
    print("=" * 70)
    print("RUNNING EDGE-CASE TESTS")
    print("=" * 70)

    results = [
        test_1_rain_override_holds_irrigation(),
        test_2_phi_violation_falls_back_to_organic(),
        test_3_sensitive_stage_overrides_threshold(),
    ]

    print("=" * 70)
    passed = sum(results)
    print(f"RESULT: {passed}/{len(results)} tests passed")
    if passed == len(results):
        print("🎉 All edge cases verified — safe to demo.")
    else:
        print("⚠️ Some tests failed — check the logic before demoing to judges.")
    print("=" * 70)