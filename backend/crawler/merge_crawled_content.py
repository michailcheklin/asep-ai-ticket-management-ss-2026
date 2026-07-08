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
