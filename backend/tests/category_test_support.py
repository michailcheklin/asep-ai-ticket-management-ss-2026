"""Shared helpers and fixtures for ticket category classification tests."""

import json
import os
import sys
import unittest
from pathlib import Path

from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(_REPO_ROOT / ".env")
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.graph.nodes import TICKET_CATEGORIES, TicketCategoryDecision, classify_ticket_category

OLD_TICKETS_PATH = Path(__file__).resolve().parents[1] / "rag" / "old_tickets.json"
HOLDOUT_TESTS_PATH = Path(__file__).resolve().parents[1] / "rag" / "category_holdout_tests.json"


def cases_from_ticket_entries(entries: list[dict], id_prefix: str) -> list[dict]:
    """Convert JSON ticket entries into normalized live-test case dicts."""
    cases = []
    for index, entry in enumerate(entries):
        ticket = entry["ticket"]
        cases.append({
            "id": f"{id_prefix}_{index}",
            "issue_description": ticket,
            "expected_category": entry.get("expected_category") or entry["category"],
            "user_messages": [ticket],
            "additional_info": entry.get("additional_info", []),
        })
    return cases


def load_regression_cases() -> list[dict]:
    """Build regression cases from rag/old_tickets.json."""
    with OLD_TICKETS_PATH.open(encoding="utf-8") as handle:
        templates = json.load(handle)["TICKET_TEMPLATES"]
    return cases_from_ticket_entries(templates, "old_ticket")


def load_holdout_cases() -> list[dict]:
    """Build holdout cases from rag/category_holdout_tests.json."""
    with HOLDOUT_TESTS_PATH.open(encoding="utf-8") as handle:
        entries = json.load(handle)["HOLDOUT_TESTS"]
    return cases_from_ticket_entries(entries, "holdout")


def regression_limit() -> int | None:
    """Return an optional cap for regression cases from CATEGORY_REGRESSION_LIMIT."""
    raw = os.getenv("CATEGORY_REGRESSION_LIMIT", "").strip()
    if not raw:
        return None
    return max(1, int(raw))


def category_decision(category: str) -> TicketCategoryDecision:
    """Build a mocked TicketCategoryDecision for unit tests."""
    return TicketCategoryDecision(category=category)


def classify_case(case: dict) -> str:
    """Run live classification for a single normalized test case."""
    return classify_ticket_category(
        issue_description=case["issue_description"],
        additional_info=case["additional_info"],
        user_messages=case["user_messages"],
    )


def format_case_failure(case: dict, result: str) -> str:
    """Format one failed live classification for reporting."""
    preview = case["issue_description"][:80].replace("\n", " ")
    return (
        f"{case['id']}: expected '{case['expected_category']}', "
        f"got '{result}' | {preview}..."
    )


def print_case_result(label: str, index: int, total: int, case: dict, result: str) -> None:
    """Print progress for one live classification case."""
    status = "ok" if result == case["expected_category"] else "FAIL"
    print(
        f"[{label}] {index}/{total} {case['id']}: "
        f"expected={case['expected_category']}, got={result} [{status}]",
        flush=True,
    )


def collect_live_failures(cases: list[dict], label: str) -> list[str]:
    """Execute all live cases and return formatted failure messages."""
    failures: list[str] = []
    total = len(cases)
    print(f"\n[{label}] Running {total} live LLM classifications...", flush=True)

    for index, case in enumerate(cases, start=1):
        result = classify_case(case)
        print_case_result(label, index, total, case, result)
        if result != case["expected_category"]:
            failures.append(format_case_failure(case, result))
    return failures


def print_suite_summary(label: str, passed: int, total: int) -> float:
    """Print the accuracy summary and return the accuracy percentage."""
    accuracy = 100 * passed / total if total else 0
    print(f"\n[{label}] {passed}/{total} passed ({accuracy:.1f}% accuracy)")
    return accuracy


def assert_min_accuracy(
    test_case: unittest.TestCase,
    label: str,
    accuracy: float,
    min_accuracy: float,
    failures: list[str],
) -> None:
    """Fail the unittest case when accuracy is below the configured threshold."""
    if accuracy < min_accuracy * 100:
        test_case.fail(
            f"[{label}] Accuracy {accuracy:.1f}% below minimum {min_accuracy * 100:.1f}% "
            f"({len(failures)} case(s) failed):\n" + "\n".join(failures)
        )


def run_live_category_suite(
    test_case: unittest.TestCase,
    *,
    label: str,
    cases: list[dict],
    min_accuracy: float,
) -> None:
    """Run a labeled live LLM classification suite and enforce a minimum accuracy."""
    failures = collect_live_failures(cases, label)
    passed = len(cases) - len(failures)
    accuracy = print_suite_summary(label, passed, len(cases))

    if failures:
        print(f"[{label}] Failures:")
        for line in failures:
            print(f"  - {line}")

    assert_min_accuracy(test_case, label, accuracy, min_accuracy, failures)


def validate_cases(cases: list[dict]) -> None:
    """Assert that loaded cases use known categories and non-empty ticket text."""
    for case in cases:
        if case["expected_category"] not in TICKET_CATEGORIES:
            raise ValueError(f"Unknown category in fixture: {case['expected_category']}")
        if not case["issue_description"].strip():
            raise ValueError(f"Empty ticket text in fixture: {case['id']}")
