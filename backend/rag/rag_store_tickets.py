import json
import os
import sys
from typing import Any

import chromadb
from sentence_transformers import SentenceTransformer

from .retrieve_info import retrieve_relevant_entries
from ..llm.llm import llm


MERGE_SIMILARITY_THRESHOLD = 0.6
MERGE_SEPARATOR = "\n\n" + ("-" * 80) + "\n"
MERGE_MARKER = "Dies ist ein weiterer verwandter Ticket-Eintrag"
FAQ_GENERATION_THRESHOLD = 2

from .pii_anonymizer import anonymize_ticket_fields
from .rag_logging import anon_logger, rag_logger

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
    summary = (state.get("summary") or state.get("full_conversation") or "").strip()
    ticket_id = str(state.get("ticket_id") or "").strip()

    parts = []
    if summary:
        parts.append(f"summary: {summary}")
    if ticket_id:
        parts.append(f"ticket_id: {ticket_id}")

    return "\n".join(parts) or "ticket"


def _detect_similar_ticket(
    collection: Any,
    embedder: SentenceTransformer,
    document: str,
    limit: int = 1,
    retrieval_func: Any | None = None,
) -> tuple[str | None, float | None]:
    if collection is None or embedder is None:
        return None, None

    try:
        retrieval_func = retrieval_func or retrieve_relevant_entries
        results = retrieval_func(document, n_results=limit)
    except Exception as exc:
        rag_logger.warning(f"Unable to query ticket collection for duplicate detection: {exc}")
        return None, None

    ticket_matches = results.get("ticket_matches", [])
    for match in ticket_matches:
        similarity = float(match.get("similarity", 0.0))
        if similarity >= MERGE_SIMILARITY_THRESHOLD:
            return str(match.get("id", "")), similarity

    return None, None


def _count_merge_markers(text: str) -> int:
    if not text:
        return 0
    return text.count(MERGE_MARKER)


def _build_faq_entry_from_merged_tickets(messages: str, document: str, llm_client: Any | None = None) -> dict[str, Any]:
    llm_client = llm_client or llm
    prompt = (
        "Du erstellst einen FAQ-Eintrag für einen IT-Support. "
        "Basierend auf den folgenden zusammengeführten Ticket-Daten, "
        "erstelle ausschließlich ein JSON mit genau diesen Schlüsseln: "
        "id: Das Thema des Eintrags,"
        "context: 2 oder 3 keywords, die beim Matching helfen können,"
        "problem: Die Problembeschreibung in einem Satz,"
        "solution: Die Lösung des Problems, die länger sein darf. (Dieses Feld sieht so aus: 'solution':[{'faq_content':'string')}]" \
        "Du sollst nur die JSON zurückgeben."
        f"TICKET-DATEN:\n{messages}\n\n{document}"
    )
    response = llm_client.invoke([prompt])
    content = getattr(response, "content", response)
    if isinstance(content, str):
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            parsed = json.loads(content.strip("```json\n").strip("```"))
        print(f"Printing parsed LLM reply: {parsed}")
        return parsed
    return {}


def _store_faq_entry(faq_entry: dict[str, Any], faq_collection: Any | None = None, faq_embedder: SentenceTransformer | None = None) -> None:
    if not faq_entry:
        return
    faq_collection = faq_collection or _get_faq_collection()
    faq_embedder = faq_embedder or _get_faq_embedder()

    faq_text = (
        f"context: {' '.join(faq_entry.get('context', []))}\n"
        f"problem: {faq_entry.get('problem', '')}\n"
        f"solution: {faq_entry.get('solution', {}).get('faq_content', '')}"
    )
    embedding_result = faq_embedder.encode(faq_text, normalize_embeddings=True)
    embedding = embedding_result.tolist() if hasattr(embedding_result, "tolist") else list(embedding_result)
    faq_collection.add(
        ids=[faq_entry.get("id", "faq_generated")],
        embeddings=[embedding],
        documents=[faq_text],
        metadatas={"extracted_urls": json.dumps([], ensure_ascii=False)},
    )


def _get_faq_collection() -> Any:
    client = chromadb.PersistentClient(path=os.path.join(BASE_DIR, "faq_db"))
    return client.get_or_create_collection("faq_entries", metadata={"hnsw:space": "cosine"})


def _get_faq_embedder() -> SentenceTransformer:
    return SentenceTransformer("intfloat/multilingual-e5-large")


def _merge_document_with_existing_ticket(
    existing_document: str,
    new_document: str,
    existing_messages: str,
    new_messages: str,
) -> tuple[str, dict[str, Any]]:
    merged_summary = (
        f"{existing_document}\n\n{MERGE_SEPARATOR}{MERGE_MARKER}\n{new_document}"
    )
    merged_messages = (
        f"{existing_messages}\n\n{MERGE_SEPARATOR}{MERGE_MARKER}\n{new_messages}"
    ) if existing_messages and new_messages else (existing_messages or new_messages)
    metadata = {
        "messages": merged_messages,
    }
    return merged_summary, metadata


