"""
rag_engine.py
-------------
ChromaDB-based RAG layer with a DUAL-GATE anti-hallucination guardrail:

  Gate 1 (retrieval):  metadata filter (crop, stage, topic) FIRST,
                        then semantic similarity search inside that filtered set.
  Gate 2 (generation):  every number in the generated explanation must exist
                        verbatim in the retrieved text OR in the decision-engine's
                        own output. If not -> fallback to a safe template sentence.
"""

import re
import chromadb
from chromadb.utils import embedding_functions

CHROMA_PATH = "./chroma_db"
COLLECTION_NAME = "agri_knowledge"

# This downloads a small model the FIRST time you run it (needs internet once).
embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"
)

client = chromadb.PersistentClient(path=CHROMA_PATH)


def get_or_create_collection():
    return client.get_or_create_collection(name=COLLECTION_NAME, embedding_function=embedding_fn)


# ---------------------------------------------------------------------------
# Sample ICAR/extension-style knowledge base (metadata-tagged chunks)
# ---------------------------------------------------------------------------

KNOWLEDGE_BASE = [
    {"id": "doc_1", "crop": "tomato", "stage": "vegetative", "topic": "early_blight",
     "text": ("For tomato early blight, Mancozeb 75% WP at 2-2.5 ml/litre gives effective "
              "control when applied at 7-10 day intervals. Maintain a 7-day pre-harvest "
              "interval (PHI) before consumption.")},

    {"id": "doc_2", "crop": "tomato", "stage": "vegetative", "topic": "early_blight",
     "text": ("Neem oil at 5 ml/litre is an approved organic option for early blight in "
              "tomato with a minimal 1-day PHI, suitable when the chemical spray window "
              "has closed near harvest.")},

    {"id": "doc_3", "crop": "tomato", "stage": "flowering", "topic": "early_blight",
     "text": ("Chlorothalonil should be avoided during the flowering stage in tomato due "
              "to phytotoxic risk to blossoms; switch to an alternative fungicide during "
              "this window.")},

    {"id": "doc_4", "crop": "wheat", "stage": "flowering", "topic": "irrigation",
     "text": ("Wheat crops at the flowering and grain-filling stages are highly sensitive "
              "to moisture stress; even a partial soil moisture deficit during this window "
              "can measurably reduce grain weight, so irrigation thresholds should be "
              "tightened compared to the vegetative stage.")},

    {"id": "doc_5", "crop": "wheat", "stage": "mid", "topic": "aphid",
     "text": ("Imidacloprid 17.8% SL at 0.5 ml/litre is effective against wheat aphids, "
              "with a 15-day pre-harvest interval required before grain harvest.")},

    {"id": "doc_6", "crop": "tomato", "stage": "any", "topic": "market",
     "text": ("Tomato fruit quality declines rapidly post-harvest, losing a meaningful "
              "share of market value within days under ambient storage, which limits how "
              "long a farmer can profitably hold stock for a price rise.")},

    {"id": "doc_7", "crop": "wheat", "stage": "any", "topic": "market",
     "text": ("Wheat grain, if stored dry and away from moisture, degrades in quality very "
              "slowly, making multi-week or multi-month holding for better prices "
              "agronomically viable when storage conditions are adequate.")},
]


def ingest_knowledge_base():
    """Idempotent: only ingests if the collection is empty, so re-running the
    app doesn't keep duplicating documents."""
    collection = get_or_create_collection()
    if collection.count() > 0:
        print(f"Collection already has {collection.count()} documents — skipping ingest.")
        return collection

    collection.add(
        ids=[d["id"] for d in KNOWLEDGE_BASE],
        documents=[d["text"] for d in KNOWLEDGE_BASE],
        metadatas=[{"crop": d["crop"], "stage": d["stage"], "topic": d["topic"]} for d in KNOWLEDGE_BASE],
    )
    print(f"Ingested {len(KNOWLEDGE_BASE)} knowledge chunks into ChromaDB.")
    return collection


