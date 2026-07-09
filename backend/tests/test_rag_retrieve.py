import sys
from pathlib import Path

RAG_ROOT = Path(__file__).resolve().parents[1] / "rag"
if str(RAG_ROOT) not in sys.path:
    sys.path.insert(0, str(RAG_ROOT))

from retrieve_info import retrieve_relevant_entries

# --- FAQ tiered thresholds (must match retrieve_info.py) ---
FAQ_TIER_1_THRESHOLD = 0.40
FAQ_TIER_2_THRESHOLD = 0.20
FAQ_TIER_3_THRESHOLD = 0.15

# --- CI threshold for ticket matches ---
CI_TICKET_THRESHOLD = 0.35


def print_results(results: dict, query: str):
    """Pretty-print retrieval results for a query"""
    print(f"\n  Query    : {query}")

    print(f"\n  FAQ Matches ({len(results['faq_matches'])} returned):")
    if results["faq_matches"]:
        for i, match in enumerate(results["faq_matches"], start=1):
            fid, problem, solution, extracted_urls, similarity = match
            print(f"    [{i}] {fid}")
            print(f"         Similarity : {similarity:.4f}")
            print(f"         Solution   : {solution[:150]}...")
    else:
        print("    None.")

    print(f"\n  Ticket Matches ({len(results['ticket_matches'])} above threshold):")
    if results["ticket_matches"]:
        for i, match in enumerate(results["ticket_matches"], start=1):
            print(f"    [{i}] {match['id']}")
            print(f"         Similarity : {match['similarity']:.4f}")
            print(f"         Text       : {match['text'][:150]}...")
    else:
        print("    None.")


def check(label: str, condition: bool, detail: str):
    """Print a single named check result"""
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {label}: {detail}")
    return condition


def best_faq_detail(matches: list) -> str:
    if matches:
        return f"best={matches[0][4]:.4f} ('{matches[0][0]}')"
    return "no matches returned"


def best_ticket_detail(matches: list, above: list) -> str:
    if above:
        return f"best={above[0]['similarity']:.4f} ('{above[0]['id']}')"
    if matches:
        return f"best={matches[0]['similarity']:.4f} ('{matches[0]['id']}') — below threshold"
    return "no matches returned"


