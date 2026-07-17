import unittest

from backend.graph.routing import route_after_classification


class RouteAfterClassificationTests(unittest.TestCase):
    """Tests fuer das Tutorial-Exit-Routing (Issue #178, Part 1)."""

    def test_solved_intent_routes_to_finish_tutorial(self):
        state = {"intent": "solved", "tutorial_attempts": 1}
        self.assertEqual(route_after_classification(state), "finish_tutorial_node")

    def test_exceeded_tutorial_limit_stays_on_problem_path(self):
        state = {"intent": "tutorial", "tutorial_attempts": 4}
        self.assertEqual(route_after_classification(state), "escalate_incidents_node")

    def test_problem_intent_routes_to_problem_path(self):
        state = {"intent": "problem", "tutorial_attempts": 0}
        self.assertEqual(route_after_classification(state), "escalate_incidents_node")


if __name__ == "__main__":
    unittest.main()