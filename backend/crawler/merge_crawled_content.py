"""
Reads faq_extracted.json and faq_crawled_content_distinction.json and merges them:
each entry's 'solution' string is replaced by an array with one tuple containing the
original text ('faq_content') plus the crawled content of every url found in it
('extracted_urls'). Writes the result to faq_extracted_with_crawled_content.json.
"""
import json
import re
from collections import defaultdict
from urllib.parse import urlparse

URL_PATTERN = re.compile(
    r'https?://'
    r'[^\s$$\}\'"<>]+'
    r'(?<![.,;:])'
)


def build_url_lookup(distinction_data):
    """
    Builds the lookup for each URL to unify all URLs that were crawled,
    no matter if there was an HTML file, another file or an error,
    by putting the data into a unified format:
    "url": "https://example.com/file.pdf"
    "domain": "example.com"
    "status": "none"
    "content": None,
    "content_length": None,
    "type": ".pdf",
    "error": None
    :param distinction_data: The input data that is split into 3 categories: HTML, non-HTML, inaccessible
    :return: The unified data
    """
    lookup = defaultdict(list)

    for record in distinction_data.get('websites', {}).values():
        lookup[(record['faq_id'], record['url'])].append({
            'url': record['url'],
            'domain': record.get('domain') or urlparse(record['url']).netloc,
            'status': 'success',
            'content': record.get('content'),
            'content_length': record.get('content_length'),
            'type': None,
            'error': None,
        })

    for record in distinction_data.get('skipped', {}).values():
        lookup[(record['faq_id'], record['url'])].append({
            'url': record['url'],
            'domain': urlparse(record['url']).netloc,
            'status': 'none',
            'content': None,
            'content_length': None,
            'type': record.get('type'),
            'error': None,
        })

    for record in distinction_data.get('failed', {}).values():
        lookup[(record['faq_id'], record['url'])].append({
            'url': record['url'],
            'domain': urlparse(record['url']).netloc,
            'status': 'error',
            'content': None,
            'content_length': None,
            'type': record.get('type'),
            'error': record.get('error'),
        })

    return lookup


def build_extracted_urls(entry_id, solution_text, lookup, unmatched_counter):
    """
    Finds all URLs in a FAQ entry
    :param entry_id: The ID of the entry
    :param solution_text: The text of the FAQ entry's solution
    :param lookup: The unified crawling data that was built with the method
    build_url_lookup
    :param unmatched_counter: Conter to keep track of how often
    a URL was not matched in the already crawled URLs
    :return: All extracted URLs
    """
    urls = URL_PATTERN.findall(solution_text)
    extracted = []

    for url in urls:
        candidates = lookup.get((entry_id, url))
        if candidates:
            extracted.append(candidates.pop(0))
        else:
            unmatched_counter[0] += 1
            extracted.append({
                'url': url,
                'domain': urlparse(url).netloc,
                'status': 'none',
                'content': None,
                'content_length': None,
                'type': None,
                'error': 'no matching crawl record found',
            })

    return extracted


def main():
    """
    Starts the merging of the crawled content. This code is run only from
    the console or an IDE, not in Docker.
    """
    input_filepath = 'faq_extracted.json'
    distinction_filepath = 'faq_crawled_content_distinction.json'
    output_filepath = 'faq_extracted_with_crawled_content.json'

    with open(input_filepath, 'r', encoding='utf-8') as f:
        faq_data = json.load(f)

    with open(distinction_filepath, 'r', encoding='utf-8') as f:
        distinction_data = json.load(f)

    lookup = build_url_lookup(distinction_data)

    total_urls = 0
    unmatched_counter = [0]

    for entry in faq_data.get('faq_entries', []):
        solution_text = entry.get('solution', '')
        entry_id = entry.get('id', '')

        extracted_urls = build_extracted_urls(entry_id, solution_text, lookup, unmatched_counter)
        total_urls += len(extracted_urls)

        entry['solution'] = [{
            'faq_content': solution_text,
            'extracted_urls': extracted_urls,
        }]

    with open(output_filepath, 'w', encoding='utf-8') as f:
        json.dump(faq_data, f, ensure_ascii=False, indent=2)

    print(f"Fertig! Gespeichert in: {output_filepath}")
    print(f"FAQ-Einträge verarbeitet: {len(faq_data.get('faq_entries', []))}")
    print(f"URLs gesamt: {total_urls}")
    print(f"URLs ohne passenden Crawl-Eintrag: {unmatched_counter[0]}")


if __name__ == "__main__":
    main()
