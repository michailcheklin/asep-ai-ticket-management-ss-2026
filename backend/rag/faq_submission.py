"""Single-entry FAQ submission: redundancy check -> LLM polish -> store.

Runtime counterpart to the wipe-and-rebuild script rag_store_faq.py. Lets a user
propose one new FAQ entry at a time (exposed via POST /faq). The flow is linear
with a single early-return, so it is a plain function -- no LangGraph needed:

    submit_faq(entry, force)
        1. check_redundancy: is the proposal already covered by existing entries?
           (reuses retrieve_relevant_entries -- same reranked FAQ retrieval the
            chatbot uses). If yes and not forced -> return the covering matches so
            the user can reconsider ("Dennoch anlegen" = call again with force=True).
        2. polish_faq: an LLM cleans up spelling/grammar/style WITHOUT changing
           meaning.
        3. add_faq_entry: upsert into the live faq_entries collection.

Heavy deps (retrieve_info loads the e5-large embedder; llm loads the model) are
imported lazily inside the functions so this module imports cheaply and the
__main__ self-check can stub the steps without loading any models.
"""
from ..config import FAQ_REDUNDANCY_THRESHOLD


def check_redundancy(problem: str) -> list[dict]:
    """Return existing FAQ entries that already cover `problem` (similarity above
    FAQ_REDUNDANCY_THRESHOLD), most similar first. Empty list => proposal is new.

    Each match is returned structured (title + parsed fields) so the frontend can
    render it nicely instead of showing the raw flattened document:
        {"id": <title>, "similarity": ..., "context", "problem", "solution",
         "last_update", "url"}  (last three present only if the entry had them)
    """
    from .rag_store_faq import parse_faq_document
    from .retrieve_info import retrieve_relevant_entries

    result = retrieve_relevant_entries(problem)
    return [
        {"id": m["id"], "similarity": m["similarity"], **parse_faq_document(m["text"])}
        for m in result.get("faq_matches", [])
        if m["similarity"] >= FAQ_REDUNDANCY_THRESHOLD
    ]


def _polish_text(text: str) -> str:
    """Language-only cleanup of a single FAQ text via the LLM (no semantic change)."""
    if not text or not text.strip():
        return text
    from langchain_core.messages import HumanMessage, SystemMessage

    from ..llm.llm import llm
    from ..llm.prompts import FAQ_POLISH_RULES

    response = llm.invoke([
        SystemMessage(content=FAQ_POLISH_RULES),
        HumanMessage(content=text),
    ])
    polished = (response.content or "").strip()
    # Never let a failed/empty polish silently wipe content.
    return polished or text


def polish_faq(entry: dict) -> dict:
    """Return a copy of `entry` with `problem` and each solution's `faq_content`
    language-polished. context, id, url and extracted_urls stay untouched."""
    polished = dict(entry)
    if polished.get("problem"):
        polished["problem"] = _polish_text(polished["problem"])

    new_solution = []
    for sol in polished.get("solution", []):
        if isinstance(sol, dict) and sol.get("faq_content"):
            sol = {**sol, "faq_content": _polish_text(sol["faq_content"])}
        new_solution.append(sol)
    polished["solution"] = new_solution
    return polished


def _strip_question(title: str) -> str:
    """Safety net over the LLM title: drop surrounding quotes and any trailing
    question mark so the stored title is always a statement, never a question."""
    title = title.strip().strip('"').strip("'").strip()
    while title.endswith("?"):
        title = title[:-1].rstrip()
    return title


def generate_faq_title(problem: str, solution: str, current_title: str = "") -> str:
    """LLM-generated FAQ title as a statement (never a question), from problem +
    solution. A non-empty `current_title` that is already a good statement is kept;
    otherwise it is improved. Falls back to current_title / first problem line if
    the LLM yields nothing usable."""
    from langchain_core.messages import HumanMessage, SystemMessage

    from ..llm.llm import llm
    from ..llm.prompts import FAQ_TITLE_RULES

    user = f"Problem: {problem}\nLösung: {solution}"
    if current_title.strip():
        user += f"\nTitel-Vorschlag des Nutzers: {current_title.strip()}"

    response = llm.invoke([
        SystemMessage(content=FAQ_TITLE_RULES),
        HumanMessage(content=user),
    ])
    title = _strip_question(response.content or "")
    if title:
        return title
    if current_title.strip():
        return current_title.strip()
    return problem.strip().splitlines()[0] if problem.strip() else "FAQ-Eintrag"


def list_faq_contexts() -> list[str]:
    """Distinct, sorted FAQ context/category values across the live collection
    (parsed out of the flattened documents). Feeds the frontend context dropdown."""
    from .rag_store_faq import parse_faq_document
    from .retrieve_info import faq_collection

    documents = faq_collection.get(include=["documents"])["documents"]
    contexts = {parse_faq_document(doc).get("context") for doc in documents}
    return sorted(c for c in contexts if c)


def _unique_id(base: str) -> str:
    """Disambiguate against ids already in the collection using the same __2, __3
    suffix convention as rag_store_faq.make_unique_ids (which only dedupes within
    one batch -- here we must check the live DB)."""
    from .retrieve_info import faq_collection

    base = base.strip() or "faq"
    candidate = base
    n = 1
    while faq_collection.get(ids=[candidate])["ids"]:
        n += 1
        candidate = f"{base}__{n}"
    return candidate


