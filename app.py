"""
app.py
------
Streamlit dashboard wiring logic_engine.py + rag_engine.py + translations.py +
field_context.py + priority_engine.py + feedback_log.py together.

Simplified UX: ONE ranked lead recommendation (red/yellow/green urgency),
water/labor/scheme context folded into the headline, escalation to KVK when
confidence is low, and an outcome-feedback capture. Raw math is hidden
behind an "Inspect Reasoning" panel for judges only.

Run:
    streamlit run app.py
"""

import streamlit as st

from logic_engine import calculate_irrigation, calculate_market_hold, filter_pest_treatment
from rag_engine import generate_explanation, ingest_knowledge_base
from mock_data import FIELD_CAPACITY_MM, PEST_CANDIDATES, DEFAULT_SCENARIOS
from translations import TRANSLATIONS, OPTION_LABELS
from field_context import (
    apply_water_source_context, apply_labor_context, check_pmfby_window, get_rotation_tip,
)
from priority_engine import rank_actions, should_escalate, escalation_message
from feedback_log import log_feedback

# Make sure the knowledge base is loaded before the app starts using it.
ingest_knowledge_base()

st.set_page_config(page_title="Crop Decision Support System", page_icon="🌾", layout="centered")

# ---------------------------------------------------------------------------
# Sidebar — Language Selector & Input Simulator
# ---------------------------------------------------------------------------

# Language Selector (Top of Sidebar)
lang_name = st.sidebar.selectbox(
    "🌐 Select Language / भाषा चुनें",
    options=list(TRANSLATIONS.keys()),
    index=0
)

# Fetch translation dictionaries for selected language (fallback to English)
t = TRANSLATIONS.get(lang_name, TRANSLATIONS["English"])
opt = OPTION_LABELS.get(lang_name, OPTION_LABELS["English"])

# App Header
st.title(t["app_title"])

st.sidebar.markdown("---")
st.sidebar.header(t["sidebar_input_simulator"])

scenario_name = st.sidebar.selectbox(t["load_scenario"], list(DEFAULT_SCENARIOS.keys()))
s = DEFAULT_SCENARIOS[scenario_name]

st.sidebar.markdown("---")

# Crop selection
crop_keys = ["wheat", "tomato"]
default_crop_index = crop_keys.index(s["crop"]) if s["crop"] in crop_keys else 0
crop_key = st.sidebar.selectbox(
    t["crop_label"],
    options=crop_keys,
    index=default_crop_index,
    format_func=lambda x: opt.get(x, x.capitalize())
)

# Growth stage selection
STAGE_OPTIONS = ["initial", "development", "vegetative", "mid", "flowering", "grain-fill", "late"]
default_stage_index = STAGE_OPTIONS.index(s["stage"]) if s["stage"] in STAGE_OPTIONS else 0
stage_key = st.sidebar.selectbox(
    t["growth_stage_label"],
    options=STAGE_OPTIONS,
    index=default_stage_index,
    format_func=lambda x: opt.get(x, x.capitalize())
)

days_to_harvest = st.sidebar.slider(t["days_to_harvest_label"], 0, 60, s["days_to_harvest"])

# Sprayer type selection
SPRAYER_OPTIONS = ["knapsack", "power_sprayer", "drone"]
default_sprayer_index = SPRAYER_OPTIONS.index(s["sprayer_type"]) if s["sprayer_type"] in SPRAYER_OPTIONS else 0
sprayer_type_key = st.sidebar.selectbox(
    t["sprayer_type_label"],
    options=SPRAYER_OPTIONS,
    index=default_sprayer_index,
    format_func=lambda x: opt.get(x, x.title())
)

# Soil & Weather Section
st.sidebar.subheader(t["soil_weather_header"])
soil_moisture = st.sidebar.slider(
    t["soil_moisture_label"],
    min_value=0.0, max_value=50.0, value=float(s["soil_moisture"]), step=0.5
)
ET0 = st.sidebar.slider(
    t["et0_label"],
    min_value=0.0, max_value=10.0, value=float(s["ET0"]), step=0.5
)
rain_48h = st.sidebar.slider(
    t["rain_48h_label"],
    min_value=0.0, max_value=50.0, value=float(s["rain_48h"]), step=0.5
)
rain_probability_pct = st.sidebar.slider(
    t["rain_probability_label"],
    min_value=0, max_value=100, value=int(s["rain_probability_pct"]), step=1
)

# Market Section
st.sidebar.subheader(t["market_header"])
mandi_price = st.sidebar.number_input(t["current_price_label"], value=float(s["mandi_price"]), step=10.0)
projected_price = st.sidebar.number_input(t["projected_price_label"], value=float(s["projected_price"]), step=10.0)
days_hold = st.sidebar.slider(t["days_hold_label"], 0, 30, s["days_hold"])
quality_decay_rate = st.sidebar.slider(t["quality_decay_label"], 0.0, 0.15, float(s["quality_decay_rate"]), step=0.001, format="%.3f")
shelf_life = st.sidebar.slider(t["shelf_life_label"], 1, 200, s["shelf_life"])

