import unittest

from backend.services.TicketService import TicketService


class TicketConfirmationBodyTests(unittest.TestCase):
    """
    This test class tests how the ticket confirmation function works.
    """
    def setUp(self):
        """
        In this method the base parameters of the test case are set
        such as the matriculation number and already received information.
        """
        self.service = TicketService()
        self.base_state = {
            "matrikelnummer": "1234567",
            "user_email": "student@uni-due.de",
            "priority": 0,
            "category": "Incident",
            "issue_description": "WLAN funktioniert nicht",
            "additional_info": ["Gebäude LF"],
            "full_conversation": "Der Student hat ein WLAN-Problem im Gebäude LF.",
            "solutions": [],
        }

    def test_ticket_body_includes_conversation_summary(self):
        """
        This test checks if the conversation summary is in the ticket body
        """
        body = self.service._build_open_body(self.base_state)
        self.assertIn("GESPRÄCHSZUSAMMENFASSUNG", body)
        self.assertIn("WLAN-Problem im Gebäude LF", body)

    def test_ticket_body_includes_user_addendum_unchanged(self):
        """
        This test checks if the user's addendum has been put literally
        into the ticket body along with the "ERGÄNZUNG DURCH NUTZER" header
        """
        state = {**self.base_state, "user_addendum": "Das Problem tritt nur im 3. OG auf."}
        body = self.service._build_open_body(state)
        self.assertIn("ERGÄNZUNG DURCH NUTZER", body)
        self.assertIn("Das Problem tritt nur im 3. OG auf.", body)

    def test_ticket_body_omits_addendum_section_when_empty(self):
        """
        This test checks if in case the user did not add any information,
        the Zammad ticket body does not have an empty section "ERGÄNZUNG DURCH NUTZER"
        """
        body = self.service._build_open_body(self.base_state)
        self.assertNotIn("ERGÄNZUNG DURCH NUTZER", body)


if __name__ == "__main__":
    unittest.main()
