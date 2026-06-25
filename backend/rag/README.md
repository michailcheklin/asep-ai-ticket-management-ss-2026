
# RAG info

## Databases

We use two Separate ChromaDB Collections:

* faq_db: Uses `msmarco-distilbert-base-dot-prod-v3` model to retrieve information from the FAQ DB. This model works best for matching a short informal query with a longer structured document.

* ticket_db: Uses `paraphrase-multilingual-mpnet-base-v2` model. Better at matching short informal queries with other old informal queries.

## Determine category

Once a query is received, we look for similar old tickets. When similar tickets are found, we make use of their category tag to predict the category of the current query.
We use the relevance percentage of the old tickets (how sure the model is that the old tickets are similar to the query) to determine the confidence level of the category prediction.
If the confidence level is below a certain threshold, the model does not predict any category.

## Function call

``` python
from retrieve_info import retrieve_relevant_entries

results = retrieve_relevant_entries(query, n_results=5)
# Where "query" is the user's problem and "n_results" the number of matching elements to return from the database
```

## Additional info

* Models load once at the beginning (takes around 15 seconds) and return relevant data for queries within milliseconds.
* A CI test file is available to confirm the DB is working and is loaded with correct data.
* All returned elements should have a similarity score of 0.3 for FAQ and 0.5 for old tickets. This can be modified anytime by modifying the code:

```python
FAQ_SIMILARITY_THRESHOLD      = 0.30
TICKET_SIMILARITY_THRESHOLD   = 0.50
```
