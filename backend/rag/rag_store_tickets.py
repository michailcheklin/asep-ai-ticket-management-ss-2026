import json
import os
import sys
from typing import Any

import chromadb
from sentence_transformers import SentenceTransformer

from .pii_anonymizer import anonymize_ticket_fields

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TICKET_DB_PATH = os.path.join(BASE_DIR, "ticket_db")
TICKET_COLLECTION_NAME = "tickets"


_ticket_collection_singleton = None
_ticket_embedder_singleton = None


def _get_ticket_collection() -> Any:
    global _ticket_collection_singleton
    if _ticket_collection_singleton is None:
        client = chromadb.PersistentClient(path=TICKET_DB_PATH)
        _ticket_collection_singleton = client.get_or_create_collection(
            TICKET_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
    return _ticket_collection_singleton


def _get_ticket_embedder() -> SentenceTransformer:
    global _ticket_embedder_singleton
    if _ticket_embedder_singleton is None:
        _ticket_embedder_singleton = SentenceTransformer("deutsche-telekom/gbert-large-paraphrase-cosine")
    return _ticket_embedder_singleton


def _normalize_messages(messages: Any) -> str:
    if not messages:
        return ""
    if isinstance(messages, str):
        return messages.strip()
    if isinstance(messages, (list, tuple)):
        return "\n".join(str(message).strip() for message in messages if str(message).strip())
    return str(messages)


def build_ticket_rag_document(state: dict[str, Any]) -> str:
    full_conversation = (state.get("full_conversation") or "").strip()
    ticket_id = str(state.get("ticket_id") or "").strip()

    parts = []
    if full_conversation:
        parts.append(f"full_conversation: {full_conversation}")
    if ticket_id:
        parts.append(f"ticket_id: {ticket_id}")

    return "\n".join(parts) or "ticket"

def store_ticket_state_to_rag(
    state: dict[str, Any],
    collection: Any | None = None,
    embedder: SentenceTransformer | None = None,
    ticket_id: Any | None = None,
) -> str:
    """Store a closed ticket's conversation summary and category in the ticket RAG DB."""
    collection = collection or _get_ticket_collection()
    embedder = embedder or _get_ticket_embedder()

    resolved_ticket_id = str(ticket_id or state.get("ticket_id") or "unknown")
    if not resolved_ticket_id.startswith("ticket_"):
        resolved_ticket_id = f"ticket_{resolved_ticket_id}"
    if resolved_ticket_id.startswith("ticket_") and resolved_ticket_id.count("_") == 1:
        resolved_ticket_id = resolved_ticket_id.replace("ticket_", "ticket_0", 1)

    raw_full_conversation = (state.get("full_conversation") or "").strip()
    raw_messages = _normalize_messages(state.get("messages"))

    anon_full_conversation, anon_messages = anonymize_ticket_fields(
        raw_full_conversation, raw_messages, ticket_id=resolved_ticket_id
    )

    # >>> TEMP DEBUG: BEFORE/AFTER ANONYMIZATION — DELETE BEFORE COMMIT >>>
    print(f"[DEBUG-ANON] {resolved_ticket_id} BEFORE full_conversation:\n{raw_full_conversation}\n")
    print(f"[DEBUG-ANON] {resolved_ticket_id} AFTER  full_conversation:\n{anon_full_conversation}\n")
    print(f"[DEBUG-ANON] {resolved_ticket_id} BEFORE messages:\n{raw_messages}\n")
    print(f"[DEBUG-ANON] {resolved_ticket_id} AFTER  messages:\n{anon_messages}\n")
    # <<< END TEMP DEBUG — DELETE BEFORE COMMIT <<<

    anonymized_state = dict(state)
    anonymized_state["full_conversation"] = anon_full_conversation

    document = build_ticket_rag_document(anonymized_state)
    metadata = {
        "messages": anon_messages,
    }
    print(f"[RAG] Persisting closed ticket to RAG DB: {resolved_ticket_id}")
    print(f"[RAG] Document preview: {document[:400]}")

    try:
        embedding_result = embedder.encode(document, normalize_embeddings=True)
        embedding = embedding_result.tolist() if hasattr(embedding_result, "tolist") else list(embedding_result)

        collection.add(
            ids=[resolved_ticket_id],
            embeddings=[embedding],
            documents=[document],
            metadatas=[metadata],
        )
        print(f"[RAG] Stored closed ticket in RAG DB: {resolved_ticket_id}")
        return resolved_ticket_id
    except Exception as exc:
        print(f"[RAG] Failed to persist closed ticket in RAG DB: {resolved_ticket_id}: {exc}")
        raise


def load_and_store_tickets(
    json_filepath: str,
    collection: Any | None = None,
    embedder: SentenceTransformer | None = None,
):
    """Load tickets from a JSON file and store them in the vector database."""
    collection = collection or _get_ticket_collection()
    embedder = embedder or _get_ticket_embedder()

    with open(json_filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        tickets = data
    elif isinstance(data, dict):
        tickets = next(iter(data.values()))
    else:
        print("[ERROR] Unexpected JSON structure.")
        sys.exit(1)

    print(f"\n[INFO] Loaded {len(tickets)} tickets from '{json_filepath}'")
    print(f"[INFO] Storing into collection '{collection.name}'...\n")

    for idx, ticket_entry in enumerate(tickets, start=1):
        ticket_id = f"ticket_{idx:03d}"

        raw_full_conversation = (ticket_entry.get("full_conversation") or "").strip()
        raw_messages = _normalize_messages(ticket_entry.get("messages"))

        anon_full_conversation, anon_messages = anonymize_ticket_fields(
            raw_full_conversation, raw_messages, ticket_id=ticket_id
        )

        # >>> TEMP DEBUG: BEFORE/AFTER ANONYMIZATION — DELETE BEFORE COMMIT >>>
        print(f"[DEBUG-ANON] {ticket_id} BEFORE full_conversation:\n{raw_full_conversation}\n")
        print(f"[DEBUG-ANON] {ticket_id} AFTER  full_conversation:\n{anon_full_conversation}\n")
        print(f"[DEBUG-ANON] {ticket_id} BEFORE messages:\n{raw_messages}\n")
        print(f"[DEBUG-ANON] {ticket_id} AFTER  messages:\n{anon_messages}\n")
        # <<< END TEMP DEBUG — DELETE BEFORE COMMIT <<<

        anonymized_entry = dict(ticket_entry)
        anonymized_entry["full_conversation"] = anon_full_conversation

        ticket_text = build_ticket_rag_document(anonymized_entry)
        embedding = embedder.encode(ticket_text, normalize_embeddings=True).tolist()
        metadata = {
            "category": (ticket_entry.get("category") or "").strip(),
            "messages": anon_messages,
        }
        collection.add(
            ids=[ticket_id],
            embeddings=[embedding],
            documents=[ticket_text],
            metadatas=[metadata],
        )
        print(f"  [STORED] {ticket_id} | category: {ticket_entry.get('category', 'N/A')}")
        
    print(f"\n[INFO] Done. {len(tickets)} tickets stored.\n")


if __name__ == "__main__":
    client = chromadb.PersistentClient(path=TICKET_DB_PATH)
    try:
        client.delete_collection(TICKET_COLLECTION_NAME)
        print("[INFO] Deleted old tickets collection.")
    except Exception as e:
        print(f"[ERROR] Failed to delete old tickets collection: {e}")

    ticket_collection = client.create_collection(
        TICKET_COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
    print("[INFO] Created new tickets collection with cosine metric.")
    load_and_store_tickets("./old_tickets.json", collection=ticket_collection)