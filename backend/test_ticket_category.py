"""
Tests for LLM-based ticket category classification.

Unit tests mock the LLM and run without Ollama/SAIA.
Optional integration tests call the real model when RUN_LLM_CATEGORY_TESTS=1.

Run from backend/:
    python test_ticket_category.py

Live LLM integration tests:
    # Bash / Linux / macOS
    RUN_LLM_CATEGORY_TESTS=1 python test_ticket_category.py

    # PowerShell
    $env:RUN_LLM_CATEGORY_TESTS="1"; python test_ticket_category.py

Regression suite (training-like tickets from rag/old_tickets.json):
    $env:RUN_LLM_CATEGORY_TESTS="1"; python test_ticket_category.py

Holdout suite (unseen tickets from rag/category_holdout_tests.json):
    $env:RUN_LLM_CATEGORY_TESTS="1"; python test_ticket_category.py

    # Optional thresholds
    $env:CATEGORY_REGRESSION_MIN_ACCURACY="0.90"
    $env:CATEGORY_HOLDOUT_MIN_ACCURACY="0.80"
"""

import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from langchain_core.messages import HumanMessage

from nodes import (
    TICKET_CATEGORIES,
    TicketCategoryDecision,
    classify_ticket,
    classify_ticket_category,
    extract_information,
    finish_ticket,
    _resolve_ticket_category,
)

OLD_TICKETS_PATH = Path(__file__).resolve().parent / "rag" / "old_tickets.json"
HOLDOUT_TESTS_PATH = Path(__file__).resolve().parent / "rag" / "category_holdout_tests.json"


def _cases_from_ticket_entries(entries: list[dict], id_prefix: str) -> list[dict]:
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
    return _cases_from_ticket_entries(templates, "old_ticket")


def load_holdout_cases() -> list[dict]:
    """Build holdout cases from rag/category_holdout_tests.json."""
    with HOLDOUT_TESTS_PATH.open(encoding="utf-8") as handle:
        entries = json.load(handle)["HOLDOUT_TESTS"]
    return _cases_from_ticket_entries(entries, "holdout")


def _regression_limit() -> int | None:
    raw = os.getenv("CATEGORY_REGRESSION_LIMIT", "").strip()
    if not raw:
        return None
    return max(1, int(raw))


def _category_decision(category: str) -> TicketCategoryDecision:
    return TicketCategoryDecision(category=category)


def _run_live_category_suite(
    test_case: unittest.TestCase,
    *,
    label: str,
    cases: list[dict],
    min_accuracy: float,
) -> None:
    failures: list[str] = []
    total = len(cases)

    print(f"\n[{label}] Running {total} live LLM classifications...", flush=True)

    for index, case in enumerate(cases, start=1):
        with test_case.subTest(case_id=case["id"], expected=case["expected_category"]):
            result = classify_ticket_category(
                issue_description=case["issue_description"],
                additional_info=case["additional_info"],
                user_messages=case["user_messages"],
            )
            status = "ok" if result == case["expected_category"] else "FAIL"
            print(
                f"[{label}] {index}/{total} {case['id']}: "
                f"expected={case['expected_category']}, got={result} [{status}]",
                flush=True,
            )
            if result != case["expected_category"]:
                preview = case["issue_description"][:80].replace("\n", " ")
                failures.append(
                    f"{case['id']}: expected '{case['expected_category']}', "
                    f"got '{result}' | {preview}..."
                )

    passed = total - len(failures)
    accuracy = 100 * passed / total if total else 0
    print(f"\n[{label}] {passed}/{total} passed ({accuracy:.1f}% accuracy)")
    if failures:
        print(f"[{label}] Failures:")
        for line in failures:
            print(f"  - {line}")

    if accuracy < min_accuracy * 100:
        test_case.fail(
            f"[{label}] Accuracy {accuracy:.1f}% below minimum {min_accuracy * 100:.1f}% "
            f"({len(failures)} case(s) failed):\n" + "\n".join(failures)
        )