def add_faq_entry(entry: dict) -> str:
    """Embed and upsert one FAQ entry into the live faq_entries collection,
    reusing the exact flatten/metadata/prefix logic of the batch store script.
    Returns the id used."""
    from .rag_store_faq import build_faq_metadata, flatten_faq_entry
    from .retrieve_info import faq_collection, faq_embedder

    text = flatten_faq_entry(entry)
    metadata = build_faq_metadata(entry)
    entry_id = _unique_id(entry.get("id") or entry.get("problem") or "faq")

    # "passage: " prefix + normalize to stay consistent with the batch script;
    # the stored `documents` field keeps the un-prefixed flattened text.
    embedding = faq_embedder.encode(
        "passage: " + text, normalize_embeddings=True
    ).tolist()

    faq_collection.upsert(
        ids=[entry_id],
        embeddings=[embedding],
        documents=[text],
        metadatas=[metadata],
    )
    return entry_id


def submit_faq(entry: dict, force: bool = False, confirmed: bool = False) -> dict:
    """Orchestrate the submission. Returns one of:
      {"status": "redundant", "matches": [{id, ...}, ...]}   (needs "Dennoch anlegen"/cancel)
      {"status": "preview",   "entry": <finalized entry>}    (needs user approval, NOT stored)
      {"status": "created",   "id": <str>}
      {"status": "error",     "detail": <str>}

    Flow: first submit -> redundancy check (unless force) -> otherwise polish + title
    and return a "preview" (nothing stored yet). Once the user approves, the frontend
    resubmits with confirmed=True and the finalized entry is stored as-is.
    """
    problem = (entry.get("problem") or "").strip()
    if not problem:
        return {"status": "error", "detail": "problem is required"}
    if not (entry.get("context") or "").strip():
        return {"status": "error", "detail": "category is required"}

    # Already previewed & approved -> store the finalized entry verbatim.
    if confirmed:
        return {"status": "created", "id": add_faq_entry(entry)}

    if not force:
        matches = check_redundancy(problem)
        if matches:
            return {"status": "redundant", "matches": matches}

    # Build the preview: polish language + finalize the title as a statement.
    from .rag_store_faq import extract_faq_contents
    polished = polish_faq(entry)
    solution_text = " ".join(extract_faq_contents(polished))
    polished["id"] = generate_faq_title(
        polished.get("problem", ""), solution_text, entry.get("id", "")
    )
    return {"status": "preview", "entry": polished}


if __name__ == "__main__":
    # Self-check of the branching logic only -- stubs the three steps so no
    # embedder/LLM/DB is loaded. Run: python -m backend.rag.faq_submission
    import backend.rag.faq_submission as m

    CTX = "20 WLAN > 20.01 Zugang"  # category is now mandatory on every path

    # Redundant: a covering match exists and force is off -> early return, no store.
    m.check_redundancy = lambda p: [{"id": "dup", "text": "problem: X\nsolution: Y", "similarity": 0.95}]
    r = m.submit_faq({"problem": "Wie trete ich der Domäne bei?", "context": CTX})
    assert r["status"] == "redundant" and r["matches"][0]["id"] == "dup", r

    # New: nothing covers it -> polish + (LLM) title -> PREVIEW (not stored). Stub
    # the title step so no LLM is loaded.
    m.check_redundancy = lambda p: []
    m.polish_faq = lambda e: {**e, "id": e.get("id", "")}
    m.generate_faq_title = lambda problem, solution, current_title="": "Neuer Aussage-Titel"
    r = m.submit_faq({"problem": "Ein ganz neues, unbekanntes Problem", "context": CTX})
    assert r["status"] == "preview" and r["entry"]["id"] == "Neuer Aussage-Titel", r

    # force=True skips redundancy but still returns a preview (no direct store).
    m.check_redundancy = lambda p: [{"id": "dup", "text": "t", "similarity": 0.99}]
    r = m.submit_faq({"problem": "X", "context": CTX}, force=True)
    assert r["status"] == "preview", r

    # confirmed=True stores the finalized entry verbatim (no redundancy/polish/title).
    m.add_faq_entry = lambda e: "stored-id"
    r = m.submit_faq({"problem": "X", "context": CTX, "id": "Fester Titel"}, confirmed=True)
    assert r["status"] == "created" and r["id"] == "stored-id", r

    # Missing problem / missing category -> error, no storage.
    assert m.submit_faq({"problem": "   ", "context": CTX})["status"] == "error"
    assert m.submit_faq({"problem": "X", "context": "  "})["status"] == "error"

    # Title safety net: strip surrounding quotes and any trailing question mark.
    assert m._strip_question('"Zugang zur Domäne?"') == "Zugang zur Domäne", m._strip_question('"Zugang zur Domäne?"')
    assert m._strip_question("Kein Fragezeichen") == "Kein Fragezeichen"
    assert m._strip_question("Wirklich??") == "Wirklich"

    # parse_faq_document is the inverse of flatten_faq_entry.
    from backend.rag.rag_store_faq import flatten_faq_entry, parse_faq_document
    entry = {
        "id": "Titel",  # not part of the flattened text by design
        "context": "20 WLAN > 20.01 Zugang",
        "problem": "Wie stelle ich das WLAN um?",
        "solution": [{"faq_content": "Folge dem Assistenten.", "extracted_urls": []}],
        "last_update": "Aktualisiert am 19.06.2024",
        "url": "https://example.org/faq?id=1",
    }
    parsed = parse_faq_document(flatten_faq_entry(entry))
    assert parsed["context"] == entry["context"], parsed
    assert parsed["problem"] == entry["problem"], parsed
    assert parsed["solution"] == "Folge dem Assistenten.", parsed
    assert parsed["last_update"] == entry["last_update"], parsed
    assert parsed["url"] == entry["url"], parsed

    print("faq_submission self-check passed.")