def store_ticket_state_to_rag(
    state: dict[str, Any],
    collection: Any | None = None,
    embedder: SentenceTransformer | None = None,
    ticket_id: Any | None = None,
    retrieval_func: Any | None = None,
    llm_client: Any | None = None,
    faq_collection: Any | None = None,
    faq_embedder: SentenceTransformer | None = None,
    faq_generation_threshold: int = FAQ_GENERATION_THRESHOLD,
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

    # Debug info for demo purposes, can be removed later
    anon_logger.debug(f"{resolved_ticket_id} BEFORE full_conversation:\n{raw_full_conversation}\n")
    anon_logger.debug(f"{resolved_ticket_id} AFTER  full_conversation:\n{anon_full_conversation}\n")
    anon_logger.debug(f"{resolved_ticket_id} BEFORE messages:\n{raw_messages}\n")
    anon_logger.debug(f"{resolved_ticket_id} AFTER  messages:\n{anon_messages}\n")
    # End debug

    anonymized_state = dict(state)
    anonymized_state["full_conversation"] = anon_full_conversation

    document = build_ticket_rag_document(anonymized_state)
    metadata = {
        "messages": anon_messages,
    }
    rag_logger.info(f"Persisting closed ticket to RAG DB: {resolved_ticket_id}")
    rag_logger.info(f"Document preview: {document[:400]}")

    try:
        similar_ticket_id, similarity = _detect_similar_ticket(
            collection,
            embedder,
            document,
            retrieval_func=retrieval_func,
        )
        if similar_ticket_id is not None:
            rag_logger.info(
                f"Found similar ticket {similar_ticket_id} for {resolved_ticket_id} with similarity {similarity:.4f}; merging into existing entry"
            )
            existing_results = collection.get(ids=[similar_ticket_id], include=["documents", "metadatas"])
            existing_documents = existing_results.get("documents", [])
            existing_metadatas = existing_results.get("metadatas", [])
            if existing_documents and isinstance(existing_documents[0], list):
                existing_document = existing_documents[0][0] if existing_documents[0] else ""
            elif existing_documents:
                existing_document = existing_documents[0]
            else:
                existing_document = ""
            if existing_metadatas and isinstance(existing_metadatas[0], list):
                existing_metadata = existing_metadatas[0][0] if existing_metadatas[0] else {}
            elif existing_metadatas:
                existing_metadata = existing_metadatas[0]
            else:
                existing_metadata = {}
            merged_document, merged_metadata = _merge_document_with_existing_ticket(
                existing_document,
                document,
                existing_metadata.get("messages", ""),
                anon_messages,
            )
            collection.delete(ids=[similar_ticket_id])
            embedding_result = embedder.encode(merged_document, normalize_embeddings=True)
            embedding = embedding_result.tolist() if hasattr(embedding_result, "tolist") else list(embedding_result)
            collection.add(
                ids=[similar_ticket_id],
                embeddings=[embedding],
                documents=[merged_document],
                metadatas=[merged_metadata],
            )
            rag_logger.info(f"Merged closed ticket into existing RAG entry: {similar_ticket_id}")

            merge_count = _count_merge_markers(merged_metadata.get("messages", "")) + 1
            if merge_count >= faq_generation_threshold:
                rag_logger.info(
                    f"Merged ticket count reached threshold {faq_generation_threshold}; generating FAQ entry for {similar_ticket_id}"
                )
                faq_entry = _build_faq_entry_from_merged_tickets(
                    merged_metadata.get("messages", ""),
                    merged_document,
                    llm_client=llm_client,
                )
                # _store_faq_entry(faq_entry, faq_collection=faq_collection, faq_embedder=faq_embedder)

            return similar_ticket_id

        embedding_result = embedder.encode(document, normalize_embeddings=True)
        embedding = embedding_result.tolist() if hasattr(embedding_result, "tolist") else list(embedding_result)

        collection.add(
            ids=[resolved_ticket_id],
            embeddings=[embedding],
            documents=[document],
            metadatas=[metadata],
        )
        rag_logger.info(f"Stored closed ticket in RAG DB: {resolved_ticket_id}")
        return resolved_ticket_id
    except Exception as exc:
        rag_logger.error(f"Failed to persist closed ticket in RAG DB: {resolved_ticket_id}: {exc}")
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

        # Debug info for demo purposes, can be removed later
        print(f"[DEBUG-ANON] {ticket_id} BEFORE full_conversation:\n{raw_full_conversation}\n")
        print(f"[DEBUG-ANON] {ticket_id} AFTER  full_conversation:\n{anon_full_conversation}\n")
        print(f"[DEBUG-ANON] {ticket_id} BEFORE messages:\n{raw_messages}\n")
        print(f"[DEBUG-ANON] {ticket_id} AFTER  messages:\n{anon_messages}\n")
        # End debug

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