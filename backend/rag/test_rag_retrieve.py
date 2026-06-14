import sys
from retrieve_info import retrieve_relevant_entries

CI_SIMILARITY_THRESHOLD = 0.60


def print_results(results: dict, query: str):
    """Pretty-print retrieval results for a query"""
    print(f"\n  Query    : {query}")

    print(f"\n  FAQ Matches ({len(results['faq_matches'])} above threshold):")
    if results["faq_matches"]:
        for i, match in enumerate(results["faq_matches"], start=1):
            print(f"    [{i}] {match['id']}")
            print(f"         Similarity : {match['similarity']:.4f}")
            print(f"         Text       : {match['text'][:150]}...")
    else:
        print("    None.")

    print(f"\n  Ticket Matches ({len(results['ticket_matches'])} above threshold):")
    if results["ticket_matches"]:
        for i, match in enumerate(results["ticket_matches"], start=1):
            print(f"    [{i}] {match['id']}")
            print(f"         Similarity : {match['similarity']:.4f}")
            print(f"         Category   : {match['category']}")
            print(f"         Text       : {match['text'][:150]}...")
    else:
        print("    None.")

    print(f"\n  Inferred Category : {results['inferred']['category']}")
    print(f"  Confidence        : {results['inferred']['confidence']:.4f}")


def check(label: str, condition: bool, detail: str):
    """Print a single named check result"""
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {label}: {detail}")
    return condition


def best_faq_detail(matches: list, above: list) -> str:
    """Return a human-readable string for the best FAQ match"""
    if above:
        return f"best={above[0]['similarity']:.4f} ('{above[0]['id']}')"
    if matches:
        return f"best={matches[0]['similarity']:.4f} ('{matches[0]['id']}') — below threshold"
    return "no matches returned"


def best_ticket_detail(matches: list, above: list) -> str:
    """Return a human-readable string for the best ticket match"""
    if above:
        return f"best={above[0]['similarity']:.4f} ('{above[0]['id']}')"
    if matches:
        return f"best={matches[0]['similarity']:.4f} ('{matches[0]['id']}') — below threshold"
    return "no matches returned"


def run_tests() -> bool:
    all_passed = True

    # ── Test 1: VPN query ─────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("Test 1: VPN connectivity query")
    print(f"{'='*60}")

    vpn_query   = "How to connect to the VPN using Forcepoint?"
    vpn_results = retrieve_relevant_entries(vpn_query, n_results=5)

    vpn_faq_above    = [m for m in vpn_results["faq_matches"]    if m["similarity"] >= CI_SIMILARITY_THRESHOLD]
    vpn_ticket_above = [m for m in vpn_results["ticket_matches"] if m["similarity"] >= CI_SIMILARITY_THRESHOLD]

    print("\n  Checks:")
    t1_faq = check(
        "FAQ match >= 0.60",
        len(vpn_faq_above) > 0,
        best_faq_detail(vpn_results["faq_matches"], vpn_faq_above)
    )
    t1_ticket = check(
        "Ticket match >= 0.60",
        len(vpn_ticket_above) > 0,
        best_ticket_detail(vpn_results["ticket_matches"], vpn_ticket_above)
    )
    all_passed = all_passed and t1_faq and t1_ticket

    # ── Test 2: Software licence query ────────────────────────────────────────
    print(f"\n{'='*60}")
    print("Test 2: Software licence query — expected category: Allgemeine Anfrage")
    print(f"{'='*60}")

    sw_query   = "where can I get a licence for software from the university"
    sw_results = retrieve_relevant_entries(sw_query, n_results=5)

    expected_category = "Allgemeine Anfrage"
    inferred_category = sw_results["inferred"]["category"]
    confidence        = sw_results["inferred"]["confidence"]

    print("\n  Checks:")
    t2_category = check(
        f"Inferred category == '{expected_category}'",
        inferred_category == expected_category,
        f"got '{inferred_category}' with confidence {confidence:.4f}"
    )
    all_passed = all_passed and t2_category

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    if all_passed:
        print("CI RESULT: SUCCESS — all tests passed.")
    else:
        print("CI RESULT: FAILURE — one or more tests failed. See above.")
    print(f"{'='*60}\n")

    return all_passed


if __name__ == "__main__":
    passed = run_tests()
    sys.exit(0 if passed else 1)