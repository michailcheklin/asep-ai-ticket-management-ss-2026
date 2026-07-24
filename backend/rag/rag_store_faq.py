import json

"""
This script writes the FAQ entries from a json file into the rag database.
Usage: python3 rag_store_faq.py

NOTE: The pure helper functions below (build_faq_metadata, extract_faq_contents,
flatten_faq_entry, make_unique_ids) are imported and reused by the single-entry
runtime path in faq_submission.py. Keep them free of module-level side effects --
the wipe-and-rebuild logic lives in main() so importing this module never touches
the collection.
"""


def build_faq_metadata(faq_entry: dict) -> dict:
    """Collect ONLY the genuinely NEW schema element that has no equivalent
    in the original FAQ format. Always includes 'extracted_urls' (even if
    empty) so ChromaDB never receives an empty metadata dict."""
    extracted_urls = []
    for sol in faq_entry.get("solution", []):
        if isinstance(sol, dict):
            extracted_urls.extend(sol.get("extracted_urls", []))

    return {"extracted_urls": json.dumps(extracted_urls, ensure_ascii=False)}


def extract_faq_contents(faq_entry: dict) -> list:
    """Pull the 'faq_content' strings out of the new nested solution schema
    (list of {faq_content, extracted_urls}). Scraped url content is
    intentionally excluded here -- it goes to metadata instead, never to
    the embedding."""
    contents = []
    for sol in faq_entry.get("solution", []):
        if isinstance(sol, dict) and sol.get("faq_content"):
            contents.append(sol["faq_content"])
    return contents


def flatten_faq_entry(faq_entry: dict) -> str:
    """Convert a JSON formatted FAQ entry to a single string -- reproduces
    EXACTLY the same fields, order, and formatting as the ORIGINAL
    flatten_faq_entry (context, problem, solution, last_update, url), so the
    embedded text -- and therefore retrieval behaviour -- matches the
    pre-schema-change pipeline. 'id' was never part of the embedded text
    in the original script and is intentionally not added here."""
    parts = []
    if faq_entry.get("context"):
        parts.append(f"context: {faq_entry['context']}")
    if faq_entry.get("problem"):
        parts.append(f"problem: {faq_entry['problem']}")

    faq_contents = extract_faq_contents(faq_entry)
    if faq_contents:
        parts.append(f"solution: {' '.join(faq_contents)}")

    if faq_entry.get("last_update"):
        parts.append(f"last_update: {faq_entry['last_update']}")
    if faq_entry.get("url"):
        parts.append(f"url: {faq_entry['url']}")

    return "\n".join(parts)


_FAQ_DOC_PREFIXES = ("context", "problem", "solution", "last_update", "url")


def parse_faq_document(text: str) -> dict:
    """Inverse of flatten_faq_entry: split a flattened FAQ document back into its
    labelled fields (context, problem, solution, last_update, url). Any line that
    doesn't start with a known 'prefix: ' label is appended to the previous field,
    so multi-line values are preserved rather than dropped."""
    fields: dict = {}
    current = None
    for line in text.split("\n"):
        matched = next((p for p in _FAQ_DOC_PREFIXES if line.startswith(p + ": ")), None)
        if matched:
            fields[matched] = line[len(matched) + 2:]
            current = matched
        elif current is not None:
            fields[current] += "\n" + line
    return fields


def make_unique_ids(ids: list) -> list:
    """Disambiguate duplicate FAQ ids (some titles repeat in the source data).
    First occurrence keeps the original id unchanged; subsequent occurrences
    get a __2, __3, ... suffix so nothing is silently dropped by ChromaDB."""
    seen = {}
    unique_ids = []
    for id_ in ids:
        if id_ not in seen:
            seen[id_] = 0
            unique_ids.append(id_)
        else:
            seen[id_] += 1
            unique_ids.append(f"{id_}__{seen[id_]}")
    return unique_ids


def main():
    """Wipe the faq_entries collection and rebuild it from the source JSON."""
    import chromadb
    from sentence_transformers import SentenceTransformer

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
            "hnsw:space": "cosine",
        }
    )
    print("[INFO] Created new faq_entries collection with cosine metric.")

    with open("./faq_extracted_with_crawled_content.json", "r", encoding="utf-8") as f:
        faq_data = json.load(f)

    faq_entries = faq_data["faq_entries"]
    total = len(faq_entries)
    print(f"\n[INFO] Preparing {total} FAQ entries...\n")

    # --- Build everything up front (cheap, CPU-only string ops) ---
    raw_ids = [entry["id"] for entry in faq_entries]
    faq_ids = make_unique_ids(raw_ids)
    faq_texts = [flatten_faq_entry(entry) for entry in faq_entries]
    faq_metadatas = [build_faq_metadata(entry) for entry in faq_entries]

    dup_count = sum(1 for i, rid in enumerate(faq_ids) if rid != raw_ids[i])
    if dup_count:
        print(f"[WARN] {dup_count} duplicate id(s) found in source data; disambiguated with suffixes.\n")

    # --- Encode + store in chunks: gives progress feedback and surfaces
    # errors right after the batch that caused them, instead of only after
    # the full encode finishes. ---
    BATCH_SIZE = 16

    for start in range(0, total, BATCH_SIZE):
        end = min(start + BATCH_SIZE, total)

        chunk_ids = faq_ids[start:end]
        chunk_texts = faq_texts[start:end]
        chunk_metadatas = faq_metadatas[start:end]

        embeddings = faq_embedder.encode(
            ["passage: " + text for text in chunk_texts],
            batch_size=BATCH_SIZE,
            normalize_embeddings=True,
        ).tolist()

        faq_collection.add(
            ids=chunk_ids,
            embeddings=embeddings,
            documents=chunk_texts,
            metadatas=chunk_metadatas,
        )

        pct = end / total * 100
        print(f"[STORED] {end}/{total} ({pct:.1f}%) — last id: {chunk_ids[-1]}")

    print(f"\n[INFO] Done. {total} FAQ entries stored.\n")


if __name__ == "__main__":
    main()