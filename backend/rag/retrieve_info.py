import chromadb
from collections import defaultdict
import os
from sentence_transformers import SentenceTransformer

# --- These run ONCE when the module is first imported ---
print("[retrieve] Loading FAQ embedder...")
faq_embedder    = SentenceTransformer("msmarco-distilbert-base-dot-prod-v3")
print("[retrieve] Loading ticket embedder...")
ticket_embedder = SentenceTransformer("paraphrase-multilingual-mpnet-base-v2")
print("[retrieve] Connecting to databases...")

# Get the directory where retrieve_info.py is located
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

faq_db_path    = os.path.join(BASE_DIR, "faq_db")
ticket_db_path = os.path.join(BASE_DIR, "ticket_db")

# Check they exist before connecting
if not os.path.exists(faq_db_path):
    raise FileNotFoundError(f"FAQ database not found at: {faq_db_path}")
if not os.path.exists(ticket_db_path):
    raise FileNotFoundError(f"Ticket database not found at: {ticket_db_path}")

chroma_client = chromadb.PersistentClient(path=faq_db_path)
ticket_client = chromadb.PersistentClient(path=ticket_db_path)

faq_collection    = chroma_client.get_or_create_collection(
    "faq_entries",
    metadata={"hnsw:space": "cosine"}
)
ticket_collection = ticket_client.get_or_create_collection(
    "tickets",
    metadata={"hnsw:space": "cosine"}
)

print("[retrieve] Ready.\n")

# --- Thresholds ---
FAQ_SIMILARITY_THRESHOLD      = 0.30
TICKET_SIMILARITY_THRESHOLD   = 0.50
CATEGORY_CONFIDENCE_THRESHOLD = 0.50


def infer_category(ticket_matches: list) -> dict:
    """
    Infer the most likely support category from a list of matched tickets.

    Formula:
        For each category c:
            weighted_sum(c)  = sum of similarities of all tickets in c
            normalized(c)    = weighted_sum(c) / sum of ALL ticket similarities
            mean_sim(c)      = weighted_sum(c) / count of tickets in c
            confidence(c)    = normalized(c) * mean_sim(c)

        winner               = category with highest confidence
        if confidence(winner) < CATEGORY_CONFIDENCE_THRESHOLD → "unknown"
    """
    if not ticket_matches:
        return {"category": "unknown", "confidence": 0.0}

    category_sum   = defaultdict(float)
    category_count = defaultdict(int)
    total_similarity = sum(m["similarity"] for m in ticket_matches)

    for match in ticket_matches:
        cat = match.get("category", "unknown")
        category_sum[cat]   += match["similarity"]
        category_count[cat] += 1

    category_scores = {}
    for cat, sim_sum in category_sum.items():
        normalized = sim_sum / total_similarity
        mean_sim   = sim_sum / category_count[cat]
        category_scores[cat] = round(normalized * mean_sim, 4)

    winner     = max(category_scores, key=category_scores.get)
    confidence = category_scores[winner]

    if confidence < CATEGORY_CONFIDENCE_THRESHOLD:
        return {"category": "unknown", "confidence": round(confidence, 4)}

    return {"category": winner, "confidence": round(confidence, 4)}


def extract_category_from_text(text: str) -> str:
    """Parse the category field out of a stored ticket's flat text"""
    for line in text.splitlines():
        if line.startswith("category:"):
            return line.split("category:", 1)[1].strip()
    return "unknown"


def retrieve_relevant_entries(user_query: str, n_results: int = 5) -> dict:
    """
    Given a user query (new support ticket string), retrieve the most relevant
    FAQ entries and historical tickets above their respective similarity thresholds,
    and infer the most likely category from the matched tickets.

    Args:
        user_query: The incoming support ticket text as a plain string.
        n_results:  Maximum number of results to retrieve from each database.

    Returns:
        {
            "faq_matches"    : list of {"id", "text", "similarity"},
            "ticket_matches" : list of {"id", "text", "similarity", "category"},
            "inferred"       : {"category": str, "confidence": float}
        }
    """

    # ── FAQ retrieval (asymmetric) ─────────────────────────────────────────────
    faq_embedding = faq_embedder.encode(user_query).tolist()
    faq_results   = faq_collection.query(
        query_embeddings=[faq_embedding],
        n_results=n_results
    )

    faq_matches = []
    if faq_results["ids"] and faq_results["ids"][0]:
        for faq_id, faq_doc, faq_distance in zip(
            faq_results["ids"][0],
            faq_results["documents"][0],
            faq_results["distances"][0]
        ):
            similarity = 1 - faq_distance
            if similarity >= FAQ_SIMILARITY_THRESHOLD:
                faq_matches.append({
                    "id":         faq_id,
                    "text":       faq_doc,
                    "similarity": round(similarity, 4)
                })

    # ── Ticket retrieval (symmetric) ──────────────────────────────────────────
    ticket_embedding = ticket_embedder.encode(user_query).tolist()
    ticket_results   = ticket_collection.query(
        query_embeddings=[ticket_embedding],
        n_results=n_results
    )

    ticket_matches = []
    if ticket_results["ids"] and ticket_results["ids"][0]:
        for ticket_id, ticket_doc, ticket_distance in zip(
            ticket_results["ids"][0],
            ticket_results["documents"][0],
            ticket_results["distances"][0]
        ):
            similarity = 1 - ticket_distance
            if similarity >= TICKET_SIMILARITY_THRESHOLD:
                ticket_matches.append({
                    "id":         ticket_id,
                    "text":       ticket_doc,
                    "similarity": round(similarity, 4),
                    "category":   extract_category_from_text(ticket_doc)
                })

    faq_matches    = sorted(faq_matches,    key=lambda x: x["similarity"], reverse=True)
    ticket_matches = sorted(ticket_matches, key=lambda x: x["similarity"], reverse=True)

    return {
        "faq_matches":    faq_matches,
        "ticket_matches": ticket_matches,
        "inferred":       infer_category(ticket_matches)
    }