def run_tests() -> bool:
    all_passed  = True
    test_results = []  # collect per-test summary for CI

    # ── Test 1: VPN query ─────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("Test 1: VPN-Verbindung")
    print(f"{'='*60}")

    vpn_query   = "Wie verbinde ich mich mit dem VPN der Universität?"
    vpn_results = retrieve_relevant_entries(vpn_query, n_results=5)
    print_results(vpn_results, vpn_query)

    vpn_ticket_above = [
        m for m in vpn_results["ticket_matches"]
        if m["similarity"] >= CI_TICKET_THRESHOLD
    ]

    print("\n  Checks:")
    t1_faq = check(
        "FAQ-Treffer zurückgegeben (beliebige Stufe)",
        len(vpn_results["faq_matches"]) > 0,
        best_faq_detail(vpn_results["faq_matches"])
    )
    t1_faq_strong = check(
        f"FAQ-Treffer >= Stufe 1 ({FAQ_TIER_1_THRESHOLD})",
        any(m[4] >= FAQ_TIER_1_THRESHOLD for m in vpn_results["faq_matches"]),
        best_faq_detail(vpn_results["faq_matches"])
    )
    t1_ticket = check(
        f"Ticket-Treffer >= {CI_TICKET_THRESHOLD}",
        len(vpn_ticket_above) > 0,
        best_ticket_detail(vpn_results["ticket_matches"], vpn_ticket_above)
    )
    t1_passed = t1_faq and t1_faq_strong and t1_ticket
    all_passed = all_passed and t1_passed
    test_results.append({
        "name":   "VPN-Verbindung",
        "passed": t1_passed,
        "checks": [
            ("FAQ beliebige Stufe",              t1_faq),
            (f"FAQ Stufe 1 >= {FAQ_TIER_1_THRESHOLD}", t1_faq_strong),
            (f"Ticket >= {CI_TICKET_THRESHOLD}", t1_ticket),
        ]
    })

    # ── Test 2: WLAN query ────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("Test 2: WLAN-Verbindungsprobleme")
    print(f"{'='*60}")

    wlan_query   = "Mein WLAN funktioniert nicht, ich kann mich nicht mit eduroam verbinden."
    wlan_results = retrieve_relevant_entries(wlan_query, n_results=5)
    print_results(wlan_results, wlan_query)

    wlan_ticket_above = [
        m for m in wlan_results["ticket_matches"]
        if m["similarity"] >= CI_TICKET_THRESHOLD
    ]

    print("\n  Checks:")
    t2_faq = check(
        "FAQ-Treffer zurückgegeben (beliebige Stufe)",
        len(wlan_results["faq_matches"]) > 0,
        best_faq_detail(wlan_results["faq_matches"])
    )
    t2_faq_strong = check(
        f"FAQ-Treffer >= Stufe 1 ({FAQ_TIER_1_THRESHOLD})",
        any(m[4] >= FAQ_TIER_1_THRESHOLD for m in wlan_results["faq_matches"]),
        best_faq_detail(wlan_results["faq_matches"])
    )
    t2_ticket = check(
        f"Ticket-Treffer >= {CI_TICKET_THRESHOLD}",
        len(wlan_ticket_above) > 0,
        best_ticket_detail(wlan_results["ticket_matches"], wlan_ticket_above)
    )
    t2_passed = t2_faq and t2_faq_strong and t2_ticket
    all_passed = all_passed and t2_passed
    test_results.append({
        "name":   "WLAN-Verbindungsprobleme",
        "passed": t2_passed,
        "checks": [
            ("FAQ beliebige Stufe",                    t2_faq),
            (f"FAQ Stufe 1 >= {FAQ_TIER_1_THRESHOLD}", t2_faq_strong),
            (f"Ticket >= {CI_TICKET_THRESHOLD}",       t2_ticket),
        ]
    })

    # ── Test 3: Software-Lizenz query ─────────────────────────────────────────
    print(f"\n{'='*60}")
    print("Test 3: Windows Lizenz")
    print(f"{'='*60}")

    sw_query   = "Wie bekomme ich eine Windows 10 Lizenz?"
    sw_results = retrieve_relevant_entries(sw_query, n_results=5)
    print_results(sw_results, sw_query)

    sw_ticket_above = [
        m for m in sw_results["ticket_matches"]
        if m["similarity"] >= CI_TICKET_THRESHOLD
    ]

    print("\n  Checks:")
    t3_faq = check(
        "FAQ-Treffer zurückgegeben (beliebige Stufe)",
        len(sw_results["faq_matches"]) > 0,
        best_faq_detail(sw_results["faq_matches"])
    )
    t3_faq_strong = check(
        f"FAQ-Treffer >= Stufe 1 ({FAQ_TIER_1_THRESHOLD})",
        any(m[4] >= FAQ_TIER_1_THRESHOLD for m in sw_results["faq_matches"]),
        best_faq_detail(sw_results["faq_matches"])
    )
    t3_ticket = check(
        f"Ticket-Treffer >= {CI_TICKET_THRESHOLD}",
        len(sw_ticket_above) > 0,
        best_ticket_detail(sw_results["ticket_matches"], sw_ticket_above)
    )
    t3_passed = t3_faq and t3_faq_strong and t3_ticket
    all_passed = all_passed and t3_passed
    test_results.append({
        "name":   "Software-Lizenz",
        "passed": t3_passed,
        "checks": [
            ("FAQ beliebige Stufe",                    t3_faq),
            (f"FAQ Stufe 1 >= {FAQ_TIER_1_THRESHOLD}", t3_faq_strong),
            (f"Ticket >= {CI_TICKET_THRESHOLD}",       t3_ticket),
        ]
    })

    # ── Test 4: Irrelevant query — expect no strong matches ───────────────────
    print(f"\n{'='*60}")
    print("Test 4: Irrelevante Anfrage — keine starken Treffer erwartet")
    print(f"{'='*60}")

    irr_query   = "Wie buche ich einen Urlaub nach Mallorca?"
    irr_results = retrieve_relevant_entries(irr_query, n_results=5)
    print_results(irr_results, irr_query)

    irr_faq_strong = [
        m for m in irr_results["faq_matches"]
        if m[4] >= FAQ_TIER_1_THRESHOLD
    ]
    irr_ticket_above = [
        m for m in irr_results["ticket_matches"]
        if m["similarity"] >= CI_TICKET_THRESHOLD
    ]

    print("\n  Checks:")
    t4_faq = check(
        f"Keine starken FAQ-Treffer >= Stufe 1 ({FAQ_TIER_1_THRESHOLD})",
        len(irr_faq_strong) == 0,
        best_faq_detail(irr_results["faq_matches"]) if irr_results["faq_matches"] else "keine Treffer — korrekt"
    )
    t4_ticket = check(
        f"Keine Ticket-Treffer >= {CI_TICKET_THRESHOLD}",
        len(irr_ticket_above) == 0,
        best_ticket_detail(irr_results["ticket_matches"], irr_ticket_above)
    )
    t4_passed = t4_faq and t4_ticket
    all_passed = all_passed and t4_passed
    test_results.append({
        "name":   "Irrelevante Anfrage",
        "passed": t4_passed,
        "checks": [
            (f"Keine FAQ >= {FAQ_TIER_1_THRESHOLD}",   t4_faq),
            (f"Keine Tickets >= {CI_TICKET_THRESHOLD}", t4_ticket),
        ]
    })

    # ── Summary ───────────────────────────────────────────────────────────────
    passed_count = sum(1 for t in test_results if t["passed"])
    failed_count = len(test_results) - passed_count
    total_checks = sum(len(t["checks"]) for t in test_results)
    passed_checks = sum(
        sum(1 for _, result in t["checks"] if result)
        for t in test_results
    )

    print(f"\n{'='*60}")
    print("TESTERGEBNIS — ZUSAMMENFASSUNG")
    print(f"{'='*60}")
    print(f"  Tests gesamt   : {len(test_results)}")
    print(f"  Tests bestanden: {passed_count}")
    print(f"  Tests fehlgesch: {failed_count}")
    print(f"  Checks gesamt  : {total_checks}")
    print(f"  Checks best.   : {passed_checks}")
    print(f"  Checks fehlg.  : {total_checks - passed_checks}")
    print(f"\n  Details:")
    for t in test_results:
        status = "PASS" if t["passed"] else "FAIL"
        print(f"\n  [{status}] {t['name']}")
        for label, result in t["checks"]:
            check_status = "PASS" if result else "FAIL"
            print(f"         [{check_status}] {label}")

    print(f"\n{'='*60}")
    if all_passed:
        print("CI ERGEBNIS: ERFOLG — alle Tests bestanden.")
    else:
        print("CI ERGEBNIS: FEHLSCHLAG — ein oder mehrere Tests fehlgeschlagen.")
    print(f"{'='*60}\n")

    return all_passed


if __name__ == "__main__":
    passed = run_tests()
    sys.exit(0 if passed else 1)