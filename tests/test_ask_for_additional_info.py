"""
Unit tests for the ask_for_additional_info node.

Mocks the RAG retrieval, the LLM and the Zammad ticket-append call.
Follows the Arrange-Act-Assert pattern used in test_ticket_category.py.

Run from the repo root:
    pytest tests/test_ask_for_additional_info.py -v -s
"""

import unittest
from unittest.mock import patch

from langchain_core.messages import HumanMessage

from backend.graph.models.AdditionalInfoDecision import AdditionalInfoDecision
from backend.graph.nodes import ask_for_additional_info


def additional_info_decision(needs_additional_info: bool, follow_up_question: str = "") -> AdditionalInfoDecision:
    """Build a mocked AdditionalInfoDecision for unit tests."""
    return AdditionalInfoDecision(
        needs_additional_info=needs_additional_info,
        follow_up_question=follow_up_question,
    )


def base_state(**overrides) -> dict:
    state = {
        "messages": [HumanMessage(content="Mein WLAN geht nicht")],
        "issue_description": "WLAN funktioniert nicht",
        "additional_info": [],
        "additional_info_attempts": 0,
        "ticket_id": 42,
    }
    state.update(overrides)
    return state


class AskForAdditionalInfoTests(unittest.TestCase):
    """Unit tests for ask_for_additional_info's RAG-gated follow-up logic."""

    @patch("backend.graph.nodes.llm")
    @patch("backend.graph.nodes.retrieve_relevant_entries")
    def test_skips_follow_up_when_rag_has_no_matches(self, mock_retrieve, mock_llm):
        # Arrange
        mock_retrieve.return_value = {"faq_matches": [], "ticket_matches": []}

        # Act
        result = ask_for_additional_info(base_state())

        # Assert
        self.assertEqual(result, {"needs_additional_info": True})
        mock_llm.with_structured_output.return_value.invoke.assert_not_called()

    @patch("backend.graph.nodes.ticket_service.append_message_to_ticket")
    @patch("backend.graph.nodes.llm")
    @patch("backend.graph.nodes.retrieve_relevant_entries")
    def test_marks_complete_when_two_additional_infos_already_collected(
        self, mock_retrieve, mock_llm, mock_append
    ):
        # Arrange
        mock_retrieve.return_value = {
            "faq_matches": [{"text": "FAQ Eintrag"}],
            "ticket_matches": [],
        }
        mock_llm.with_structured_output.return_value.invoke.return_value = additional_info_decision(
            False, "Bist du im Uni-Netzwerk?"
        )
        state = base_state(additional_info=["Gebäude SGW", "eduroam"])

        # Act
        result = ask_for_additional_info(state)

        # Assert
        self.assertEqual(result, {"needs_additional_info": True})
        mock_append.assert_not_called()

    @patch("backend.graph.nodes.ticket_service.append_message_to_ticket")
    @patch("backend.graph.nodes.llm")
    @patch("backend.graph.nodes.retrieve_relevant_entries")
    def test_marks_complete_after_max_attempts(self, mock_retrieve, mock_llm, mock_append):
        # Arrange
        mock_retrieve.return_value = {
            "faq_matches": [{"text": "FAQ Eintrag"}],
            "ticket_matches": [],
        }
        mock_llm.with_structured_output.return_value.invoke.return_value = additional_info_decision(
            False, "Bist du im Uni-Netzwerk?"
        )
        state = base_state(additional_info_attempts=3)

        # Act
        result = ask_for_additional_info(state)

        # Assert
        self.assertEqual(result, {"needs_additional_info": True})
        mock_append.assert_not_called()

    @patch("backend.graph.nodes.ticket_service.append_message_to_ticket")
    @patch("backend.graph.nodes.llm")
    @patch("backend.graph.nodes.retrieve_relevant_entries")
    def test_marks_complete_when_llm_decides_no_more_info_needed(
        self, mock_retrieve, mock_llm, mock_append
    ):
        # Arrange
        mock_retrieve.return_value = {
            "faq_matches": [{"text": "FAQ Eintrag"}],
            "ticket_matches": [],
        }
        mock_llm.with_structured_output.return_value.invoke.return_value = additional_info_decision(True)

        # Act
        result = ask_for_additional_info(base_state())

        # Assert
        self.assertEqual(result, {"needs_additional_info": True})
        mock_append.assert_not_called()

    @patch("backend.graph.nodes.ticket_service.append_message_to_ticket")
    @patch("backend.graph.nodes.llm")
    @patch("backend.graph.nodes.retrieve_relevant_entries")
    def test_asks_follow_up_question_and_appends_to_ticket(
        self, mock_retrieve, mock_llm, mock_append
    ):
        # Arrange
        mock_retrieve.return_value = {
            "faq_matches": [{"text": "FAQ Eintrag"}],
            "ticket_matches": [],
        }
        mock_llm.with_structured_output.return_value.invoke.return_value = additional_info_decision(
            False, "Bist du im Uni-Netzwerk?"
        )
        state = base_state(additional_info=["Gebäude SGW"], additional_info_attempts=1)

        # Act
        result = ask_for_additional_info(state)

        # Assert
        self.assertEqual(result["needs_additional_info"], False)
        self.assertEqual(result["additional_info_attempts"], 2)
        self.assertIn("Bist du im Uni-Netzwerk?", result["messages"][0].content)
        mock_append.assert_called_once()
        _, kwargs = mock_append.call_args
        self.assertEqual(kwargs["ticket_id"], 42)
        self.assertEqual(kwargs["sender"], "Agent")
        self.assertTrue(kwargs["internal"])
        self.assertIn("Bist du im Uni-Netzwerk?", kwargs["body"])


if __name__ == "__main__":
    unittest.main()