# Pest Section
st.sidebar.subheader(t["pest_header"])
PEST_OPTIONS = ["aphid", "early_blight"]
default_pest_index = PEST_OPTIONS.index(s["pest"]) if s["pest"] in PEST_OPTIONS else 0
pest_key = st.sidebar.selectbox(
    t["detected_pest_label"],
    options=PEST_OPTIONS,
    index=default_pest_index,
    format_func=lambda x: opt.get(x, x.replace("_", " ").title())
)

# ---------------------------------------------------------------------------
# NEW — Field Context Section (water source, labor, scheme window)
# ---------------------------------------------------------------------------

st.sidebar.markdown("---")
st.sidebar.subheader("🌍 Field Context")

WATER_SOURCE_OPTIONS = ["borewell", "canal", "rainfed"]
default_water_index = WATER_SOURCE_OPTIONS.index(s["water_source"]) if s["water_source"] in WATER_SOURCE_OPTIONS else 0
water_source = st.sidebar.selectbox(
    "Water source", options=WATER_SOURCE_OPTIONS, index=default_water_index,
    format_func=lambda x: x.capitalize()
)
canal_days_until_available = st.sidebar.slider(
    "Canal water available in (days)", 0, 10, s["canal_days_until_available"]
)
labor_available = st.sidebar.checkbox("Labor available today", value=s["labor_available"])
local_daily_wage_rs = st.sidebar.number_input(
    "Local daily wage (₹/worker)", value=float(s["local_daily_wage_rs"]), step=10.0
)
acres = st.sidebar.number_input("Field size (acres)", value=float(s["acres"]), step=0.5)
days_since_sowing = st.sidebar.slider("Days since sowing", 0, 150, s["days_since_sowing"])

data_confidence = st.sidebar.slider(
    "Overall data confidence (simulates sensor health)", 0.0, 1.0, 0.9, step=0.05
)

# ---------------------------------------------------------------------------
# Run the 3 core decision engines (UNCHANGED)
# ---------------------------------------------------------------------------

FC = FIELD_CAPACITY_MM.get(crop_key, 40.0)

irrigation_result = calculate_irrigation(
    soil_moisture=soil_moisture, FC=FC, ET0=ET0, rain_48h=rain_48h,
    crop_stage=stage_key, crop=crop_key, rain_probability_pct=rain_probability_pct,
)

market_result = calculate_market_hold(
    current_price=mandi_price, projected_price=projected_price, days_hold=days_hold,
    quality_decay_rate=quality_decay_rate, shelf_life=shelf_life,
)

candidates = PEST_CANDIDATES.get((crop_key, pest_key), [])
pest_result = filter_pest_treatment(
    candidates=candidates, days_to_harvest=days_to_harvest,
    sprayer_type=sprayer_type_key, growth_stage=stage_key,
)

# ---------------------------------------------------------------------------
# NEW — Apply real-world context layers on top of the raw decision-engine output
# ---------------------------------------------------------------------------

water_adjusted = apply_water_source_context(irrigation_result, water_source, canal_days_until_available)
labor_adjusted = apply_labor_context(market_result, labor_available, local_daily_wage_rs, acres)
pmfby_flag = check_pmfby_window(crop_key, days_since_sowing)
rotation_tip = get_rotation_tip(crop_key)

# ---------------------------------------------------------------------------
# RAG-grounded explanations (unchanged — English, guardrail-validated)
# ---------------------------------------------------------------------------

irrigation_summary = (
    f"Irrigate {irrigation_result['quantity_mm']} mm ({irrigation_result['quantity_liters_per_acre']} L/acre)."
    if irrigation_result["action"] == "IRRIGATE" else "Hold irrigation."
)
irrigation_factors = [
    f"Soil water deficit {irrigation_result['swd_mm']} mm",
    f"Net irrigation requirement {irrigation_result['nir_mm']} mm",
    f"Effective forecast rain {irrigation_result['p_eff_mm']} mm",
    f"Rain probability {rain_probability_pct}%",
]
irrigation_explanation = generate_explanation(
    decision_summary=irrigation_summary, triggering_factors=irrigation_factors,
    crop=crop_key, stage=stage_key, topic="irrigation", query_hint="soil moisture deficit stage sensitivity",
)

if pest_result["action"] in ("SPRAY", "ORGANIC_FALLBACK"):
    pest_summary = f"Spray {pest_result['treatment']} at {pest_result['dosage_ml_per_liter']} ml/litre."
else:
    pest_summary = "No safe treatment available — consult extension officer."
pest_factors = [
    f"PHI {pest_result['phi_days']} days" if pest_result["phi_days"] else "PHI unresolved",
    f"Days to harvest {days_to_harvest}",
]
pest_explanation = generate_explanation(
    decision_summary=pest_summary, triggering_factors=pest_factors,
    crop=crop_key, stage=stage_key, topic=pest_key, query_hint=pest_key,
)

