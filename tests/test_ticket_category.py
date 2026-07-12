"""
Unit tests for LLM-based ticket category classification.

Mocks the LLM by default. Live suites live in test_ticket_category_live.py.

Run from the repo root:
    pytest tests/test_ticket_category.py -v -s

Live LLM tests:
    RUN_LLM_CATEGORY_TESTS=1 pytest tests/test_ticket_category_live.py -v -s

Optional thresholds:
    CATEGORY_REGRESSION_MIN_ACCURACY=0.90
    CATEGORY_HOLDOUT_MIN_ACCURACY=0.80
"""

import unittest
from unittest.mock import patch

from langchain_core.messages import HumanMessage

from tests.category_test_support import (
    category_decision,
    load_holdout_cases,
    load_regression_cases,
    validate_cases,
)
from backend.graph.models.TicketCategoryDecision import TICKET_CATEGORIES
from backend.graph.nodes import (
    classify_ticket,
    classify_ticket_category,
    extract_information,
    finish_ticket,
    _resolve_ticket_category,
)


class ClassifyTicketCategoryTests(unittest.TestCase):
    """Unit tests for classify_ticket_category prompt and fallback behavior."""

    @patch("backend.graph.nodes.category_llm")
    def test_returns_valid_category_from_llm(self, mock_category_llm):
        mock_category_llm.invoke.return_value = category_decision("Incident")

        result = classify_ticket_category(
            issue_description="WLAN funktioniert nicht",
            additional_info=["Gebäude SGW", "eduroam"],
            user_messages=["Mein WLAN geht nicht", "Ich bin im Gebäude SGW"],
        )

        self.assertEqual(result, "Incident")
        mock_category_llm.invoke.assert_called_once()

    @patch("backend.graph.nodes.category_llm")
    def test_falls_back_when_llm_returns_unknown_category(self, mock_category_llm):
        mock_category_llm.invoke.return_value = category_decision("Netzwerk")

        result = classify_ticket_category(
            issue_description="VPN Verbindung bricht ab",
            additional_info=[],
            user_messages=["VPN geht nicht"],
        )

        self.assertEqual(result, "Service Request")

    @patch("backend.graph.nodes.category_llm")
    def test_prompt_includes_full_conversation_context(self, mock_category_llm):
        mock_category_llm.invoke.return_value = category_decision("Incident")

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

    @patch("backend.graph.nodes.category_llm")
    def test_moodle_login_classified_as_incident(self, mock_category_llm):
        mock_category_llm.invoke.return_value = category_decision("Incident")

        result = classify_ticket_category(
            issue_description="Falsche Credentials angezeigt",
            additional_info=["Moodle", "Windows Rechner", "gleiche Fehlermeldung"],
            user_messages=["Ich kann mich nicht in Moodle einloggen, falsche Credentials angezeigt"],
        )

        self.assertEqual(result, "Incident")

    @patch("backend.graph.nodes.category_llm")
    def test_wlan_classified_as_incident(self, mock_category_llm):
        mock_category_llm.invoke.return_value = category_decision("Incident")

        result = classify_ticket_category(
            issue_description="WLAN funktioniert nicht",
            additional_info=["Gebäude S-GW", "Essen", "Windows Rechner"],
            user_messages=["Wlan funktioniert nicht"],
        )

        self.assertEqual(result, "Incident")


class ExtractInformationTests(unittest.TestCase):
    """Unit tests ensuring extraction does not perform category classification."""

    @patch("backend.graph.nodes.structured_llm")
    def test_extract_information_does_not_set_category(self, mock_structured_llm):
        from backend.graph.models.ExtractedTicketData import ExtractedTicketData

        mock_structured_llm.invoke.return_value = ExtractedTicketData(
            problem="WLAN Problem",
            priority=0,
        )

        state_update = extract_information({
            "messages": [HumanMessage(content="WLAN geht nicht")],
            "issue_description": "",
            "additional_info": [],
            "user_email": "test@example.com",
        })

        self.assertEqual(state_update.get("issue_description"), "WLAN Problem")
        self.assertNotIn("category", state_update)

    @patch("backend.graph.nodes.structured_llm")
    def test_extract_prompt_does_not_include_category_rules(self, mock_structured_llm):
        from backend.graph.models.ExtractedTicketData import ExtractedTicketData

        mock_structured_llm.invoke.return_value = ExtractedTicketData()

        extract_information({
            "messages": [HumanMessage(content="WLAN geht nicht")],
            "issue_description": "",
            "additional_info": [],
        })

        system_prompt = mock_structured_llm.invoke.call_args[0][0][0].content
        self.assertNotIn("4. Kategorie", system_prompt)
        self.assertNotIn("ITSM-Ticket-Typ", system_prompt)


class ClassifyTicketNodeTests(unittest.TestCase):
    """Unit tests for classify_ticket workflow node and finish_ticket reuse."""

    @patch("backend.graph.nodes.classify_ticket_category")
    def test_classify_ticket_node_sets_category(self, mock_classify):
        mock_classify.return_value = "Incident"

        state_update = classify_ticket({
            "messages": [HumanMessage(content="Mein WLAN geht nicht")],
            "issue_description": "WLAN funktioniert nicht",
            "additional_info": ["Gebäude SGW"],
            "category": "",
        })

        self.assertEqual(state_update["category"], "Incident")
        mock_classify.assert_called_once()

    @patch("backend.graph.nodes.classify_ticket_category")
    def test_resolve_ticket_category_reuses_existing_value(self, mock_classify):
        category = _resolve_ticket_category({
            "messages": [],
            "issue_description": "WLAN funktioniert nicht",
            "additional_info": [],
            "category": "Incident",
        })

        self.assertEqual(category, "Incident")
        mock_classify.assert_not_called()

    @patch("backend.graph.nodes.classify_ticket_category")
    @patch("backend.graph.nodes.ticket_service.create_support_ticket")
    def test_finish_ticket_reuses_category_without_reclassifying(
        self,
        mock_create_ticket,
        mock_classify,
    ):
        mock_create_ticket.return_value = {
            "messages": [],
            "is_complete": True,
        }

        result = finish_ticket({
            "messages": [HumanMessage(content="WLAN geht nicht")],
            "user_email": "user@mail.com",
            "matrikelnummer": "1234567",
            "issue_description": "WLAN funktioniert nicht",
            "additional_info": [],
            "priority": 0,
            "category": "Incident",
        })

        mock_classify.assert_not_called()
        mock_create_ticket.assert_called_once()
        self.assertEqual(result["category"], "Incident")
        self.assertEqual(
            mock_create_ticket.call_args[0][0]["category"],
            "Incident",
        )


class TicketCategoryConstantsTests(unittest.TestCase):
    """Fixture and taxonomy sanity checks without calling the LLM."""

    def test_expected_categories_are_defined(self):
        self.assertEqual(
            TICKET_CATEGORIES,
            [
                "Incident",
                "Service Request",
                "Change",
                "Problem",
                "Complaint",
            ],
        )

    def test_regression_fixtures_load_from_old_tickets(self):
        cases = load_regression_cases()
        self.assertEqual(len(cases), 56)
        validate_cases(cases)

    def test_holdout_fixtures_load(self):
        cases = load_holdout_cases()
        self.assertGreaterEqual(len(cases), 5)
        validate_cases(cases)


if __name__ == "__main__":
    unittest.main()
