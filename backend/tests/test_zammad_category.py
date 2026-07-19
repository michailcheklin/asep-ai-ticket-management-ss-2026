import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.api.zammad import resolve_zammad_category
from backend.graph.models.TicketCategoryDecision import TICKET_CATEGORIES


class ResolveZammadCategoryTests(unittest.TestCase):
    def test_returns_configured_category_unchanged(self):
        self.assertEqual(resolve_zammad_category("Incident"), "Incident")
        self.assertIn("Incident", TICKET_CATEGORIES)

    def test_returns_none_for_empty_or_unknown_values(self):
        self.assertIsNone(resolve_zammad_category(None))
        self.assertIsNone(resolve_zammad_category(""))
        self.assertIsNone(resolve_zammad_category("Beschwerde"))
        self.assertIsNone(resolve_zammad_category("Netzwerk"))


if __name__ == "__main__":
    unittest.main()
