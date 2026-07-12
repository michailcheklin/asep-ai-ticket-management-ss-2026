"""
Unit tests for LLM-based intent classification.

Mocks the LLM by default, mirroring test_ticket_category.py.
Tests the fallback logic, prompt construction and e-mail extraction of
classify_intent — not the LLM's actual accuracy.

Run from backend/:
    python -m unittest tests.test_intent_classification
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from langchain_core.messages import HumanMessage

from backend.graph.nodes import INTENTS, classify_intent
from backend.graph.models.IntentDecision import IntentDecision


def intent_decision(intent: str, reason: str = "") -> IntentDecision:
    """Build a mocked IntentDecision for unit tests."""
    return IntentDecision(intent=intent, reason=reason)


class ClassifyIntentTests(unittest.TestCase):
    """Unit tests for classify_intent prompt, fallback and email extraction."""

    @patch("backend.graph.nodes.intent_llm")
    def test_returns_valid_intent_from_llm(self, mock_intent_llm):
        """
        Checks if a valid intent is returned by the mock LLM
        """
        mock_intent_llm.invoke.return_value = intent_decision("tutorial")

        result = classify_intent({
            "messages": [HumanMessage(content="Wie richte ich eduroam ein?")],
            "intent": "",
            "user_email": "test@web.de",
        })

        self.assertEqual(result["intent"], "tutorial")
        mock_intent_llm.invoke.assert_called_once()

    @patch("backend.graph.nodes.intent_llm")
    def test_falls_back_to_unclear_on_unknown_intent(self, mock_intent_llm):
        """
        Checks if the situation of unclear intent is handled correctly
        """
        # LLM liefert einen Wert ausserhalb des Schemas -> doppelter Boden greift
        mock_intent_llm.invoke.return_value = intent_decision("anleitung")

        result = classify_intent({
            "messages": [HumanMessage(content="irgendwas")],
            "intent": "",
            "user_email": "test@web.de",
        })

        self.assertEqual(result["intent"], "unclear")

    @patch("backend.graph.nodes.intent_llm")
    def test_prompt_includes_previous_intent_and_conversation(self, mock_intent_llm):
        """
        Check if the prompt saves the previous conversation
        """
        mock_intent_llm.invoke.return_value = intent_decision("tutorial")

        classify_intent({
            "messages": [HumanMessage(content="hat leider nicht funktioniert")],
            "intent": "tutorial",
            "user_email": "test@web.de",
        })

        prompt = mock_intent_llm.invoke.call_args[0][0][0].content
        self.assertIn("tutorial", prompt)
        self.assertIn("hat leider nicht funktioniert", prompt)

    @patch("backend.graph.nodes.intent_llm")
    def test_email_is_extracted_when_missing(self, mock_intent_llm):
        """
        Checks if the e-mail address is actually extracted into the correct field,
        if it is missing.
        """
        mock_intent_llm.invoke.return_value = intent_decision("tutorial")

        result = classify_intent({
            "messages": [HumanMessage(content="Hallo, meine Mail ist max@web.de")],
            "intent": "tutorial",
            "user_email": "",
        })

        self.assertEqual(result.get("user_email"), "max@web.de")

    @patch("backend.graph.nodes.intent_llm")
    def test_existing_email_is_not_overwritten(self, mock_intent_llm):
        """
        Check if the e-mail address is kept throughout the whole conversation
        """
        mock_intent_llm.invoke.return_value = intent_decision("tutorial")

        result = classify_intent({
            "messages": [HumanMessage(content="Schreib an andere@web.de")],
            "intent": "tutorial",
            "user_email": "vorhanden@web.de",
        })

        self.assertNotIn("user_email", result)


class IntentConstantsTests(unittest.TestCase):
    """Sanity checks on the intent taxonomy without calling the LLM."""

    def test_expected_intents_are_defined(self):
        """
        Checks if all tests have passed
        """
        self.assertEqual(INTENTS, ["tutorial", "problem", "unclear", "solved"])


if __name__ == "__main__":
    unittest.main()