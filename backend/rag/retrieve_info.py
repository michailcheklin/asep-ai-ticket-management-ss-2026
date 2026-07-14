import chromadb
import json
import numpy as np
from collections import defaultdict
import os
from sentence_transformers import SentenceTransformer, CrossEncoder

from .rag_logging import rag_logger

# --- These run ONCE when the module is first imported ---
rag_logger.logger.info("Loading FAQ embedder...")
faq_embedder  = SentenceTransformer("intfloat/multilingual-e5-large")
rag_logger.logger.info("Loading FAQ re-ranker...")
faq_reranker  = CrossEncoder("cross-encoder/mmarco-mMiniLMv2-L12-H384-v1")
rag_logger.logger.info("Loading ticket embedder...")
ticket_embedder = SentenceTransformer("deutsche-telekom/gbert-large-paraphrase-cosine")
rag_logger.logger.info("Connecting to databases...")

# Get the directory where retrieve_info.py is located
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

faq_db_path    = os.path.join(BASE_DIR, "faq_db")
ticket_db_path = os.path.join(BASE_DIR, "ticket_db")

if not os.path.exists(faq_db_path):
    faq_db_not_found_error_message = f"[RAG] FAQ database not found at: {faq_db_path}"
    rag_logger.logger.critical(faq_db_not_found_error_message)
    raise FileNotFoundError(faq_db_not_found_error_message)
if not os.path.exists(ticket_db_path):
    ticket_db_not_found_error_message = f"[RAG] Ticket database not found at: {ticket_db_path}"
    rag_logger.logger.critical(ticket_db_not_found_error_message)
    raise FileNotFoundError(ticket_db_not_found_error_message)

faq_client    = chromadb.PersistentClient(path=faq_db_path)
ticket_client = chromadb.PersistentClient(path=ticket_db_path)

faq_collection = faq_client.get_or_create_collection(
    "faq_entries",
    metadata={"hnsw:space": "cosine"}
)
ticket_collection = ticket_client.get_or_create_collection(
    "tickets",
    metadata={"hnsw:space": "cosine"}
)

rag_logger.logger.info("Ready.\n")

# --- Thresholds ---
TICKET_SIMILARITY_THRESHOLD   = 0.35
CATEGORY_CONFIDENCE_THRESHOLD = 0.50

# --- FAQ tiered thresholds ---
FAQ_TIER_1_THRESHOLD  = 0.40   # return top 4 above this
FAQ_TIER_1_COUNT      = 4
FAQ_TIER_2_THRESHOLD  = 0.20   # fallback: top 2 above this
FAQ_TIER_2_COUNT      = 2
FAQ_TIER_3_THRESHOLD  = 0.15   # last resort: top 1 above this
FAQ_TIER_3_COUNT      = 1


def scaled_sigmoid(x, scale=0.28, shift=1.2):
    """
    Scales returned scores between -5 and 10 to be between 0 and 1
    """
    return 1 / (1 + np.exp(-(x - shift) * scale))


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

    category_sum     = defaultdict(float)
    category_count   = defaultdict(int)
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

def parse_faq_metadata(metadata: dict) -> dict:
    """
    Expand a stored FAQ metadata dict back into its full form, deserialising
    the JSON-encoded extracted_urls field (ChromaDB metadata only supports
    flat primitives, so extracted_urls was stored as a JSON string).
    """
    if not metadata:
        return {}
    parsed = dict(metadata)
    if "extracted_urls" in parsed and isinstance(parsed["extracted_urls"], str):
        try:
            parsed["extracted_urls"] = json.loads(parsed["extracted_urls"])
        except json.JSONDecodeError:
            parsed["extracted_urls"] = []
    return parsed

def select_faq_matches(ranked: list) -> list:
    """
    Apply tiered threshold logic to select FAQ matches.
    ranked: list of (faq_id, doc, raw_score, scaled_score, metadata) sorted by
    scaled_score desc. metadata is carried through untouched -- it plays no
    role in threshold decisions, it just needs to survive to the output.

    Tier 1: top 4 above 0.40
    Tier 2: top 2 above 0.20
    Tier 3: top 1 above 0.15
    """
    tier1 = [(fid, doc, s, meta) for fid, doc, _, s, meta in ranked if s >= FAQ_TIER_1_THRESHOLD]
    if len(tier1) >= 1:
        selected = tier1[:FAQ_TIER_1_COUNT]
        rag_logger.logger.info(f"FAQ tier 1 matched: returning {len(selected)} results above {FAQ_TIER_1_THRESHOLD}")
        return selected

    tier2 = [(fid, doc, s, meta) for fid, doc, _, s, meta in ranked if s >= FAQ_TIER_2_THRESHOLD]
    if len(tier2) >= 1:
        selected = tier2[:FAQ_TIER_2_COUNT]
        rag_logger.logger.info(f"FAQ tier 2 matched: returning {len(selected)} results above {FAQ_TIER_2_THRESHOLD}")
        return selected

    tier3 = [(fid, doc, s, meta) for fid, doc, _, s, meta in ranked if s >= FAQ_TIER_3_THRESHOLD]
    if len(tier3) >= 1:
        selected = tier3[:FAQ_TIER_3_COUNT]
        rag_logger.logger.info(f"FAQ tier 3 matched: returning {len(selected)} results above {FAQ_TIER_3_THRESHOLD}")
        return selected

    rag_logger.logger.info(f"FAQ no results above minimum threshold {FAQ_TIER_3_THRESHOLD}")
    return []