class ClassifyTicketCategoryTests(unittest.TestCase):
  @patch("nodes.category_llm")
  def test_returns_valid_category_from_llm(self, mock_category_llm):
    mock_category_llm.invoke.return_value = _category_decision("Technisches Problem")

    result = classify_ticket_category(
      issue_description="WLAN funktioniert nicht",
      additional_info=["Gebäude SGW", "eduroam"],
      user_messages=["Mein WLAN geht nicht", "Ich bin im Gebäude SGW"],
    )

    self.assertEqual(result, "Technisches Problem")
    mock_category_llm.invoke.assert_called_once()

  @patch("nodes.category_llm")
  def test_falls_back_when_llm_returns_unknown_category(self, mock_category_llm):
    mock_category_llm.invoke.return_value = _category_decision("Netzwerk")

    result = classify_ticket_category(
      issue_description="VPN Verbindung bricht ab",
      additional_info=[],
      user_messages=["VPN geht nicht"],
    )

    self.assertEqual(result, "Allgemeine Anfrage")

  @patch("nodes.category_llm")
  def test_prompt_includes_full_conversation_context(self, mock_category_llm):
    mock_category_llm.invoke.return_value = _category_decision("Zugang/Login")

    classify_ticket_category(
      issue_description="Falsche Credentials angezeigt",
      additional_info=["Moodle", "Windows Rechner"],
      user_messages=[
        "Mein WLAN geht nicht",
        "Es geht um Moodle, falsche Credentials werden angezeigt",
      ],
    )

    prompt = mock_category_llm.invoke.call_args[0][0][0].content
    self.assertIn("Mein WLAN geht nicht", prompt)
    self.assertIn("Moodle, falsche Credentials", prompt)
    self.assertIn("Falsche Credentials angezeigt", prompt)
    self.assertIn("Moodle", prompt)

  @patch("nodes.category_llm")
  def test_moodle_credentials_classified_as_zugang_login(self, mock_category_llm):
    mock_category_llm.invoke.return_value = _category_decision("Zugang/Login")

    result = classify_ticket_category(
      issue_description="Falsche Credentials angezeigt",
      additional_info=["Moodle", "Windows Rechner", "gleiche Fehlermeldung"],
      user_messages=["Ich kann mich nicht in Moodle einloggen, falsche Credentials angezeigt"],
    )

    self.assertEqual(result, "Zugang/Login")

  @patch("nodes.category_llm")
  def test_wlan_classified_as_technisches_problem(self, mock_category_llm):
    mock_category_llm.invoke.return_value = _category_decision("Technisches Problem")

    result = classify_ticket_category(
      issue_description="WLAN funktioniert nicht",
      additional_info=["Gebäude S-GW", "Essen", "Windows Rechner"],
      user_messages=["Wlan funktioniert nicht"],
    )

    self.assertEqual(result, "Technisches Problem")


class ExtractInformationTests(unittest.TestCase):
  @patch("nodes.structured_llm")
  def test_extract_information_does_not_set_category(self, mock_structured_llm):
    from nodes import ExtractedTicketData

    mock_structured_llm.invoke.return_value = ExtractedTicketData(
      problem="WLAN Problem",
      priority=0,
    )

    state_update = extract_information({
      "messages": [HumanMessage(content="WLAN geht nicht")],
      "issue_description": "",
      "additional_info": [],
    })

    self.assertEqual(state_update.get("issue_description"), "WLAN Problem")
    self.assertNotIn("category", state_update)

  @patch("nodes.structured_llm")
  def test_extract_prompt_does_not_include_category_rules(self, mock_structured_llm):
    from nodes import ExtractedTicketData

    mock_structured_llm.invoke.return_value = ExtractedTicketData()

    extract_information({
      "messages": [HumanMessage(content="WLAN geht nicht")],
      "issue_description": "",
      "additional_info": [],
    })

    system_prompt = mock_structured_llm.invoke.call_args[0][0][0].content
    self.assertNotIn("4. Kategorie", system_prompt)
    self.assertNotIn("Klassifiziere nach Hauptabsicht", system_prompt)


class ClassifyTicketNodeTests(unittest.TestCase):
  @patch("nodes.classify_ticket_category")
  def test_classify_ticket_node_sets_category(self, mock_classify):
    mock_classify.return_value = "Technisches Problem"

    state_update = classify_ticket({
      "messages": [HumanMessage(content="Mein WLAN geht nicht")],
      "issue_description": "WLAN funktioniert nicht",
      "additional_info": ["Gebäude SGW"],
      "category": "",
    })

    self.assertEqual(state_update["category"], "Technisches Problem")
    mock_classify.assert_called_once()

  @patch("nodes.classify_ticket_category")
  def test_resolve_ticket_category_reuses_existing_value(self, mock_classify):
    category = _resolve_ticket_category({
      "messages": [],
      "issue_description": "WLAN funktioniert nicht",
      "additional_info": [],
      "category": "Technisches Problem",
    })

    self.assertEqual(category, "Technisches Problem")
    mock_classify.assert_not_called()

  @patch("nodes.classify_ticket_category")
  @patch("nodes.llm")
  @patch("nodes.create_ticket_by_user_email")
  def test_finish_ticket_reuses_category_without_reclassifying(
    self,
    mock_create_ticket,
    mock_llm,
    mock_classify,
  ):
    mock_llm.invoke.return_value.content = "WLAN Problem"
    mock_create_ticket.return_value = None

    finish_ticket({
      "messages": [HumanMessage(content="WLAN geht nicht")],
      "user_email": "user@mail.com",
      "matrikelnummer": "1234567",
      "issue_description": "WLAN funktioniert nicht",
      "additional_info": [],
      "priority": 0,
      "category": "Technisches Problem",
    })

    mock_classify.assert_not_called()
    mock_create_ticket.assert_called_once()


