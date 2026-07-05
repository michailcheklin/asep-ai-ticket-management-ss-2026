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

## Function Call

```python
from retrieve_info import retrieve_relevant_entries

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
        {
            "id":         str,   # FAQ entry ID
            "text":       str,   # Full FAQ text as stored
            "similarity": float  # Sigmoid-scaled cross-encoder score (0–1)
        },
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

## Additional Notes

- **Models load once** at module import time (around 30 seconds on my device). Subsequent queries are fast.
- **All input should be in German**. Both databases are stored with German text and the ticket embedder is a German monolingual model. If the user conversation is not in German, the ticket summary should still be in German. For better results, translate input before calling `retrieve_relevant_entries` if needed.
- **A CI test file** is available at `tests/test_rag_retrieve.py` to confirm the databases are loaded correctly and retrieval works as expected.
