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
