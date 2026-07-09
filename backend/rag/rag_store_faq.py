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


def extract_faq_contents(faq_entry: dict) -> list:
    """Pull only the 'faq_content' strings out of the new nested solution
    schema (list of {faq_content, extracted_urls}). Scraped url content is
    intentionally ignored here -- it is noise, not signal."""
    contents = []
    for sol in faq_entry.get("solution", []):
        if isinstance(sol, dict) and sol.get("faq_content"):
            contents.append(sol["faq_content"])
    return contents

def build_faq_metadata(faq_entry: dict) -> dict:
    """Collect all fields that must be STORED but NOT tokenised/embedded.
    These have zero influence on the embedding vector and therefore zero
    influence on retrieval ranking -- they are returned alongside a match
    purely as supplementary information."""
    metadata = {}

    if faq_entry.get("last_update"):
        metadata["last_update"] = faq_entry["last_update"]
    if faq_entry.get("url"):
        metadata["url"] = faq_entry["url"]

    # ChromaDB metadata values must be primitives (str/int/float/bool),
    # so nested extracted_urls lists are JSON-serialised into a string.
    extracted_urls = []
    for sol in faq_entry.get("solution", []):
        if isinstance(sol, dict):
            extracted_urls.extend(sol.get("extracted_urls", []))
    if extracted_urls:
        metadata["extracted_urls"] = json.dumps(extracted_urls, ensure_ascii=False)

    return metadata

def flatten_faq_entry(faq_entry: dict) -> str:
    """Convert ONLY the tokenised fields (id, context, problem, solution)
    of a FAQ entry into a single string. This string is what gets embedded --
    nothing else should feed the vector."""
    parts = []
    if faq_entry.get("id"):
        parts.append(f"id: {faq_entry['id']}")
    if faq_entry.get("context"):
        parts.append(f"context: {faq_entry['context']}")
    if faq_entry.get("problem"):
        parts.append(f"problem: {faq_entry['problem']}")

    faq_contents = extract_faq_contents(faq_entry)
    if faq_contents:
        parts.append(f"solution: {' '.join(faq_contents)}")

    return "\n".join(parts)

def store_faq_entry(faq_id: str, faq_text: str, metadata: dict):
    embedding = faq_embedder.encode(
        "passage: " + faq_text,
        normalize_embeddings=True
    ).tolist()
    faq_collection.add(
        ids=[faq_id],
        embeddings=[embedding],
        documents=[faq_text],
        metadatas=[metadata]
    )
    print(f"  [STORED] {faq_id}")

with open("./faq_extracted_with_crawled_content.json", "r", encoding="utf-8") as f:
    faq_data = json.load(f)

faq_entries = faq_data["faq_entries"]
print(f"\n[INFO] Storing {len(faq_entries)} FAQ entries...\n")

for faq_entry in faq_entries:
    faq_text = flatten_faq_entry(faq_entry)
    faq_metadata = build_faq_metadata(faq_entry)
    store_faq_entry(faq_entry["id"], faq_text, faq_metadata)

print(f"\n[INFO] Done. {len(faq_entries)} FAQ entries stored.\n")