# ---------------------------------------------------------------------------
# GATE 1: Retrieval — metadata filter FIRST, then semantic similarity
# ---------------------------------------------------------------------------

def retrieve(crop, stage, topic, query_hint="", k=3):
    crop, stage, topic = crop.lower(), stage.lower(), topic.lower()
    collection = get_or_create_collection()

    where_filter = {
        "$and": [
            {"crop": {"$eq": crop}},
            {"topic": {"$eq": topic}},
            {"$or": [{"stage": {"$eq": stage}}, {"stage": {"$eq": "any"}}]},
        ]
    }

    query_text = query_hint if query_hint else topic
    results = collection.query(query_texts=[query_text], n_results=k, where=where_filter)

    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]

    if not docs:
        # Relax stage constraint before giving up entirely — better a slightly
        # less specific match than nothing at all.
        where_relaxed = {"$and": [{"crop": {"$eq": crop}}, {"topic": {"$eq": topic}}]}
        results = collection.query(query_texts=[query_text], n_results=k, where=where_relaxed)
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]

    return list(zip(docs, metas))


# ---------------------------------------------------------------------------
# GATE 2: Post-generation entity validation (anti-hallucination check)
# ---------------------------------------------------------------------------

NUMBER_PATTERN = re.compile(r"\d+(?:\.\d+)?")


def _extract_numbers(text):
    return set(NUMBER_PATTERN.findall(text))


def validate_output(generated_text, allowed_source_texts):
    """
    True only if every number in generated_text also appears somewhere in
    allowed_source_texts. This is what stops a hallucinated dosage or price
    from ever reaching the farmer.
    """
    generated_numbers = _extract_numbers(generated_text)
    if not generated_numbers:
        return True  # nothing numeric to hallucinate

    allowed_numbers = set()
    for src in allowed_source_texts:
        allowed_numbers |= _extract_numbers(src)

    return generated_numbers.issubset(allowed_numbers)


# ---------------------------------------------------------------------------
# Explanation generation (template-based — swap for a real LLM call later)
# ---------------------------------------------------------------------------
# Production system prompt would be:
#   "You may ONLY state facts present in the retrieved context and the
#    structured decision output. Do not invent dosage numbers, chemical
#    names, or timelines. If context is insufficient, output exactly:
#    'Consult local agri-extension officer.'"
# validate_output() below still runs on whatever the LLM returns.

def generate_explanation(decision_summary, triggering_factors, crop, stage, topic, query_hint=""):
    retrieved = retrieve(crop=crop, stage=stage, topic=topic, query_hint=query_hint)
    retrieved_texts = [text for text, meta in retrieved]

    if not retrieved_texts:
        return "Consult local agri-extension officer (no verified guidance found for this combination)."

    factor_str = "; ".join(triggering_factors)
    candidate = f"{decision_summary} Based on: {factor_str}."

    allowed_sources = retrieved_texts + [decision_summary] + triggering_factors
    if not validate_output(candidate, allowed_sources):
        return "Consult local agri-extension officer (guardrail check failed on generated explanation)."

    return candidate


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("--- Ingesting knowledge base ---")
    ingest_knowledge_base()

    print("\n--- Retrieval test: tomato / vegetative / early_blight ---")
    chunks = retrieve(crop="tomato", stage="vegetative", topic="early_blight")
    for text, meta in chunks:
        print(f"[{meta}] {text}")

    print("\n--- Explanation test (should succeed) ---")
    explanation = generate_explanation(
        decision_summary="Spray Mancozeb 75% WP at 2.5 ml/litre.",
        triggering_factors=["Early blight detected", "PHI 7 days satisfied (10 days to harvest)"],
        crop="tomato", stage="vegetative", topic="early_blight",
    )
    print(explanation)

    print("\n--- Guardrail test: deliberately hallucinated dosage (should be REJECTED) ---")
    bad_text = "Spray Mancozeb at 99 ml/litre for best results."
    is_valid = validate_output(bad_text, [text for text, meta in chunks])
    print(f"Is '{bad_text}' valid? -> {is_valid}   (must print False)")