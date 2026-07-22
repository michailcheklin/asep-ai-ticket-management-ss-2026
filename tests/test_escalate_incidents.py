"""
Unit tests for the escalate_incidents node.

Mocks ProblemService so no real RAG/Zammad calls occur.

Run from the repo root:
    pytest tests/test_escalate_incidents.py -v -s
"""

import unittest
from unittest.mock import patch

from backend.graph.nodes import escalate_incidents


class EscalateIncidentsTests(unittest.TestCase):
    """Control-flow and fallback tests for escalate_incidents."""

    def test_returns_empty_when_category_is_not_incident(self):
        result = escalate_incidents({
            "category": "Service Request",
            "ticket_id": 42,
            "issue_description": "WLAN",
            "additional_info": [],
        })
        self.assertEqual(result, {})

    def test_returns_empty_when_ticket_id_missing_or_invalid(self):
        self.assertEqual(
            escalate_incidents({
                "category": "Incident",
                "ticket_id": None,
                "issue_description": "WLAN",
                "additional_info": [],
            }),
            {},
        )
        self.assertEqual(
            escalate_incidents({
                "category": "Incident",
                "ticket_id": -1,
                "issue_description": "WLAN",
                "additional_info": [],
            }),
            {},
        )

    @patch("backend.graph.nodes.problem_service.register_and_check_incident")
    def test_returns_empty_after_successful_escalation_check(self, mock_register):
        mock_register.return_value = {
            "escalated": True,
            "problem_id": 99,
            "created": True,
        }

        result = escalate_incidents({
            "category": "Incident",
            "ticket_id": 42,
            "issue_description": "WLAN down",
            "additional_info": ["Gebäude LF"],
        })

        self.assertEqual(result, {})
        mock_register.assert_called_once_with(
            ticket_id=42,
            issue_description="WLAN down",
            additional_info=["Gebäude LF"],
        )

    @patch("backend.graph.nodes.problem_service.register_and_check_incident")
    def test_swallows_exception_and_returns_empty(self, mock_register):
        mock_register.side_effect = RuntimeError("RAG unavailable")

        with self.assertLogs("backend.graph.nodes", level="ERROR") as log_cm:
            result = escalate_incidents({
                "category": "Incident",
                "ticket_id": 42,
                "issue_description": "WLAN down",
                "additional_info": [],
            })

        self.assertEqual(result, {})
        mock_register.assert_called_once()
        self.assertTrue(any("failed for ticket 42" in line for line in log_cm.output))
        self.assertTrue(any("RAG unavailable" in line for line in log_cm.output))

    @patch("backend.graph.nodes.problem_service.register_and_check_incident")
    def test_logs_escalation_outcome_without_user_text(self, mock_register):
        mock_register.return_value = {
            "escalated": True,
            "problem_id": 99,
            "created": True,
        }

        with self.assertLogs("backend.graph.nodes", level="INFO") as log_cm:
            escalate_incidents({
                "category": "Incident",
                "ticket_id": 42,
                "issue_description": "sensitive user problem text",
                "additional_info": ["Gebäude LF"],
            })

        joined = "\n".join(log_cm.output)
        self.assertIn("ticket 42", joined)
        self.assertIn("escalated=True", joined)
        self.assertNotIn("sensitive user problem text", joined)


if __name__ == "__main__":
    unittest.main()
