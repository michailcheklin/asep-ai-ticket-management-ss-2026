import requests
from bs4 import BeautifulSoup
import json
import time
import re

"""
This script takes all links from the links.json file and creates a json file with all the problems and solutions from scraped pages.
The output json has the following attributes:
    {
      "id": "Subsubsection title",
      "context": "Section > subsection",
      "problem": "Problem description.",
      "solution": "Solution description.",
      "last_update": "Date, if available",
      "url": "reference to the source of this information"
    }
"""

def load_links(filepath='./faqs.json'):
    """Load links from the properly formatted links.json file"""
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    links = []
    for item in data:
        title = item.get('title', '').strip()
        url   = item.get('url', '').strip()
        if title and url:
            links.append({
                'name': title,
                'url':  url
            })

    print(f"[INFO] Loaded {len(links)} links from {filepath}")
    return links


def get_context_from_page(soup, anchor_id):
    """
    Find the anchor with the given id and walk UP the nested <ul>/<li> tree
    to collect only the actual parent section titles, stopping at the top level.
    """
    target = soup.find('a', attrs={'name': anchor_id})
    if not target:
        return []

    breadcrumbs = []
    current = target.parent  # start at the <li> containing our anchor

    while current:
        # Look for an <a> tag with a <b> inside at this level (section title)
        if current.name == 'li':
            anchor = current.find('a', recursive=False)
            if anchor:
                b_tag = anchor.find('b')
                if b_tag:
                    title = b_tag.get_text(strip=True)
                    if title:
                        breadcrumbs.insert(0, title)
        current = current.parent

    return breadcrumbs


def extract_faq_content(url):
    """Extract problem and solution from a FAQ page"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        result = {
            'title':    None,
            'context':  None,
            'problem':  None,
            'solution': None,
            'updated':  None,
        }

        # ── Extract anchor id from URL ─────────────────────────────────────────
        # e.g. ...faqs.php?id=188#a_188  →  "a_188"
        anchor_match = re.search(r'#(a_\d+)', url)
        anchor_id    = anchor_match.group(1) if anchor_match else None

        # ── Build correct breadcrumb context ──────────────────────────────────
        if anchor_id:
            breadcrumbs = get_context_from_page(soup, anchor_id)

            # Last entry is the entry title itself
            result['title']   = breadcrumbs[-1] if breadcrumbs else None
            # Everything before the last entry is the context path
            result['context'] = ' > '.join(breadcrumbs[:-1]) if len(breadcrumbs) > 1 else None

        # ── FAQ rows ──────────────────────────────────────────────────────────
        rows = soup.find_all('div', class_='mb-3')

        for row in rows:
            if 'row' not in row.get('class', []):
                continue

            label_div   = row.find('div', class_='col-lg-2')
            content_div = row.find('div', class_='col-lg-10')

            if not label_div or not content_div:
                continue

            label   = label_div.get_text(strip=True)
            content = content_div.get_text(strip=True)

            if not label and not content:
                continue

            label_lower = label.lower()

            if 'problem' in label_lower:
                result['problem'] = content
            elif 'lösung' in label_lower:
                result['solution'] = content_div.get_text(separator=' ', strip=True)
            elif 'aktualisiert' in content.lower():
                result['updated'] = content

        return result

    except requests.RequestException as e:
        print(f"  [ERROR] fetching {url}: {e}")
        return None


def build_faq_entry(idx, link, content):
    """
    Build a FAQ entry with flat attributes:
      id          - title of the entry
      context     - parent breadcrumb path (without the entry title)
      problem     - the question/problem statement
      solution    - the answer/solution (including any links as text)
      last_update - when the entry was last updated
      url         - source URL
    """
    return {
        "id":          content['title'] or link['name'],
        "context":     content['context'],
        "problem":     content['problem'],
        "solution":    content['solution'],
        "last_update": content['updated'],
        "url":         link['url'],
    }


def main():
    all_links = load_links('./faqs.json')
    # links = all_links[:15]
    links = all_links

    faq_entries = []
    skipped     = []

    for idx, link in enumerate(links, start=1):
        name = link.get('name', 'Unknown')
        url  = link.get('url', '')

        print(f"\n[{idx:02d}] Processing: {name}")
        print(f"      URL: {url}")

        content = extract_faq_content(url)

        if not content:
            print(f"  [SKIP] Could not fetch content.")
            skipped.append({'idx': idx, 'name': name, 'url': url, 'reason': 'fetch error'})
            continue

        has_problem  = bool(content['problem'])
        has_solution = bool(content['solution'])

        # ── Warnings ──────────────────────────────────────────────────────────
        if has_problem and not has_solution:
            print(f"  [WARNING] Problem found but NO solution!")
        if has_solution and not has_problem:
            print(f"  [WARNING] Solution found but NO problem!")
        if not has_problem and not has_solution:
            print(f"  [INFO] No problem/solution — likely a category heading, skipping.")
            skipped.append({'idx': idx, 'name': name, 'url': url, 'reason': 'no content'})
            continue

        entry = build_faq_entry(idx, link, content)
        faq_entries.append(entry)

        print(f"  ID          : {entry['id']}")
        print(f"  Context     : {entry['context']}")
        print(f"  Problem     : {content['problem'][:80]}..." if content['problem'] else "  Problem     : None")
        print(f"  Solution    : {content['solution'][:80]}..." if content['solution'] else "  Solution    : None")
        print(f"  Last Update : {content['updated']}")

        time.sleep(1)

    # ── Save results ──────────────────────────────────────────────────────────
    output = {
        "faq_entries":   faq_entries,
        "skipped":       skipped,
        "total":         len(faq_entries),
        "total_skipped": len(skipped)
    }

    with open('faq_extracted.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"Done. {len(faq_entries)} entries saved, {len(skipped)} skipped.")
    print(f"Output: faq_extracted_full.json")


if __name__ == "__main__":
    main()