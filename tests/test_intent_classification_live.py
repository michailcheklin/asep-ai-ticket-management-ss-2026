"""Live LLM tests for intent classification (tutorial / problem / unclear).

Run from the repo root:
    RUN_LLM_INTENT_TESTS=1 PYTHONPATH=. pytest tests/test_intent_classification_live.py -v -s
"""

import os
import unittest

from langchain_core.messages import HumanMessage

from backend.graph.nodes import classify_intent


def classify(message: str, previous_intent: str = "") -> str:
    result = classify_intent({
        "messages": [HumanMessage(content=message)],
        "intent": previous_intent,
        "user_email": "test@web.de",
    })
    return result["intent"]


@unittest.skipUnless(
    os.getenv("RUN_LLM_INTENT_TESTS") == "1",
    "Set RUN_LLM_INTENT_TESTS=1 to run live LLM integration tests",
)
class LiveIntentClassificationTests(unittest.TestCase):
    """Spot checks against the real LLM for the tutorial/problem/unclear split."""

    def test_bare_problem_statement_is_unclear(self):
        self.assertEqual(classify("Ich habe ein Problem mit dem WLAN."), "unclear")

    def test_problem_statement_with_solution_request_is_tutorial(self):
        self.assertEqual(
            classify("Ich habe ein Problem mit dem WLAN. Was kann ich tun?"),
            "tutorial",
        )

    def test_how_to_question_is_tutorial(self):
        self.assertEqual(classify("Wie richte ich eduroam ein?"), "tutorial")

    def test_explicit_ticket_request_is_problem(self):
        self.assertEqual(classify("Erstellt mir bitte ein Ticket."), "problem")

    def test_explicit_human_support_request_is_problem(self):
        self.assertEqual(
            classify("Ich will mit einem Mitarbeiter sprechen."), "problem"
        )

    def test_pure_infrastructure_outage_is_problem(self):
        self.assertEqual(
            classify("WLAN in Raum R14 ist komplett ausgefallen."), "problem"
        )


if __name__ == "__main__":
    unittest.main()