def retrieve_relevant_entries(user_query: str, n_results: int = 5) -> dict:
    """
    Given a user query (new support ticket string), retrieve the most relevant
    FAQ entries and historical tickets above their respective similarity thresholds,
    and infer the most likely category from the matched tickets.

    Args:
        user_query: The incoming support ticket text as a plain string.
        n_results:  Maximum number of results to retrieve from the ticket database.
                    FAQ always fetches 10 candidates for re-ranking.

    Returns:
        {
            "faq_matches"    : list of {"id", "text", "similarity"},
            "ticket_matches" : list of {"id", "text", "similarity", "category"},
            "inferred"       : {"category": str, "confidence": float}
        }
    """

    # ── FAQ retrieval + cross-encoder re-ranking ───────────────────────────────
    rag_logger.logger.info("Encoding FAQ query...")
    faq_embedding = faq_embedder.encode(
        "query: " + user_query,
        normalize_embeddings=True
    ).tolist()

    faq_results = faq_collection.query(
        query_embeddings=[faq_embedding],
        n_results=10,
        include=["documents", "distances", "metadatas"]
    )

    pre_rerank = {
        faq_id: round(1 - dist, 4)
        for faq_id, dist in zip(faq_results["ids"][0], faq_results["distances"][0])
    }

    rag_logger.logger.info(f"Running cross-encoder re-ranking on {len(faq_results['ids'][0])} FAQ candidates...")
    pairs        = [[user_query, doc] for doc in faq_results["documents"][0]]
    raw_scores   = faq_reranker.predict(pairs)
    scaled_scores = scaled_sigmoid(raw_scores)

    ranked = sorted(
        zip(
            faq_results["ids"][0],
            faq_results["documents"][0],
            raw_scores,
            scaled_scores,
            faq_results["metadatas"][0]
        ),
        key=lambda x: x[3],
        reverse=True
    )

    rag_logger.logger.info("FAQ re-ranking results (converting from cosine to sigmoid):")
    rag_result_ranking_table_columns = ['Title'.ljust(80),
                                        'before'.ljust(20),
                                        'after (raw)'.ljust(20),
                                        'after (sigmoid)'.ljust(20),]
    rag_logger.logger.info("|".join(rag_result_ranking_table_columns))

    for faq_id, doc, raw, scaled, meta in ranked:
        pre = pre_rerank[faq_id]
        rag_result_ranking_table_entry = [
            str(faq_id).ljust(80),
            f'{pre:.4f}'.ljust(20),
            f'{raw:.4f}'.ljust(20),
            f'{scaled:.4f}'.ljust(20),
        ]

        rag_logger.logger.info("|".join(rag_result_ranking_table_entry))

    selected = select_faq_matches(ranked)
    faq_matches = [
        {
            "id":         fid,
            "text":       doc,
            "similarity": round(float(score), 4),
            **parse_faq_metadata(meta)
        }
        for fid, doc, score, meta in selected
    ]
    
    # ── Ticket retrieval (symmetric) ──────────────────────────────────────────
    rag_logger.logger.info("Encoding ticket query...")
    ticket_embedding = ticket_embedder.encode(
        user_query,
        normalize_embeddings=True
    ).tolist()

    ticket_results = ticket_collection.query(
        query_embeddings=[ticket_embedding],
        n_results=n_results
    )

    ticket_matches = []
    if ticket_results["ids"] and ticket_results["ids"][0]:
        for ticket_id, ticket_doc, ticket_distance, ticket_meta in zip(
            ticket_results["ids"][0],
            ticket_results["documents"][0],
            ticket_results["distances"][0],
            ticket_results["metadatas"][0]
        ):
            similarity = 1 - ticket_distance
            rag_logger.logger.info(f"[RAG]   [{ticket_id}] similarity: {similarity:.4f}")
            if similarity >= TICKET_SIMILARITY_THRESHOLD:
                ticket_meta = ticket_meta or {}
                ticket_matches.append({
                    "id":         ticket_id,
                    "text":       ticket_doc,
                    "similarity": round(similarity, 4),
                    "category":   extract_category_from_text(ticket_doc),
                    "messages":   ticket_meta.get("messages", "")
                })
    faq_matches    = sorted(faq_matches,    key=lambda x: x["similarity"], reverse=True)
    ticket_matches = sorted(ticket_matches, key=lambda x: x["similarity"], reverse=True)

    rag_logger.logger.info(f"Final: {len(faq_matches)} FAQ matches, {len(ticket_matches)} ticket matches")
    rag_logger.logger.info(f"Inferred category: {infer_category(ticket_matches)}")

    return {
        "faq_matches":    faq_matches,
        "ticket_matches": ticket_matches,
        "inferred":       infer_category(ticket_matches)
    }