class TicketCategoryConstantsTests(unittest.TestCase):
  def test_expected_categories_are_defined(self):
    self.assertEqual(
      TICKET_CATEGORIES,
      [
        "Zugang/Login",
        "Technisches Problem",
        "Allgemeine Anfrage",
        "Beschwerde",
        "Rechnung",
      ],
    )

  def test_regression_fixtures_load_from_old_tickets(self):
    cases = load_regression_cases()
    self.assertEqual(len(cases), 50)
    for case in cases:
      self.assertIn(case["expected_category"], TICKET_CATEGORIES)
      self.assertTrue(case["issue_description"].strip())

  def test_holdout_fixtures_load(self):
    cases = load_holdout_cases()
    self.assertGreaterEqual(len(cases), 5)
    for case in cases:
      self.assertIn(case["expected_category"], TICKET_CATEGORIES)
      self.assertTrue(case["issue_description"].strip())


@unittest.skipUnless(
  os.getenv("RUN_LLM_CATEGORY_TESTS") == "1",
  "Set RUN_LLM_CATEGORY_TESTS=1 to run live LLM integration tests",
)
class LiveCategoryClassificationTests(unittest.TestCase):
  def test_live_wlan_is_technisches_problem(self):
    result = classify_ticket_category(
      issue_description="WLAN funktioniert nicht",
      additional_info=["Gebäude SGW", "Essen"],
      user_messages=["Mein Wlan funktioniert nicht im Gebäude SGW"],
    )
    self.assertEqual(result, "Technisches Problem")

  def test_live_moodle_login_is_zugang_login(self):
    result = classify_ticket_category(
      issue_description="Falsche Credentials angezeigt",
      additional_info=["Moodle", "Windows Rechner"],
      user_messages=["Ich kann mich nicht in Moodle einloggen, falsche Credentials angezeigt"],
    )
    self.assertEqual(result, "Zugang/Login")

  def test_live_login_without_keywords_is_zugang_login(self):
    result = classify_ticket_category(
      issue_description="Kein Zugang mehr zur Abgabe nach erneutem Einloggen",
      additional_info=[],
      user_messages=[
        "Ich wurde beim Einloggen rausgeworfen und komme nicht mehr in meine Abgabe rein.",
      ],
    )
    self.assertEqual(result, "Zugang/Login")


@unittest.skipUnless(
  os.getenv("RUN_LLM_CATEGORY_TESTS") == "1",
  "Set RUN_LLM_CATEGORY_TESTS=1 to run live LLM regression tests",
)
class LiveCategoryRegressionTests(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    cls.cases = load_regression_cases()
    limit = _regression_limit()
    if limit is not None:
      cls.cases = cls.cases[:limit]

  def test_regression_cases_from_old_tickets(self):
    min_accuracy = float(os.getenv("CATEGORY_REGRESSION_MIN_ACCURACY", "0.90"))
    _run_live_category_suite(
        self,
        label="REGRESSION",
        cases=self.cases,
        min_accuracy=min_accuracy,
    )


@unittest.skipUnless(
  os.getenv("RUN_LLM_CATEGORY_TESTS") == "1",
  "Set RUN_LLM_CATEGORY_TESTS=1 to run live LLM holdout tests",
)
class LiveCategoryHoldoutTests(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    cls.cases = load_holdout_cases()

  def test_holdout_cases_generalization(self):
    min_accuracy = float(os.getenv("CATEGORY_HOLDOUT_MIN_ACCURACY", "0.80"))
    _run_live_category_suite(
        self,
        label="HOLDOUT",
        cases=self.cases,
        min_accuracy=min_accuracy,
    )


def run_tests():
  loader = unittest.TestLoader()
  suite = unittest.TestSuite()
  suite.addTests(loader.loadTestsFromModule(__import__(__name__)))
  runner = unittest.TextTestRunner(verbosity=2)
  result = runner.run(suite)
  return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
  raise SystemExit(run_tests())
