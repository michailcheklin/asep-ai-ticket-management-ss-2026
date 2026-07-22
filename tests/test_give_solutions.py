"""
Unit tests for the give_solutions node.

Mocks the RAG retrieval, the LLM and the Zammad ticket-append call.
Follows the Arrange-Act-Assert pattern used in test_ticket_category.py.

Run from the repo root:
    pytest tests/test_give_solutions.py -v -s
"""

import unittest
from unittest.mock import MagicMock, patch

from langchain_core.messages import HumanMessage

from backend.graph.nodes import give_solutions


def base_state(**overrides) -> dict:
    state = {
        "messages": [HumanMessage(content="Mein WLAN geht nicht")],
        "issue_description": "WLAN funktioniert nicht",
        "additional_info": ["Gebäude SGW"],
        "ticket_id": 42,
    }
    state.update(overrides)
    return state


class GiveSolutionsTests(unittest.TestCase):
    """Unit tests for give_solutions' RAG-to-summary pipeline."""

    @patch("backend.graph.nodes.retrieve_relevant_entries")
    def test_returns_early_message_when_issue_description_empty(self, mock_retrieve):
        # Arrange
        state = base_state(issue_description="")

        # Act
        result = give_solutions(state)

        # Assert
        self.assertEqual(result["solutions"], [])
        self.assertIn("Keine ausreichende Anfrage", result["messages"][0].content)
        mock_retrieve.assert_not_called()

    @patch("backend.graph.nodes.retrieve_relevant_entries")
    def test_returns_error_message_when_rag_raises(self, mock_retrieve):
        # Arrange
        mock_retrieve.side_effect = Exception("Chroma unavailable")

        # Act
        with self.assertLogs("backend.graph.nodes", level="ERROR") as log_cm:
            result = give_solutions(base_state())

        # Assert
        self.assertEqual(result["solutions"], [])
        self.assertIn("Fehler bei der Suche", result["messages"][0].content)
        self.assertTrue(any("RAG retrieval failed" in line for line in log_cm.output))
        self.assertTrue(any("Chroma unavailable" in line for line in log_cm.output))
        self.assertFalse(any("WLAN funktioniert nicht" in line for line in log_cm.output))

    @patch("backend.graph.nodes.ticket_service.append_message_to_ticket")
    @patch("backend.graph.nodes.llm")
    @patch("backend.graph.nodes.retrieve_relevant_entries")
    def test_builds_solutions_from_two_faq_matches(self, mock_retrieve, mock_llm, mock_append):
        # Arrange
        mock_retrieve.return_value = {
            "faq_matches": [
                {"id": "faq-1", "text": "Starte den Router neu."},
                {"id": "faq-2", "text": "Prüfe die eduroam-Zertifikate."},
            ],
            "ticket_matches": [{"category": "Incident", "text": "Altes ähnliches Ticket"}],
        }
        mock_llm.invoke.return_value = MagicMock(content="Zusammenfassung der Lösungen.")

        # Act
        result = give_solutions(base_state())

        # Assert
        self.assertEqual(
            result["solutions"],
            [
                {"title": "FAQ: faq-1", "description": "Starte den Router neu."},
                {"title": "FAQ: faq-2", "description": "Prüfe die eduroam-Zertifikate."},
                {"title": "Ähnliches Ticket (Incident)", "description": "Altes ähnliches Ticket"},
            ],
        )
        self.assertIn("Zusammenfassung der Lösungen.", result["messages"][0].content)
        self.assertIn("Konnte ich dir dabei helfen", result["messages"][0].content)
        mock_append.assert_called_once()

    @patch("backend.graph.nodes.ticket_service.append_message_to_ticket")
    @patch("backend.graph.nodes.llm")
    @patch("backend.graph.nodes.retrieve_relevant_entries")
    def test_fills_up_with_ticket_matches_when_fewer_than_two_faq_matches(
        self, mock_retrieve, mock_llm, mock_append
    ):
        # Arrange
        mock_retrieve.return_value = {
            "faq_matches": [{"id": "faq-1", "text": "Starte den Router neu."}],
            "ticket_matches": [{"category": "Incident", "text": "Altes ähnliches Ticket"}],
        }
        mock_llm.invoke.return_value = MagicMock(content="Zusammenfassung der Lösungen.")

        # Act
        result = give_solutions(base_state())

        # Assert
        self.assertEqual(
            result["solutions"],
            [
                {"title": "FAQ: faq-1", "description": "Starte den Router neu."},
                {"title": "Ähnliches Ticket (Incident)", "description": "Altes ähnliches Ticket"},
            ],
        )

    @patch("backend.graph.nodes.ticket_service.append_message_to_ticket")
    @patch("backend.graph.nodes.llm")
    @patch("backend.graph.nodes.retrieve_relevant_entries")
    def test_appends_summary_to_ticket_with_correct_payload(self, mock_retrieve, mock_llm, mock_append):
        # Arrange
        mock_retrieve.return_value = {
            "faq_matches": [{"id": "faq-1", "text": "Starte den Router neu."}],
            "ticket_matches": [],
        }
        mock_llm.invoke.return_value = MagicMock(content="Zusammenfassung der Lösungen.")

        # Act
        give_solutions(base_state())

        # Assert
        _, kwargs = mock_append.call_args
        self.assertEqual(kwargs["ticket_id"], 42)
        self.assertEqual(kwargs["sender"], "Agent")
        self.assertTrue(kwargs["internal"])
        self.assertIn("Zusammenfassung der Lösungen.", kwargs["body"])

    @patch("backend.graph.nodes.ticket_service.append_message_to_ticket")
    @patch("backend.graph.nodes.llm")
    @patch("backend.graph.nodes.retrieve_relevant_entries")
    def test_continues_when_ticket_append_fails(self, mock_retrieve, mock_llm, mock_append):
        # Arrange
        mock_retrieve.return_value = {
            "faq_matches": [{"id": "faq-1", "text": "Starte den Router neu."}],
            "ticket_matches": [],
        }
        mock_llm.invoke.return_value = MagicMock(content="Zusammenfassung der Lösungen.")
        mock_append.side_effect = Exception("Zammad unavailable")

        # Act
        result = give_solutions(base_state())

        # Assert: no exception propagates, solutions/messages are still returned
        self.assertEqual(len(result["solutions"]), 1)
        self.assertIn("Zusammenfassung der Lösungen.", result["messages"][0].content)


if __name__ == "__main__":
    unittest.main()
