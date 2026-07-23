"""
This script reads faq_solution_urls.json, crawls each url and saves the raw content.
URLs are separated into:
- websites: successfully crawled HTML pages
- skipped: non-HTML files (PDFs, etc.) that are not crawled
- failed: URLs that resulted in an error
"""
import json
import os
import time
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

# Dateitypen, die NICHT gecrawlt werden sollen
SKIP_EXTENSIONS = {
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    '.zip', '.tar', '.gz', '.rar',
    '.exe', '.msi', '.dmg',
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg',
    '.mp3', '.mp4', '.avi', '.mov',
    '.csv', '.xml'
}


def get_url_extension(url: str) -> str:
    """Gibt die Dateiendung einer URL zurück, z.B. '.pdf'"""
    path = urlparse(url).path
    _, ext = os.path.splitext(path)
    return ext.lower()


def is_skippable(url: str) -> bool:
    """Prüft ob die URL eine nicht-crawlbare Datei ist."""
    return get_url_extension(url) in SKIP_EXTENSIONS


def crawl_url(url: str, timeout: int = 10) -> dict:
    """Crawlt eine URL und gibt den bereinigten Text zurück."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; UniDUE-RAG-Bot/1.0)'
        }
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()

        # Prüfe Content-Type aus dem Response-Header
        content_type = response.headers.get('Content-Type', '').lower()
        if 'html' not in content_type:
            # Wurde doch als nicht-HTML erkannt (z.B. falsche Endung in URL)
            ext = get_url_extension(url) or f"({content_type.split('/')[1] if '/' in content_type else 'unknown'})"
            return {
                'status': 'skipped',
                'type': ext
            }

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
        return {'status': 'error', 'error': 'Timeout'}
    except requests.exceptions.HTTPError as e:
        return {'status': 'error', 'error': f'HTTP {e.response.status_code}'}
    except Exception as e:
        return {'status': 'error', 'error': str(e)}


def main():
    input_filepath = 'faq_solution_urls.json'
    output_filepath = 'faq_crawled_content_distinction.json'

    with open(input_filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    websites = {}
    skipped = {}
    failed = {}

    # Zähler für eindeutige Keys
    website_counter = 0
    skipped_counter = 0
    failed_counter = 0

    for entry in data.get('extracted_urls', []):
        entry_id = entry.get('id', '')
        urls = entry.get('urls', [])

        print(f"\nVerarbeite Eintrag: {entry_id}")

        for url in urls:
            ext = get_url_extension(url)

            # --- Skippable: nicht crawlen ---
            if is_skippable(url):
                print(f"  Überspringe [{ext}]: {url}")
                skipped[str(skipped_counter)] = {
                    'url': url,
                    'faq_id': entry_id,
                    'type': ext
                }
                skipped_counter += 1
                continue

            # --- Crawlen ---
            print(f"  Crawle: {url}")
            result = crawl_url(url)
            result['faq_id'] = entry_id

            if result['status'] == 'success':
                websites[str(website_counter)] = result
                website_counter += 1

            elif result['status'] == 'skipped':
                # Wurde beim Crawlen als non-HTML erkannt
                skipped[str(skipped_counter)] = {
                    'url': url,
                    'faq_id': entry_id,
                    'type': result.get('type', ext if ext else 'unknown')
                }
                skipped_counter += 1

            elif result['status'] == 'error':
                failed[str(failed_counter)] = {
                    'url': url,
                    'faq_id': entry_id,
                    'type': ext if ext else 'unknown',
                    'error': result.get('error', '')
                }
                failed_counter += 1

            time.sleep(1)

    output_data = {
        'websites': websites,
        'skipped': skipped,
        'failed': failed
    }

    with open(output_filepath, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print(f"\nFertig! Gespeichert in: {output_filepath}")
    print(f"Websites (gecrawlt): {len(websites)}")
    print(f"Übersprungen:        {len(skipped)}")
    print(f"Fehlgeschlagen:      {len(failed)}")


if __name__ == "__main__":
    main()