market_summary = (
    f"Hold for {market_result['days_hold_used']} days."
    if market_result["action"] == "HOLD" else "Sell now."
)
market_factors = [
    f"Current price ₹{mandi_price}", f"Projected price ₹{projected_price}",
    f"Expected value if sold now ₹{market_result['expected_value_sell_now']}",
    f"Expected value if held ₹{market_result['expected_value_hold']}",
]
market_explanation = generate_explanation(
    decision_summary=market_summary, triggering_factors=market_factors,
    crop=crop_key, stage=stage_key, topic="market", query_hint="price trend shelf life storage",
)

# ---------------------------------------------------------------------------
# NEW — Collapse everything into ONE ranked lead action
# ---------------------------------------------------------------------------

# Headlines built from the CONTEXT-ADJUSTED result, not raw math —
# "output = one action, not a formula."
irrigation_headline = {
    "IRRIGATE": f"💧 Irrigate today — {water_adjusted.availability_note}",
    "WAIT_FOR_RAIN": f"💧 {water_adjusted.availability_note}",
    "IRRIGATE_WHEN_AVAILABLE": f"💧 {water_adjusted.availability_note}",
    "HOLD": "💧 No irrigation needed today.",
}.get(water_adjusted.final_action, "💧 Check irrigation.")

pest_headline = {
    "SPRAY": f"🌿 Spray {pest_result['treatment']} today ({pest_result['dosage_ml_per_liter']} ml/L).",
    "ORGANIC_FALLBACK": f"🌿 Use {pest_result['treatment']} (organic) — chemical window closed.",
    "NO_SAFE_OPTION": "🌿 No safe treatment found — consult an expert.",
}.get(pest_result["action"], "🌿 Check crop protection.")

if market_result["action"] == "SELL_NOW":
    market_headline = f"💰 {labor_adjusted.note}"
elif market_result["action"] == "HOLD":
    market_headline = f"💰 Hold for {market_result['days_hold_used']} day(s), price expected to rise."
else:
    market_headline = "💰 Check market timing."

ranked = rank_actions(
    irrigation_result, pest_result, market_result, FC,
    irrigation_headline, pest_headline, market_headline,
)

COLOR_MAP = {"red": "🔴", "yellow": "🟡", "green": "🟢"}

# ---------------------------------------------------------------------------
# UI — lead card first, secondary items collapsed, escalation banner if needed
# ---------------------------------------------------------------------------

escalate = should_escalate(data_confidence)

if escalate:
    st.error(escalation_message())
else:
    lead = ranked[0]
    st.markdown(f"## {COLOR_MAP[lead.color]} Today's #1 Priority")
    st.markdown(f"### {lead.headline}")

    if pmfby_flag:
        st.info(pmfby_flag)

    with st.expander("See other 2 items for today"):
        for a in ranked[1:]:
            st.markdown(f"{COLOR_MAP[a.color]} **{a.headline}**")

# Confidence indicator
dots = "●" * round(data_confidence * 5) + "○" * (5 - round(data_confidence * 5))
conf_text = t["confidence_high"] if data_confidence > 0.75 else t["confidence_medium"]
st.caption(f"{t['confidence_label']}: {dots} ({conf_text})")

# ---------------------------------------------------------------------------
# NEW — Outcome feedback capture (only shown when not escalating)
# ---------------------------------------------------------------------------

if not escalate:
    st.markdown("---")
    st.markdown("#### Did you follow yesterday's recommendation?")
    fcol1, fcol2 = st.columns(2)
    if fcol1.button("✅ Yes, followed it"):
        log_feedback(crop_key, stage_key, ranked[0].category, ranked[0].headline, followed=True)
        st.success("Thanks — logged.")
    if fcol2.button("❌ No, did something else"):
        log_feedback(crop_key, stage_key, ranked[0].category, ranked[0].headline, followed=False)
        st.success("Thanks — logged. This helps us improve future advice.")

# ---------------------------------------------------------------------------
# NEW — Rotation tip: separate, long-horizon, not part of daily ranking
# ---------------------------------------------------------------------------

with st.expander("🔄 Long-term tip: next-season rotation"):
    st.write(rotation_tip)

# ---------------------------------------------------------------------------
# "Inspect Logic & Reasoning" — full raw trace for evaluators
# ---------------------------------------------------------------------------

with st.expander(t["inspect_panel_title"]):
    st.markdown(f"#### {t['inspect_irrigation']}")
    st.json(irrigation_result)
    st.json({"water_source_adjustment": water_adjusted.__dict__})

    st.markdown(f"#### {t['inspect_market']}")
    st.json(market_result)
    st.json({"labor_adjustment": labor_adjusted.__dict__})

    st.markdown(f"#### {t['inspect_pest']}")
    st.json(pest_result)

    st.markdown(f"#### {t['rag_guardrail_title']}")
    st.markdown(t["rag_guardrail_text"])
    st.markdown(f"**Irrigation reason:** {irrigation_explanation}")
    st.markdown(f"**Pest reason:** {pest_explanation}")
    st.markdown(f"**Market reason:** {market_explanation}")

    st.markdown("#### Urgency Ranking")
    st.json([{"category": a.category, "urgency_score": a.urgency_score, "color": a.color} for a in ranked])

st.markdown("---")
st.caption(t["footer_caption"])