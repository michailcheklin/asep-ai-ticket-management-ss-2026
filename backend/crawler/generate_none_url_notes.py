"""
One-off precompute script: for every extracted_urls entry in
faq_extracted_with_crawled_content.json with status == "none" (i.e. URLs
that could not be crawled because they point to a non-HTML file such as a
PDF), ask the LLM to write a single German sentence describing the file
type and its purpose, using the surrounding FAQ entry's problem/faq_content
as context. The result is written back into the entry as a new "note" field.

Usage: python3 generate_none_url_notes.py
(run from backend/crawler/, with a .env at the repo root providing AGENT /
USE_SAIA_API / SAIA_API_KEY or OLLAMA_BASE_URL, since it imports the shared
LLM wrapper from backend.llm.llm)
"""
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from langchain_core.messages import SystemMessage

from backend.llm.llm import llm

FAQ_SOURCE_PATH = Path(__file__).resolve().parents[1] / "rag" / "faq_extracted_with_crawled_content.json"


def build_prompt(problem: str, faq_content: str, url: str, url_type: str) -> str:
    """
    Builds the prompt to send to the LLM that generates an explanation of a non-HTML file
    :param problem: The problem that the question in the FAQ addresses
    :param faq_content: The answer of the FAQ
    :param url: The URL of the non-HTML file
    :param url_type: The type of the non-HTML file (PDF, EXE, ...)
    :return: The prompt to send to the LLM for explaining what a non-HTML is for
    """
    return f"""Du bekommst einen FAQ-Eintrag eines Uni-IT-Supports sowie eine darin verlinkte URL,
die nicht automatisch als Text gelesen werden konnte (z.B. weil es sich um eine PDF- oder
andere Nicht-HTML-Datei handelt).

FAQ-PROBLEM: {problem}
FAQ-LÖSUNGSTEXT: {faq_content}
URL: {url}
DATEITYP: {url_type or "unbekannt"}

Schreibe GENAU EINEN deutschen Satz, der den Dateityp und den vermuteten Nutzen dieser
Datei im Kontext des FAQ-Eintrags beschreibt. Orientiere dich am folgenden Stil:
"Die URL ist eine .pdf, welche als Anleitung für die Beantragung einer Organisationseinheit dient."

Gib NUR den einen Satz zurück, ohne Anführungszeichen, ohne Erklärung, ohne Aufzählung."""


def generate_note(problem: str, faq_content: str, url: str, url_type: str) -> str:
    """
    Sends the prompt built in the method build_prompt to the LLM
    that generates an explanation of a non-HTML file
    :param problem: The problem that the question in the FAQ addresses
    :param faq_content: The answer of the FAQ
    :param url: The URL of the non-HTML file
    :param url_type: The type of the non-HTML file (PDF, EXE, ...)
    :return: The explanation of the non-HTML file that the LLM generated
    """
    prompt = build_prompt(problem, faq_content, url, url_type)
    response = llm.invoke([SystemMessage(content=prompt)])
    return response.content.strip()


def main():
    """
    Generates explanations for each non-HTML file supplied in the file the
    variable FAQ_SOURCE_PATH points to. This script runs only from the console
    or from an IDE, not inside Docker.
    """
    with open(FAQ_SOURCE_PATH, "r", encoding="utf-8") as f:
        faq_data = json.load(f)

    entries = faq_data["faq_entries"]
    total = 0
    generated = 0

    for entry in entries:
        solution = entry.get("solution") or [{}]
        problem = entry.get("problem", "")
        faq_content = solution[0].get("faq_content", "")
        extracted_urls = solution[0].get("extracted_urls", [])

        for url_entry in extracted_urls:
            if url_entry.get("status") != "none":
                continue
            total += 1
            note = generate_note(
                problem=problem,
                faq_content=faq_content,
                url=url_entry.get("url", ""),
                url_type=url_entry.get("type"),
            )
            url_entry["note"] = note
            generated += 1
            print(f"[{generated}/?] {entry['id']} -> {url_entry.get('url')}\n    {note}")

    with open(FAQ_SOURCE_PATH, "w", encoding="utf-8") as f:
        json.dump(faq_data, f, ensure_ascii=False, indent=2)

    print(f"\nFertig! {generated}/{total} Notes generiert und in {FAQ_SOURCE_PATH.name} gespeichert.")


if __name__ == "__main__":
    main()
