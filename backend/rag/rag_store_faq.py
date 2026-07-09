import chromadb
import json
from sentence_transformers import SentenceTransformer

"""
This script writes the FAQ entries from a json file into the rag database.
Usage: python3 rag_store_faq.py
"""

# --- Setup ---
faq_embedder = SentenceTransformer("intfloat/multilingual-e5-large")

chroma_client = chromadb.PersistentClient(path="./faq_db")

# Wipe and recreate with cosine metric
try:
    chroma_client.delete_collection("faq_entries")
    print("[INFO] Deleted old faq_entries collection.")
except Exception as e:
    print(f"[ERROR] Failed to delete old faq_entries collection: {e}")

faq_collection = chroma_client.create_collection(
    "faq_entries",
    metadata={
        "hnsw:space":           "cosine",
    }
)
print("[INFO] Created new faq_entries collection with cosine metric.")


def flatten_faq_entry(faq_entry: dict) -> str:
    """Convert a JSON formatted FAQ entry to a single string"""
    parts = []
    if faq_entry.get("problem"):
        parts.append(f"problem: {faq_entry['problem']}")

    solution = faq_entry.get("solution")
    if solution:
        faq_content = solution[0].get("faq_content")
        if faq_content:
            parts.append(f"faq_content: {faq_content}")

    return "\n".join(parts)


def store_faq_entry(faq_id: str, faq_text: str):
    embedding = faq_embedder.encode(
        "passage: " + faq_text,
        normalize_embeddings=True
    ).tolist()
    faq_collection.add(
        ids=[faq_id],
        embeddings=[embedding],
        documents=[faq_text]
    )
    print(f"  [STORED] {faq_id}")


with open("./faq_extracted_with_crawled_content.json", "r", encoding="utf-8") as f:
    faq_data = json.load(f)

faq_entries = faq_data["faq_entries"]
print(f"\n[INFO] Storing {len(faq_entries)} FAQ entries...\n")

for faq_entry in faq_entries:
    store_faq_entry(faq_entry["id"], flatten_faq_entry(faq_entry))

print(f"\n[INFO] Done. {len(faq_entries)} FAQ entries stored.\n")