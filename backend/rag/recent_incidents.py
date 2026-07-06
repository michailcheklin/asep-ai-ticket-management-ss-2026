"""Verwaltung der 'Recent Incidents'-Collection für die Problem-Eskalation.

Diese Collection ist bewusst getrennt von der historischen ``tickets``-Collection
(``rag_store_tickets.py`` löscht jene bei jedem Lauf komplett). Hier werden nur
offene Incidents der letzten Stunden mit Metadaten gehalten, um gehäufte,
thematisch gleiche Incidents zu einem Problem eskalieren zu können.

Metadaten pro Eintrag:
    ticket_id  (int)   – Zammad-Ticket-ID
    status     (str)   – "open" | "closed"
    created_at (float) – Unix-Timestamp (Zahl -> erlaubt $lt/$gte-Filter)
    problem_id (int)   – 0 = keinem Problem zugeordnet, sonst Problem-Ticket-ID
    topic      (str)   – optionales Kurz-Thema für den Problem-Titel
"""
import os
import time

import chromadb

# Denselben (bereits geladenen) symmetrischen Ticket-Embedder wiederverwenden,
# damit das Modell nicht ein zweites Mal in den Speicher geladen wird.
from .retrieve_info import ticket_embedder
from ..config import (
    INCIDENT_RECENCY_WINDOW_HOURS,
    INCIDENT_SIMILARITY_THRESHOLD,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Pfad überschreibbar (z. B. für isolierte Tests) via Umgebungsvariable.
RECENT_INCIDENTS_DB_PATH = os.getenv(
    "RECENT_INCIDENTS_DB_PATH",
    os.path.join(BASE_DIR, "recent_incidents_db"),
)

_client = chromadb.PersistentClient(path=RECENT_INCIDENTS_DB_PATH)
_collection = _client.get_or_create_collection(
    "recent_incidents",
    metadata={"hnsw:space": "cosine"},
)

# Sentinel für "noch keinem Problem zugeordnet".
NO_PROBLEM = 0


def _window_seconds() -> float:
    return INCIDENT_RECENCY_WINDOW_HOURS * 3600.0


def build_incident_text(issue_description: str, additional_info: list[str]) -> str:
    """Baut den Text, der für die semantische Suche eingebettet wird."""
    parts = [issue_description.strip()] if issue_description else []
    if additional_info:
        parts.append(" ".join(str(info) for info in additional_info if info))
    return "\n".join(p for p in parts if p).strip()


def purge_stale_incidents(now: float | None = None) -> int:
    """Löscht alle Incidents, die älter als das konfigurierte Zeitfenster sind.

    :return: Anzahl der gelöschten Einträge (best effort).
    """
    now = now if now is not None else time.time()
    cutoff = now - _window_seconds()
    try:
        stale = _collection.get(where={"created_at": {"$lt": cutoff}})
        stale_ids = stale.get("ids", []) or []
        if stale_ids:
            _collection.delete(ids=stale_ids)
        return len(stale_ids)
    except Exception as e:  # pragma: no cover - defensiv gegen Chroma-Fehler
        print(f"[recent_incidents] purge_stale_incidents failed: {e}")
        return 0


def add_incident(
    ticket_id: int,
    text: str,
    created_at: float | None = None,
    problem_id: int = NO_PROBLEM,
    topic: str = "",
) -> None:
    """Fügt einen offenen Incident der Collection hinzu (bzw. aktualisiert ihn)."""
    if not text:
        return
    created_at = created_at if created_at is not None else time.time()
    try:
        embedding = ticket_embedder.encode(text).tolist()
        _collection.upsert(
            ids=[str(ticket_id)],
            embeddings=[embedding],
            documents=[text],
            metadatas=[{
                "ticket_id": int(ticket_id),
                "status": "open",
                "created_at": float(created_at),
                "problem_id": int(problem_id),
                "topic": topic or "",
            }],
        )
    except Exception as e:  # pragma: no cover
        print(f"[recent_incidents] add_incident failed for {ticket_id}: {e}")


def find_similar_open_incidents(
    text: str,
    exclude_ticket_id: int | None = None,
    n_results: int = 20,
    now: float | None = None,
) -> list[dict]:
    """Semantische Suche über offene Incidents innerhalb des Zeitfensters.

    :return: Liste von Treffern über der Similarity-Schwelle, ohne den
        ausgeschlossenen Incident, absteigend nach Ähnlichkeit sortiert.
        Jeder Treffer: {ticket_id, similarity, problem_id, topic, text}.
    """
    if not text:
        return []
    now = now if now is not None else time.time()
    cutoff = now - _window_seconds()

    try:
        embedding = ticket_embedder.encode(text).tolist()
        results = _collection.query(
            query_embeddings=[embedding],
            n_results=n_results,
            where={"$and": [
                {"status": {"$eq": "open"}},
                {"created_at": {"$gte": cutoff}},
            ]},
        )
    except Exception as e:  # pragma: no cover
        print(f"[recent_incidents] query failed: {e}")
        return []

    matches: list[dict] = []
    if results.get("ids") and results["ids"][0]:
        for doc_id, doc, distance, meta in zip(
            results["ids"][0],
            results["documents"][0],
            results["distances"][0],
            results["metadatas"][0],
        ):
            similarity = 1 - distance
            ticket_id = int(meta.get("ticket_id", doc_id))
            if exclude_ticket_id is not None and ticket_id == exclude_ticket_id:
                continue
            if similarity < INCIDENT_SIMILARITY_THRESHOLD:
                continue
            matches.append({
                "ticket_id": ticket_id,
                "similarity": round(similarity, 4),
                "problem_id": int(meta.get("problem_id", NO_PROBLEM)),
                "topic": meta.get("topic", ""),
                "text": doc,
            })

    matches.sort(key=lambda m: m["similarity"], reverse=True)
    return matches


def find_existing_problem_id(similar_incidents: list[dict]) -> int | None:
    """Prüft, ob einer der ähnlichen Incidents bereits einem Problem zugeordnet ist.

    :return: die problem_id oder None (Dedup-Schritt gegen doppelte Problem-Tickets).
    """
    for incident in similar_incidents:
        problem_id = incident.get("problem_id", NO_PROBLEM)
        if problem_id and problem_id != NO_PROBLEM:
            return int(problem_id)
    return None


def _update_metadata(ticket_id: int, updates: dict) -> None:
    try:
        existing = _collection.get(ids=[str(ticket_id)])
        metas = existing.get("metadatas") or []
        if not metas:
            return
        meta = dict(metas[0])
        meta.update(updates)
        _collection.update(ids=[str(ticket_id)], metadatas=[meta])
    except Exception as e:  # pragma: no cover
        print(f"[recent_incidents] metadata update failed for {ticket_id}: {e}")


def assign_incident_to_problem(ticket_id: int, problem_id: int, topic: str | None = None) -> None:
    """Setzt problem_id (und optional topic) in den Metadaten eines Incidents."""
    updates: dict = {"problem_id": int(problem_id)}
    if topic is not None:
        updates["topic"] = topic
    _update_metadata(ticket_id, updates)


def mark_incident_closed(ticket_id: int) -> None:
    """Entfernt einen geschlossenen Incident aus der Collection."""
    try:
        _collection.delete(ids=[str(ticket_id)])
    except Exception as e:  # pragma: no cover
        print(f"[recent_incidents] mark_incident_closed failed for {ticket_id}: {e}")
