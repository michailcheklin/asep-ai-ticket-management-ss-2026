# RAG Info

## Overview

The RAG (Retrieval-Augmented Generation) module retrieves relevant information from two separate knowledge bases given a user's support ticket query. It returns the most semantically similar FAQ entries and historical solved tickets to be used as context for the AI response.

---

## Databases and paths

We use two separate ChromaDB collections, each with its own embedding model chosen for its specific retrieval relationship:

| Database | Path | Collection |
|---|---|---|
| FAQ | `faq_db` | `faq_entries` |
| Tickets | `ticket_db` | `tickets` |
| Recent Incidents | `recent_incidents_db` | `recent_incidents` |
---

## Models & Design Choices

### FAQ

`intfloat/multilingual-e5-large`  
+  
`cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`

The FAQ retrieval is a two-stage pipeline:

**Stage 1: Bidirectional encoder (`intfloat/multilingual-e5-large`)**

- Retrieves the top 10 candidate FAQ entries from the database using cosine similarity
- This model was chosen because it is trained on asymmetric query-to-passage pairs, meaning it handles short informal queries matched against longer structured documents well (which is the pattern to expect when looking for FAQ entries based on short queries).
- It requires explicit prefixes at encode time: `"query: "` for incoming queries and `"passage: "` for stored documents. Without these the asymmetric benefit is lost
- 768 dimensions, multilingual, cosine similarity

**Stage 2: Cross-encoder re-ranker (`cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`)**

- Takes the 10 candidates from stage 1 and re-scores each `(query, FAQ entry)` pair jointly
- Unlike the bi-encoder which encodes query and document separately, the cross-encoder processes them together allowing full attention between all tokens, this gives much more discriminative and accurate relevance scores
- Outputs raw logits which are then passed through a scaled sigmoid to produce a 0–1 score
- Multilingual, trained on MS MARCO asymmetric pairs

**Why two stages?**
The bi-encoder alone produces compressed scores (e.g. 0.81–0.83 for all results regardless of relevance) because all FAQ entries share domain vocabulary. The cross-encoder re-ranker produces well-spread, discriminative scores that reliably separate relevant from irrelevant results.

---

### Tickets — `deutsche-telekom/gbert-large-paraphrase-cosine`

- Chosen for **symmetric** similarity: matching a short new ticket summary against short old ticket summaries (same style, same length)
- German monolingual model. All ticket data summaries will be stored in German, so a dedicated German model performs better
- Trained specifically for cosine similarity with paraphrase pairs
- 768 dimensions

---

### Recent Incidents — `deutsche-telekom/gbert-large-paraphrase-cosine`
- Same model as the ticket embedder since this database is a subset of the database of all tickets

## Thresholds & Tiered FAQ Selection

### FAQ — Tiered selection logic

Rather than a single threshold, FAQ results are selected in tiers:

| Tier | Threshold | Max results returned | Behaviour |
|---|---|---|---|
| 1 | 0.40 | 4 | Primary: return top 4 above 0.40 |
| 2 | 0.20 | 2 | Fallback: if tier 1 empty, return top 2 above 0.20 |
| 3 | 0.15 | 1 | Last resort: if tier 2 empty, return top 1 above 0.15 |
| None | - | 0 | If nothing passes tier 3, return empty |

### Tickets

```python
TICKET_SIMILARITY_THRESHOLD = 0.35
```

Only tickets above this threshold are returned.

---

### Recent Incidents
Default similarity threshold is 0.55 against which the similarity check while finding recent incidents matching to the topic of the incoming ticket is filtering. Additionally, it is checked for tickets that are more recent than the recency time threshold (default is 8 hours) and also only similar open tickets are returned.

A problem is only created if a specified amount of similar incident tickets (default is 5) that are
* Not closed
* More recent than the recency threshold
* More similar than the similarity threshold
could be found in the recent incidents database.

The thresholds can be altered by supplying the following environment variables in the .env file (also cf. the example.env file) before building the project with Docker:
```
INCIDENT_ESCALATION_MIN_COUNT=5
INCIDENT_RECENCY_WINDOW_HOURS=8
INCIDENT_SIMILARITY_THRESHOLD=0.55
```

## Function Call

```python
from backend.rag.retrieve_info import retrieve_relevant_entries

results = retrieve_relevant_entries(query, n_results=5)
```

| Parameter | Type | Description |
|---|---|---|
| `query` | `str` | The user's problem description as a plain string |
| `n_results` | `int` | Max candidates to retrieve from ticket DB (default: 5) |

