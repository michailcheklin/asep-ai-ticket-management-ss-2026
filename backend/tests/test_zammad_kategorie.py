import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.api.zammad import resolve_zammad_kategorie
from backend.graph.models.TicketCategoryDecision import TICKET_CATEGORIES


class ResolveZammadKategorieTests(unittest.TestCase):
    def test_returns_configured_category_unchanged(self):
        self.assertEqual(resolve_zammad_kategorie("Incident"), "Incident")
        self.assertIn("Incident", TICKET_CATEGORIES)

    def test_returns_none_for_empty_or_unknown_values(self):
        self.assertIsNone(resolve_zammad_kategorie(None))
        self.assertIsNone(resolve_zammad_kategorie(""))
        self.assertIsNone(resolve_zammad_kategorie("Beschwerde"))
        self.assertIsNone(resolve_zammad_kategorie("Netzwerk"))


if __name__ == "__main__":
    unittest.main()
