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

from backend.graph.models.ExtractedTicketData import ExtractedTicketData
from backend.graph.models.TicketCategoryDecision import TICKET_CATEGORIES
from backend.graph.nodes import (
    _resolve_ticket_category,
    classify_ticket,
    classify_ticket_category,
    extract_information,
    finish_ai_created_ticket,
)
from tests.category_test_support import (
    category_decision,
    load_holdout_cases,
    load_regression_cases,
    validate_cases,
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
    def test_prompt_includes_summary_context(self, mock_category_llm):
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
    """Unit tests for extract_information state mapping and ticket side effects."""

    @patch("backend.graph.nodes.structured_llm")
    def test_extract_information_does_not_set_category(self, mock_structured_llm):
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
        mock_structured_llm.invoke.return_value = ExtractedTicketData()

        extract_information({
            "messages": [HumanMessage(content="WLAN geht nicht")],
            "issue_description": "",
            "additional_info": [],
        })

        system_prompt = mock_structured_llm.invoke.call_args[0][0][0].content
        self.assertNotIn("4. Kategorie", system_prompt)
        self.assertNotIn("ITSM-Ticket-Typ", system_prompt)

    @patch("backend.graph.nodes.ticket_service.update_ticket_title_from_state")
    @patch("backend.graph.nodes.ticket_service.append_message_to_ticket")
    @patch("backend.graph.nodes.structured_llm")
    def test_maps_fields_only_when_missing_in_state(
        self,
        mock_structured_llm,
        mock_append,
        mock_update_title,
    ):
        mock_structured_llm.invoke.return_value = ExtractedTicketData(
            student_id="7654321",
            problem="Neues Problem",
            priority=1,
            additional_info=["eduroam"],
            summary="Kurzfassung",
        )

        state_update = extract_information({
            "messages": [HumanMessage(content="Mein WLAN geht nicht")],
            "user_email": "alt@example.com",
            "student_id": "1234567",
            "issue_description": "Bestehendes Problem",
            "additional_info": ["Gebäude SGW"],
            "priority": 1,
            "summary": "alt",
            "ticket_id": 42,
        })

        self.assertNotIn("user_email", state_update)
        self.assertNotIn("student_id", state_update)
        self.assertNotIn("issue_description", state_update)
        self.assertNotIn("priority", state_update)
        self.assertEqual(state_update["additional_info"], ["eduroam"])
        self.assertEqual(state_update["summary"], "Kurzfassung")

    @patch("backend.graph.nodes.ticket_service.update_ticket_title_from_state")
    @patch("backend.graph.nodes.ticket_service.append_message_to_ticket")
    @patch("backend.graph.nodes.structured_llm")
    def test_priority_zero_in_state_is_treated_as_unset(
        self,
        mock_structured_llm,
        mock_append,
        mock_update_title,
    ):
        """Document current behavior: priority 0 is falsy, so a new priority is applied."""
        mock_structured_llm.invoke.return_value = ExtractedTicketData(
            priority=1,
            summary="Kurzfassung",
        )

        state_update = extract_information({
            "messages": [HumanMessage(content="Dringend")],
            "user_email": "user@mail.com",
            "priority": 0,
            "additional_info": [],
            "ticket_id": 42,
        })

        self.assertEqual(state_update["priority"], 1)

    @patch("backend.graph.nodes.structured_llm")
    def test_skips_duplicate_additional_info(self, mock_structured_llm):
        mock_structured_llm.invoke.return_value = ExtractedTicketData(
            additional_info=["Gebäude SGW", "eduroam"],
            summary="Kurzfassung",
        )

        state_update = extract_information({
            "messages": [HumanMessage(content="Noch Infos")],
            "additional_info": ["Gebäude SGW"],
            "user_email": "test@example.com",
            "ticket_id": None,
        })

        self.assertEqual(state_update["additional_info"], ["eduroam"])

    @patch("backend.graph.nodes.add_tag_to_ticket")
    @patch("backend.graph.nodes.create_ticket_by_user_email")
    @patch("backend.graph.nodes.structured_llm")
    def test_creates_ticket_when_problem_extracted_and_no_ticket_id(
        self,
        mock_structured_llm,
        mock_create_ticket,
        mock_add_tag,
    ):
        mock_structured_llm.invoke.return_value = ExtractedTicketData(
            problem="WLAN funktioniert nicht",
            student_id="1234567",
            priority=1,
            summary="Kurzfassung",
        )
        mock_create_ticket.return_value = 99

        state_update = extract_information({
            "messages": [HumanMessage(content="WLAN geht nicht")],
            "user_email": "user@mail.com",
            "priority": 0,
            "additional_info": [],
            "category": "Incident",
        })

        self.assertEqual(state_update["ticket_id"], 99)
        mock_create_ticket.assert_called_once_with(
            email="user@mail.com",
            title="[1234567] WLAN funktioniert nicht",
            body="WLAN geht nicht",
            priority=1,
            internal=True,
            state="new",
            category="Incident",
        )
        mock_add_tag.assert_called_once_with(99, "AI-Created")

    @patch("backend.graph.nodes.ticket_service.update_ticket_title_from_state")
    @patch("backend.graph.nodes.ticket_service.append_message_to_ticket")
    @patch("backend.graph.nodes.create_ticket_by_user_email")
    @patch("backend.graph.nodes.structured_llm")
    def test_appends_to_existing_ticket_instead_of_creating(
        self,
        mock_structured_llm,
        mock_create_ticket,
        mock_append,
        mock_update_title,
    ):
        mock_structured_llm.invoke.return_value = ExtractedTicketData(
            problem="Präzisierung",
            additional_info=["MacBook"],
            summary="Kurzfassung",
        )

        state_update = extract_information({
            "messages": [HumanMessage(content="Es ist ein MacBook")],
            "user_email": "user@mail.com",
            "issue_description": "WLAN Problem",
            "additional_info": [],
            "ticket_id": 42,
            "priority": 0,
        })

        mock_create_ticket.assert_not_called()
        mock_append.assert_called_once_with(42, "Es ist ein MacBook", sender="Customer")
        mock_update_title.assert_called_once()
        merged_state = mock_update_title.call_args[0][0]
        self.assertEqual(merged_state["issue_description"], "Präzisierung")
        self.assertEqual(mock_update_title.call_args[0][1], 42)
        self.assertNotIn("ticket_id", state_update)

    @patch("backend.graph.nodes.create_ticket_by_user_email")
    @patch("backend.graph.nodes.structured_llm")
    def test_does_not_create_ticket_without_problem(self, mock_structured_llm, mock_create_ticket):
        mock_structured_llm.invoke.return_value = ExtractedTicketData(
            summary="Nur Hallo",
        )

        state_update = extract_information({
            "messages": [HumanMessage(content="Hallo")],
            "user_email": "user@mail.com",
            "priority": 0,
            "additional_info": [],
        })

        mock_create_ticket.assert_not_called()
        self.assertNotIn("ticket_id", state_update)
        self.assertEqual(state_update["summary"], "Nur Hallo")


class ClassifyTicketNodeTests(unittest.TestCase):
    """Unit tests for classify_ticket workflow node and finish_ai_created_ticket reuse."""

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
    @patch("backend.graph.nodes.ticket_service.finalize_ticket_metadata")
    def test_finish_ai_created_ticket_reuses_category_without_reclassifying(
            self,
            mock_finalize,
            mock_classify,
    ):

        with self.assertLogs("Langgraph", level="ERROR") as log_cm:
            result = finish_ai_created_ticket({
                "messages": [HumanMessage(content="WLAN geht nicht")],
                "user_email": "user@mail.com",
                "student_id": "1234567",
                "issue_description": "WLAN funktioniert nicht",
                "additional_info": [],
                "priority": 0,
                "category": "Incident",
                "ticket_id": 55,
            })

        mock_classify.assert_not_called()
        mock_finalize.assert_called_once()

        self.assertEqual(result["category"], "Incident")
        self.assertEqual(
            mock_finalize.call_args[0][0]["category"],
            "Incident",
        )
        self.assertTrue(
            any("Could not read bot message to append to ticket 55" in line for line in log_cm.output)
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
