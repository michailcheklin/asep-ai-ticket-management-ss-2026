"""
This script reads faq_solution_urls.json, crawls each url and saves the raw content.
"""
import json
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse


def crawl_url(url: str, timeout: int = 10) -> dict:
    """Crawlt eine URL und gibt den bereinigten Text zurück."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; UniDUE-RAG-Bot/1.0)'
        }
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        # Entferne irrelevante Tags
        for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'aside', 'form']):
            tag.decompose()

        # Extrahiere den Haupttext
        text = soup.get_text(separator='\n', strip=True)

        # Mehrfache Leerzeilen entfernen
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        clean_text = '\n'.join(lines)

        return {
            'url': url,
            'domain': urlparse(url).netloc,
            'status': 'success',
            'content': clean_text,
            'content_length': len(clean_text)
        }

    except requests.exceptions.Timeout:
        return {'url': url, 'status': 'error', 'error': 'Timeout', 'content': ''}
    except requests.exceptions.HTTPError as e:
        return {'url': url, 'status': 'error', 'error': f'HTTP {e.response.status_code}', 'content': ''}
    except Exception as e:
        return {'url': url, 'status': 'error', 'error': str(e), 'content': ''}


def main():
    input_filepath = 'faq_solution_urls.json'
    output_filepath = 'faq_crawled_content.json'

    with open(input_filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    crawled_results = []

    for entry in data.get('extracted_urls', []):
        entry_id = entry.get('id', '')
        urls = entry.get('urls', [])

        print(f"\nVerarbeite Eintrag: {entry_id}")

        for url in urls:
            print(f"  Crawle: {url}")
            result = crawl_url(url)
            result['faq_id'] = entry_id
            crawled_results.append(result)

            # Höfliche Pause zwischen Requests
            time.sleep(1)

    # Statistik
    success = [r for r in crawled_results if r['status'] == 'success']
    failed = [r for r in crawled_results if r['status'] == 'error']

    output_data = {
        'crawled_pages': crawled_results,
        'total': len(crawled_results),
        'successful': len(success),
        'failed': len(failed),
        'failed_urls': [{'url': r['url'], 'error': r.get('error')} for r in failed]
    }

    with open(output_filepath, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print(f"\nFertig! Gespeichert in: {output_filepath}")
    print(f"Erfolgreich: {len(success)} | Fehlgeschlagen: {len(failed)}")


if __name__ == "__main__":
    main()