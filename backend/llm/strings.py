"""Minimal DE→EN lookup for hardcoded, non-LLM-generated chatbot messages
(ticket confirmations, error fallbacks). Mirrors frontend/ui/strings.py.

The very first greeting is intentionally NOT covered here — it stays in the
browser/system language and is handled entirely in the frontend."""

_EN = {
    "Ich habe gerade ein Support-Ticket erstellt. Für eine optimale Bearbeitung bitte die folgenden Fragen beantworten:":
        "I've just created a support ticket. To process it optimally, please answer the following questions:",
    "Das Anliegen kann leider nicht weiter als ZIM-IT-Support bearbeitet werden, "
    "da keine eindeutige IT-/ZIM-bezogene Problemstellung erkannt wurde.\n\n"
    "Bei einem späteren IT-Problem rund um Dienste der Universität "
    "(z. B. WLAN, VPN, E-Mail, Moodle oder Account-Probleme) hilft der ZIM-IT-Support gerne weiter.":
        "Unfortunately, this request cannot be processed further as ZIM IT support, "
        "since no clear IT/ZIM-related issue was identified.\n\n"
        "For a future IT issue related to university services "
        "(e.g. Wi-Fi, VPN, email, Moodle, or account problems), ZIM IT support will be happy to help.",
    "Keine ausreichende Anfrage für die Suche.": "Not enough information for a search.",
    "Fehler bei der Suche in der Wissensdatenbank.": "Error while searching the knowledge base.",
    "\n\n Konnte das Problem damit gelöst werden?": "\n\n Did this solve the problem?",
    "Super, das freut mich! Bei weiteren Fragen stehe ich jederzeit zur Verfügung. Einen schönen Tag noch!":
        "Great, glad to hear it! Feel free to reach out again if you have further questions. Have a nice day!",
    "Fehler beim Abschließen des Tickets.": "Error while closing the ticket.",
    "Perfekt, {name}!": "Perfect, {name}!",
    "Perfekt!": "Perfect!",
    "{greeting} Perfekt! Ihr Ticket wurde erfolgreich erstellt.\n\n"
    "Ein Support-Mitarbeiter meldet sich so bald wie möglich.\n\n"
    "**Ticketübersicht**\n\n"
    "**Betreff:** {title}\n\n"
    "**E-Mail:** {email}\n\n"
    "**Problembeschreibung:**\n"
    "{issue}":
        "{greeting} Your ticket has been created successfully.\n\n"
        "A support agent will get back to you as soon as possible.\n\n"
        "**Ticket overview**\n\n"
        "**Subject:** {title}\n\n"
        "**Email:** {email}\n\n"
        "**Description:**\n"
        "{issue}",
    "Ticket konnte nicht erstellt werden. Bitte später erneut versuchen.":
        "The ticket could not be created. Please try again later.",
}


def t(text: str, lang: str) -> str:
    """Translate *text* to *lang*; only "en" is translated, everything else stays German."""
    return _EN.get(text, text) if lang == "en" else text
