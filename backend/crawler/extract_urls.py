"""
This script reads faq_extracted.json and stores each url that is part of the field 'solution' inside an own json file.
"""
import json
import re


def extract_urls_from_json(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Regex-Pattern für URLs (http:// und https://)
    url_pattern = re.compile(
        r'https?://'  # http:// oder https://
        r'[^\s$$\}\'"<>]+'  # alles außer Whitespace und bestimmten Sonderzeichen
        r'(?<![.,;:])'  # kein Satzzeichen am Ende
    )

    results = []

    # Durch alle FAQ-Einträge iterieren
    for entry in data.get('faq_entries', []):
        if not isinstance(entry, dict):
            continue

        solution = entry.get('solution', '')
        entry_id = entry.get('id', '')

        # URLs im solution-Feld suchen
        found_urls = url_pattern.findall(solution)

        if found_urls:
            results.append({
                'id': entry_id,
                'urls': found_urls
            })

    return results


def main():
    input_filepath = 'faq_extracted.json'  # Pfad zur JSON-Eingabedatei
    output_filepath = 'faq_solution_urls.json'  # Pfad zur JSON-Ausgabedatei

    results = extract_urls_from_json(input_filepath)

    # Ergebnisse in JSON-Datei speichern
    output_data = {
        'extracted_urls': results,
        'total_entries_with_urls': len(results),
        'total_urls': sum(len(r['urls']) for r in results)
    }

    with open(output_filepath, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print(f"Fertig! Ergebnisse gespeichert in: {output_filepath}")
    print(f"Einträge mit URLs: {output_data['total_entries_with_urls']}")
    print(f"URLs gesamt: {output_data['total_urls']}")


if __name__ == "__main__":
    main()