> IMPORTANT: n_results here controls the number of old tickets returned and does not affect the FAQ DB. For the FAQ, we use a flexible logic based on the quality of data we find (see: Tiered selection logic).

---

## Return Value

```python
{
    "faq_matches": [
        (
            id,              # str: FAQ entry ID
            problem,         # str: FAQ problem description
            solution,        # str: FAQ solution text (solution[0].faq_content)
            extracted_urls,  # list of (url, status, type, content, notes) tuples, see below
            similarity,      # float: Sigmoid-scaled cross-encoder score (0–1)
        ),
        ...
    ],
    "ticket_matches": [
        {
            "id":         str,   # Ticket ID e.g. "ticket_042"
            "text":       str,   # Flattened ticket text as stored
            "similarity": float, # Cosine similarity (0–1)
            "category":   str    # Category parsed from stored ticket text
        },
        ...
    ],
    "inferred": {
        "category":   str,  # Most likely support category inferred from ticket matches
        "confidence": float # Confidence score (0–1), "unknown" if below threshold
    }
}
```

Each entry in `extracted_urls` is a `(url, status, type, content, notes)` tuple, where `notes` depends on `status`:

| `status` | `notes` |
|---|---|
| `"success"` | Fixed hint that `content` can be used as context for the answer. |
| `"error"` | Fixed hint that the link is likely only reachable via the university network/VPN. |
| `"none"` | Precomputed one-sentence description of the file type and its purpose (see `backend/crawler/generate_none_url_notes.py`), with a generic type-only fallback if not yet precomputed. |

---

## Logging

All internal RAG logs are prefixed with `[RAG]` to distinguish them from application logs:

``` txt
[RAG] Loading FAQ embedder...
[RAG] Running cross-encoder re-ranking on 10 FAQ candidates...
[RAG] FAQ tier 1 matched: returning 3 results above 0.40
[RAG]   [ticket_042] similarity: 0.5123
```

---

## PII Anonymization (Ticket Storage)

Before a solved ticket is written to `ticket_db`, both the embedded text
(`full_conversation`) and the stored metadata (`messages`) are anonymized to
remove personally identifiable information (names, emails, phone numbers,
IBANs, matriculation numbers, IPs/MACs, addresses, dates of birth, etc.).

This happens in `backend/rag/pii_anonymizer.py`, which is imported by
`rag_store_tickets.py` before any ticket is embedded/stored — retrieval
itself is unaffected, since by the time a ticket is in the database it is
already anonymized.

**Pipeline:**

1. **Piiranha** (`iiiorg/piiranha-v1-detect-personal-information`) — detects structured PII (emails, phone numbers, IBANs, credit cards, addresses, DOB, etc.)
2. **flair-DE** (`flair/ner-german-large`) — detects person names only, chosen specifically because it avoids the subword-fragmentation issues transformer models have on German names/compounds
3. **Regex safety net** — catches structured identifiers models tend to miss (matriculation numbers, IPs, MACs, IBANs, phone numbers)

City/country are deliberately **not** masked, to preserve useful context (e.g. "the printer in the Essen campus library").

Like the retrieval models, both models are **loaded once at import time** (see `[Anonymizer]`-prefixed startup logs), so they're warm before the first ticket-closed webhook arrives.

**Known limitations** (documented, non-blocking): a small number of edge cases are not reliably caught (e.g. passwords that are sent in the support ticket). These are tracked as accepted risk since any password shared with a support agent (although not the norm) must be changed. Even if this is not the case, the username and email address are reliably anonymized so the password alone is not a security threat.

A CI test file, `tests/test_anonymiser.py`, checks anonymization quality on a hand-crafted dataset with known ground truth, enforces zero-tolerance on a list of "critical" PII types (passwords, emails, IBANs, etc.), and prints a full precision/recall + false-positive/negative report.

## Additional Notes

- **Models load once** at module import time (around 30 seconds on my device). Subsequent queries are fast.
- **All input should be in German**. Both databases are stored with German text and the ticket embedder is a German monolingual model. If the user conversation is not in German, the ticket summary should still be in German. For better results, translate input before calling `retrieve_relevant_entries` if needed.
- **A CI test file** is available at `tests/test_rag_retrieve.py` to confirm the databases are loaded correctly and retrieval works as expected.
- **Hardware resources** used by the whole project after this feature is estimated to be around 8 GB of RAM (mostly for loading models that embed and retrieve tickets from the RAG DB as well as models to anonymise tickets).
