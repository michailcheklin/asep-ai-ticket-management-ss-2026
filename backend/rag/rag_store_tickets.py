import sys
import json
import chromadb
from sentence_transformers import SentenceTransformer

# --- Setup ---
ticket_embedder = SentenceTransformer("paraphrase-multilingual-mpnet-base-v2")

ticket_client   = chromadb.PersistentClient(path="./ticket_db")

# Wipe and recreate with cosine metric
try:
    ticket_client.delete_collection("tickets")
    print("[INFO] Deleted old tickets collection.")
except:
    pass

ticket_collection = ticket_client.create_collection(
    "tickets",
    metadata={"hnsw:space": "cosine"}
)
print("[INFO] Created new tickets collection with cosine metric.")


def flatten_ticket(ticket_entry: dict) -> str:
    """Store only ticket, solution and category — no PII fields"""
    parts = []
    if ticket_entry.get("ticket"):
        parts.append(f"ticket: {ticket_entry['ticket']}")
    if ticket_entry.get("solution"):
        parts.append(f"solution: {ticket_entry['solution']}")
    if ticket_entry.get("category"):
        parts.append(f"category: {ticket_entry['category']}")
    return "\n".join(parts)


def load_and_store_tickets(json_filepath: str):
    with open(json_filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Handle both a raw list and a dict with a named key
    if isinstance(data, list):
        tickets = data
    elif isinstance(data, dict):
        # Grab the first (and presumably only) list value in the dict
        tickets = next(iter(data.values()))
    else:
        print("[ERROR] Unexpected JSON structure.")
        sys.exit(1)

    print(f"\n[INFO] Loaded {len(tickets)} tickets from '{json_filepath}'")
    print(f"[INFO] Storing into collection '{ticket_collection.name}'...\n")

    for idx, ticket_entry in enumerate(tickets, start=1):
        ticket_id   = f"ticket_{idx:03d}"
        ticket_text = flatten_ticket(ticket_entry)
        embedding   = ticket_embedder.encode(ticket_text).tolist()
        ticket_collection.add(
            ids=[ticket_id],
            embeddings=[embedding],
            documents=[ticket_text]
        )
        print(f"  [STORED] {ticket_id} | category: {ticket_entry.get('category', 'N/A')}")

    print(f"\n[INFO] Done. {len(tickets)} tickets stored.\n")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python store_tickets.py <path_to_tickets.json>")
        sys.exit(1)

    load_and_store_tickets(sys.argv[1])