"""Regression tests for Issue #190: user-facing replies use neutral,
pronoun-free wording (no "du"/"dein", no "Sie"/"Ihr" either).

Why this test reads source instead of importing:
`import backend.graph.nodes` transitively imports backend/rag/retrieve_info.py,
which loads SentenceTransformer models at import time (slow, network-dependent).
So we read the files as text / parse them with `ast` (which does NOT execute
the module) and assert on the fixed message strings only.

Scope: only the hardcoded, user-facing strings. LLM-generated tone is covered
separately by the manual walkthrough and tests/provocation_test_cases.md.
"""
import ast
import os
import re
import unittest

# tests/ lives directly under the project root.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

NODES_PY  = os.path.join(ROOT, "backend", "graph", "nodes.py")
TICKET_PY = os.path.join(ROOT, "backend", "services", "TicketService.py")
API_PY    = os.path.join(ROOT, "backend", "api", "ZIM.py")
CHAT_PY   = os.path.join(ROOT, "frontend", "ui", "chat.py")

# Informal 2nd-person address that must never appear in a user-facing reply.
DU_PATTERN = re.compile(r"\b(?:du|dir|dich|dein\w*)\b", re.IGNORECASE)

# Canonical ticket-intro. MUST be byte-identical in the backend
# (nodes.ask_for_additional_info) and the frontend (chat.TICKET_INTRO_VARIANTS),
# otherwise strip_redundant_ticket_intro() silently stops matching.
TICKET_INTRO = (
    "Ich habe gerade ein Support-Ticket erstellt. "
    "Für eine optimale Bearbeitung bitte die folgenden Fragen beantworten:"
)


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _string_constants(path: str) -> list[str]:
    """Return every string literal in a file via AST (no code execution).

    Adjacent literals like ("a" "b") are folded into one constant by the
    parser, and f-string literal chunks are individual Constants — both are
    covered here.
    """
    tree = ast.parse(_read(path), filename=path)
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            out.append(node.value)
    return out


def _module_str_assign(path: str, name: str) -> str | None:
    """Return the value of a module-level `NAME = "..."` string assignment."""
    tree = ast.parse(_read(path), filename=path)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Name)
                    and target.id == name
                    and isinstance(node.value, ast.Constant)
                    and isinstance(node.value.value, str)
                ):
                    return node.value.value
    return None


def _module_tuple_of_str_assign(path: str, name: str) -> list[str] | None:
    """Return the values of a module-level `NAME = ("...", "...")` tuple assignment."""
    tree = ast.parse(_read(path), filename=path)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Name)
                    and target.id == name
                    and isinstance(node.value, ast.Tuple)
                ):
                    return [
                        elt.value for elt in node.value.elts
                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                    ]
    return None


class NeutralAddressTests(unittest.TestCase):
    """Issue #190 — no informal address in fixed user-facing strings."""

    def test_frontend_ui_strings_have_no_du(self):
        """chat.py has no LLM prompts, so every string literal is fair game."""
        offenders = [s for s in _string_constants(CHAT_PY) if DU_PATTERN.search(s)]
        self.assertEqual(
            offenders, [],
            msg="Informal 'du'/'dein' found in frontend UI strings: " + repr(offenders),
        )

    def test_backend_old_du_replies_are_gone(self):
        """The specific 'du' reply strings changed for #190 must not resurface."""
        forbidden = {
            NODES_PY: [
                "Ich habe für dich gerade ein Support-Ticket",
                "Um dich optimal zu unterstützen",
                "Konnte ich dir dabei helfen",
                "helfe ich dir gerne weiter",
                "Ich kann dein Anliegen leider nicht",
            ],
            TICKET_PY: [
                "Wenn du in Zukunft weitere Fragen hast",
                "Hab einen schönen Tag!",
                "Dein Ticket wurde erfolgreich erstellt",
                "meldet sich so bald wie möglich bei dir",
            ],
            API_PY: [
                "Dein Ticket wurde an den Support weitergeleitet",
            ],
        }
        for path, phrases in forbidden.items():
            source = _read(path)
            for phrase in phrases:
                self.assertNotIn(
                    phrase, source,
                    msg=f"Old 'du' wording resurfaced in {os.path.basename(path)}: {phrase!r}",
                )

    def test_ticket_intro_is_in_sync(self):
        """Backend and frontend ticket-intro must match verbatim."""
        # Frontend: the German variant in the TICKET_INTRO_VARIANTS tuple
        # (used to recognize the intro regardless of response language).
        frontend_intro_variants = _module_tuple_of_str_assign(CHAT_PY, "TICKET_INTRO_VARIANTS")
        self.assertIsNotNone(
            frontend_intro_variants,
            msg="chat.TICKET_INTRO_VARIANTS not found or not a plain string tuple.",
        )
        self.assertIn(
            TICKET_INTRO, frontend_intro_variants,
            msg="chat.TICKET_INTRO_VARIANTS no longer contains the canonical German intro.",
        )
        # Backend: the same text is an f-string literal inside nodes.py.
        self.assertIn(
            TICKET_INTRO, _read(NODES_PY),
            msg="nodes.py ticket-intro text drifted from chat.TICKET_INTRO.",
        )


if __name__ == "__main__":
    unittest.main()