"""
This script reads faq_extracted.json and stores each url that is part of the field 'solution' inside an own json file.
"""
import json
import re


def extract_urls_from_json(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Regex pattern for URLs (http:// and https://)
    url_pattern = re.compile(
        r'https?://'  # http:// or https://
        r'[^\s$$\}\'"<>]+'  # everything except whitespace and certain special chars
        r'(?<![.,;:])'  # no trailing punctuation
    )

    results = []

    # Iterate over all FAQ entries
    for entry in data.get('faq_entries', []):
        if not isinstance(entry, dict):
            continue

        solution = entry.get('solution', '')
        entry_id = entry.get('id', '')

        # Find URLs in the solution field
        found_urls = url_pattern.findall(solution)

        if found_urls:
            results.append({
                'id': entry_id,
                'urls': found_urls
            })

    return results


def main():
    input_filepath = 'faq_extracted.json'  # Path to JSON input file
    output_filepath = 'faq_solution_urls.json'  # Path to JSON output file

    results = extract_urls_from_json(input_filepath)

    # Save results to JSON file
    output_data = {
        'extracted_urls': results,
        'total_entries_with_urls': len(results),
        'total_urls': sum(len(r['urls']) for r in results)
    }

    with open(output_filepath, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print(f"Done! Results saved to: {output_filepath}")
    print(f"Entries with URLs: {output_data['total_entries_with_urls']}")
    print(f"Total URLs: {output_data['total_urls']}")


if __name__ == "__main__":
    main()
