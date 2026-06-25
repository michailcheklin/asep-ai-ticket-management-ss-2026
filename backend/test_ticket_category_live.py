"""Live LLM tests for ticket category classification."""

import os
import unittest

from category_test_support import (
    load_holdout_cases,
    load_regression_cases,
    regression_limit,
    run_live_category_suite,
)
from nodes import classify_ticket_category


@unittest.skipUnless(
    os.getenv("RUN_LLM_CATEGORY_TESTS") == "1",
    "Set RUN_LLM_CATEGORY_TESTS=1 to run live LLM integration tests",
)
class LiveCategoryClassificationTests(unittest.TestCase):
    """Spot checks against the real LLM for representative category cases."""

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
    """Regression accuracy against tickets from rag/old_tickets.json."""

    @classmethod
    def setUpClass(cls):
        cls.cases = load_regression_cases()
        limit = regression_limit()
        if limit is not None:
            cls.cases = cls.cases[:limit]

    def test_regression_cases_from_old_tickets(self):
        min_accuracy = float(os.getenv("CATEGORY_REGRESSION_MIN_ACCURACY", "0.90"))
        run_live_category_suite(
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
    """Generalization accuracy against unseen holdout tickets."""

    @classmethod
    def setUpClass(cls):
        cls.cases = load_holdout_cases()

    def test_holdout_cases_generalization(self):
        min_accuracy = float(os.getenv("CATEGORY_HOLDOUT_MIN_ACCURACY", "0.80"))
        run_live_category_suite(
            self,
            label="HOLDOUT",
            cases=self.cases,
            min_accuracy=min_accuracy,
        )
