"""
mock_data.py
------------
Hardcoded but realistic data standing in for IoT sensors, weather API,
mandi price API, and the pest-treatment master list. Replace each dict
with a real API/DB call in production.

Updated: each scenario now also carries field-context data (water source,
labor, wage, acreage, days since sowing) used by field_context.py.
"""

FIELD_CAPACITY_MM = {
    "wheat": 45.0,
    "tomato": 40.0,
}

# Pest treatment candidates per (crop, pest) — feeds filter_pest_treatment()
PEST_CANDIDATES = {
    ("tomato", "early_blight"): [
        {"name": "Mancozeb 75% WP", "label_rate_ml_per_liter": 2.5, "phi_days": 7,
         "phytotoxic_stages": [], "is_organic": False},
        {"name": "Chlorothalonil 75% WP", "label_rate_ml_per_liter": 2.0, "phi_days": 5,
         "phytotoxic_stages": ["flowering"], "is_organic": False},
        {"name": "Neem Oil (organic)", "label_rate_ml_per_liter": 5.0, "phi_days": 1,
         "phytotoxic_stages": [], "is_organic": True},
    ],
    ("wheat", "aphid"): [
        {"name": "Imidacloprid 17.8% SL", "label_rate_ml_per_liter": 0.5, "phi_days": 15,
         "phytotoxic_stages": [], "is_organic": False},
        {"name": "Neem-based bio-pesticide", "label_rate_ml_per_liter": 4.0, "phi_days": 1,
         "phytotoxic_stages": [], "is_organic": True},
    ],
}

# Demo scenarios for the sidebar dropdown
# NEW fields added at the end of each dict: water_source, canal_days_until_available,
# labor_available, local_daily_wage_rs, acres, days_since_sowing
DEFAULT_SCENARIOS = {
    "Wheat — Grain-fill, dry spell": dict(
        crop="wheat", stage="grain-fill", soil_moisture=20, ET0=4.8, rain_48h=1.5,
        rain_probability_pct=15, mandi_price=2150, projected_price=2180, days_hold=5,
        quality_decay_rate=0.001, shelf_life=180, pest="aphid", days_to_harvest=25,
        sprayer_type="knapsack",
        water_source="borewell", canal_days_until_available=0,
        labor_available=True, local_daily_wage_rs=350, acres=1.0, days_since_sowing=45,
    ),
    "Tomato — Flowering, rain incoming": dict(
        crop="tomato", stage="flowering", soil_moisture=22, ET0=5.5, rain_48h=15,
        rain_probability_pct=80, mandi_price=1850, projected_price=2050, days_hold=4,
        quality_decay_rate=0.06, shelf_life=7, pest="early_blight", days_to_harvest=10,
        sprayer_type="knapsack",
        water_source="rainfed", canal_days_until_available=0,
        labor_available=True, local_daily_wage_rs=300, acres=0.5, days_since_sowing=18,
    ),
    "Tomato — Near harvest, PHI conflict": dict(
        crop="tomato", stage="vegetative", soil_moisture=28, ET0=5.0, rain_48h=3,
        rain_probability_pct=30, mandi_price=1600, projected_price=1650, days_hold=3,
        quality_decay_rate=0.07, shelf_life=7, pest="early_blight", days_to_harvest=3,
        sprayer_type="knapsack",
        water_source="canal", canal_days_until_available=2,
        labor_available=False, local_daily_wage_rs=300, acres=0.5, days_since_sowing=60,
    ),
    "Wheat — Mid-stage, healthy": dict(
        crop="wheat", stage="mid", soil_moisture=30, ET0=4.0, rain_48h=5,
        rain_probability_pct=40, mandi_price=2300, projected_price=2350, days_hold=6,
        quality_decay_rate=0.001, shelf_life=180, pest="aphid", days_to_harvest=20,
        sprayer_type="power_sprayer",
        water_source="borewell", canal_days_until_available=0,
        labor_available=True, local_daily_wage_rs=350, acres=2.0, days_since_sowing=55,
    ),
}