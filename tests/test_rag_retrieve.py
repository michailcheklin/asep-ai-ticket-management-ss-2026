import pytest

from backend.rag.retrieve_info import (
    FAQ_TIER_1_THRESHOLD,
    retrieve_relevant_entries,
)

QUERIES = {
    "vpn": "Wie verbinde ich mich mit dem VPN der Universität?",
    "wlan": "Mein WLAN funktioniert nicht, ich kann mich nicht mit eduroam verbinden.",
    "license": "Wie bekomme ich eine Windows 10 Lizenz?",
    "irrelevant": "Wie buche ich einen Urlaub nach Mallorca?",
}

MATCH_QUERY_KEYS = ["vpn", "wlan", "license"]


def _print_results(key: str, results: dict):
    print(f"\n  Query    : {QUERIES[key]}")

    print(f"\n  FAQ Matches ({len(results['faq_matches'])} returned):")
    for i, match in enumerate(results["faq_matches"], start=1):
        print(f"    [{i}] {match['id']} (similarity={match['similarity']:.4f})")

    print(f"\n  Ticket Matches ({len(results['ticket_matches'])} above threshold):")
    for i, match in enumerate(results["ticket_matches"], start=1):
        print(f"    [{i}] {match['id']} (similarity={match['similarity']:.4f})")


@pytest.fixture(scope="module")
def retrieval_results():
    """Runs retrieve_relevant_entries() once per query and reuses the results across all tests."""
    results = {key: retrieve_relevant_entries(query, n_results=5) for key, query in QUERIES.items()}
    for key, result in results.items():
        _print_results(key, result)
    return results


@pytest.mark.parametrize("key", MATCH_QUERY_KEYS)
def test_faq_match_returned(retrieval_results, key):
    matches = retrieval_results[key]["faq_matches"]
    assert len(matches) > 0, f"no FAQ match returned for query '{QUERIES[key]}'"


@pytest.mark.parametrize("key", MATCH_QUERY_KEYS)
def test_faq_match_reaches_tier_1(retrieval_results, key):
    matches = retrieval_results[key]["faq_matches"]
    best = max((m["similarity"] for m in matches), default=0.0)
    assert best >= FAQ_TIER_1_THRESHOLD, (
        f"best FAQ similarity {best:.4f} for query '{QUERIES[key]}' "
        f"is below tier 1 threshold {FAQ_TIER_1_THRESHOLD}"
    )


@pytest.mark.parametrize("key", MATCH_QUERY_KEYS)
def test_ticket_match_returned(retrieval_results, key):
    # ticket_matches is already filtered to >= TICKET_SIMILARITY_THRESHOLD by retrieve_relevant_entries()
    matches = retrieval_results[key]["ticket_matches"]
    assert len(matches) > 0, f"no ticket match above threshold for query '{QUERIES[key]}'"


def test_irrelevant_query_has_no_strong_faq_match(retrieval_results):
    matches = retrieval_results["irrelevant"]["faq_matches"]
    strong = [m for m in matches if m["similarity"] >= FAQ_TIER_1_THRESHOLD]
    assert not strong, f"unexpected strong FAQ match(es) for irrelevant query: {strong}"


def test_irrelevant_query_has_no_ticket_match(retrieval_results):
    matches = retrieval_results["irrelevant"]["ticket_matches"]
    assert not matches, f"unexpected ticket match(es) for irrelevant query: {matches}"
