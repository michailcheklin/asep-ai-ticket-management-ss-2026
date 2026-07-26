"""
Unit tests for multiple-choice back navigation in the frontend Q&A widget.

These cover the pure navigation helpers in frontend.ui.chat (no Streamlit
runtime required). Run from the repo root:

    PYTHONPATH=. pytest tests/test_question_back_navigation.py -v -s
"""

import unittest

from frontend.ui.qa_navigation import (
    apply_question_answer,
    can_go_back,
    format_answers_as_message,
    navigate_back,
    parse_questions_from_message,
    split_stored_mcq_answer,
)


class QuestionBackNavigationTests(unittest.TestCase):
    """Back navigation and answer-correction behaviour for the Q&A widget."""

    def test_back_button_unavailable_on_first_question(self):
        self.assertFalse(can_go_back(0))
        self.assertTrue(can_go_back(1))
        self.assertTrue(can_go_back(2))

    def test_navigate_back_returns_to_previous_question(self):
        answers = ["Windows", "Poolraum", "Kabel"]
        new_idx, new_answers = navigate_back(2, answers)

        self.assertEqual(new_idx, 1)
        # Prior answers are kept so the widget can restore the selection.
        self.assertEqual(new_answers, ["Windows", "Poolraum", "Kabel"])

    def test_navigate_back_is_noop_on_first_question(self):
        answers = ["Windows"]
        new_idx, new_answers = navigate_back(0, answers)

        self.assertEqual(new_idx, 0)
        self.assertEqual(new_answers, ["Windows"])

    def test_navigate_back_step_by_step(self):
        answers = ["Windows", "Poolraum", "Kabel"]
        idx, answers = navigate_back(2, answers)
        self.assertEqual(idx, 1)
        idx, answers = navigate_back(idx, answers)
        self.assertEqual(idx, 0)
        self.assertFalse(can_go_back(idx))

    def test_previous_answer_restored_from_stored_mcq(self):
        options = ["Windows", "macOS", "Andere"]
        option, detail = split_stored_mcq_answer("Windows", options)
        self.assertEqual(option, "Windows")
        self.assertEqual(detail, "")

        option, detail = split_stored_mcq_answer("Andere: R11", options)
        self.assertEqual(option, "Andere")
        self.assertEqual(detail, "R11")

    def test_corrected_answer_replaces_stored_value(self):
        answers = ["Windows", "Poolraum"]
        new_idx, new_answers, done = apply_question_answer(
            0, answers, "macOS", is_last=False
        )

        self.assertFalse(done)
        self.assertEqual(new_idx, 1)
        self.assertEqual(new_answers, ["macOS"])

    def test_unchanged_answer_keeps_subsequent_answers(self):
        answers = ["Windows", "Poolraum", "Kabel"]
        new_idx, new_answers, done = apply_question_answer(
            0, answers, "Windows", is_last=False
        )

        self.assertFalse(done)
        self.assertEqual(new_idx, 1)
        self.assertEqual(new_answers, ["Windows", "Poolraum", "Kabel"])

    def test_dependent_subsequent_answers_reset_when_answer_changes(self):
        answers = ["Windows", "Poolraum", "Kabel"]
        _, new_answers, _ = apply_question_answer(
            1, answers, "Bibliothek", is_last=False
        )

        self.assertEqual(new_answers, ["Windows", "Bibliothek"])
        self.assertNotIn("Kabel", new_answers)

    def test_final_message_uses_corrected_answers(self):
        questions = parse_questions_from_message(
            "* Welches OS? (options: Windows | macOS | Andere)\n"
            "* Wo bist du? (options: Poolraum | Bibliothek | Andere)"
        )
        answers = ["Windows", "Poolraum"]
        _, answers, _ = apply_question_answer(0, answers, "macOS", is_last=False)
        _, answers, done = apply_question_answer(
            1, answers, "Bibliothek", is_last=True
        )

        self.assertTrue(done)
        message = format_answers_as_message(questions, answers)
        self.assertIn("macOS", message)
        self.assertIn("Bibliothek", message)
        self.assertNotIn("Windows", message)
        self.assertNotIn("Poolraum", message)

    def test_forward_only_workflow_unchanged(self):
        """Answering without using Back still appends and completes as before."""
        answers: list[str] = []
        idx, answers, done = apply_question_answer(0, answers, "Windows", is_last=False)
        self.assertEqual((idx, answers, done), (1, ["Windows"], False))

        idx, answers, done = apply_question_answer(1, answers, "Poolraum", is_last=True)
        self.assertEqual(idx, 1)
        self.assertEqual(answers, ["Windows", "Poolraum"])
        self.assertTrue(done)


if __name__ == "__main__":
    unittest.main()
