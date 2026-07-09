# Crawler info

## `alllevel.py`

Takes the base URL of the ZIM's FAQ page and scrapes all the links from that page then writes them in `faqs.json`

## `crawl_faq`

Uses the links from `faqs.json` to crawl the pages for FAQ problems and solutions.

It creates a json file with all the problems and solutions from scraped pages and writes them in `faq_extracted_full.json` with the following attributes:

```json
    {
      "id": "Subsubsection title",
      "context": "Section > subsection",
      "problem": "Problem description.",
      "solution": "Solution description.",
      "last_update": "Date, if available",
      "url": "reference to the source of this information"
    }
```

PS. Some links in `faqs.json` do not lead to a page with problems/solutions, rather to the (sub)section title. Those are logged separately in the `faq_extracted_full.json` file and were manually removed to create `faq_extracted.json` which is the json fed into the DB. The manual work was simply selecting the attribute "skipped" from the json and removing it.

## extract_urls.py

Since there are urls inside the content header of each faq entry, we need to crawl each url if possible and store its data inside our VectorDB.   
Only then, we are able to enrich our chatbot knowledge base.

This script reads faq_extracted.json and extracts the field `id` with associated urls from `solution`field.   
It will be stored in `faq_solution_urls.json`.   

JSON FORMAT
```
{
  "extracted_urls": [
    {
      "id": "Beitritt zur Domäne",
      "urls": [
        "http://www.uni-due.de/imperia/md/content/zim/services/benutzerverwaltung/antrag_ou.pdf"
      ]
    },
    ....
  ],
  "total_entries_with_urls": 192,
  "total_urls": 296
}
```


## generate_none_url_notes.py

For every `extracted_urls` entry in `../rag/faq_extracted_with_crawled_content.json` with
`status == "none"` (URLs pointing to non-HTML files like PDFs, which couldn't be crawled as
text), this script asks the LLM to write a single German sentence describing the file type
and its purpose, using the surrounding FAQ entry's `problem`/`faq_content` as context. The
result is written back into that URL entry as a new `"note"` field, which
`backend/rag/retrieve_info.py` reads at runtime (no LLM calls happen there).

One-off script, run manually after re-crawling or when new `status == "none"` URLs appear:
```
cd backend/crawler && python3 generate_none_url_notes.py
```

## crawl_urls_distinction.py

This script reads `faq_solution_urls.json` which contains all urls that were inside the solution field of the FAQ.  
Then, it crawls through each website, following these rules:  

RULES:
```
READ URL
    │
    ▼
Ending in SKIP_EXTENSIONS?
    ├── YES  → skipped  (kein Request)
    └── NO → crawlen
                │
                ├── Content-Type != HTML? → skipped
                ├── status = success      → websites
                └── status = error        → failed
```