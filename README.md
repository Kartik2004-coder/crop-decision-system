# 🌾 Multilingual AI Crop Decision Support System

An enterprise-grade, RAG-grounded decision engine built with Streamlit, ChromaDB, Sentence-Transformers, and Pandas. The system delivers actionable agriculture guidance across 10 Indian languages while maintaining strict English deterministic decision logic.

---

## 🌟 Key Features

- **🌐 10 Indian Languages Support**: Seamless UI localization in Hindi, Bengali, Telugu, Marathi, Tamil, Urdu, Gujarati, Kannada, Malayalam, and Punjabi.
- **⚡ Dual-Gate Anti-Hallucination Guardrails**: Combines deterministic math logic for critical agricultural decisions with vector search explanations.
- **🔍 RAG Explanations**: Contextual retrieval powered by ChromaDB and Sentence-Transformers (`all-MiniLM-L6-v2`).
- **📊 Real-time Dynamic Dashboard**: Interactive Streamlit controls for soil moisture, pest threat levels, market prices, and field conditions.
- **🎯 Multi-Action Priority Engine**: Sorts and prioritizes recommendations based on urgency and crop impact.

---

## 🏗️ System Architecture

```text
[ Streamlit UI (Multilingual) ]
              │
              ├─► Logic Engine (Deterministic Math & Logic Rules)
              │
              ├─► RAG Engine (ChromaDB Vector Store + Dual-Gate Anti-Hallucination)
              │
              └─► Priority Engine & Feedback Logger