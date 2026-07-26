"""Minimal DE→EN lookup for the static Streamlit UI chrome (buttons, labels,
errors). LLM-generated chat content is translated by the backend itself and
never passes through here."""

_EN = {
    "Hallo! Ich bin ZIM Helper. Worum geht es? Bitte das Anliegen kurz beschreiben.":
        "Hello! I'm ZIM Helper. What's going on? Please briefly describe the issue.",
    "Hallo {name}! Ich bin ZIM Helper. Worum geht es? Bitte das Anliegen kurz beschreiben.":
        "Hello {name}! I'm ZIM Helper. What's going on? Please briefly describe the issue.",
    "Bitte warten. Antwort wird generiert...": "Please wait. Generating a response...",
    "(keine Zusammenfassung vorhanden)": "(no summary available)",
    "Die Anfrage konnte aus Sicherheitsgründen nicht verarbeitet werden.":
        "The request could not be processed for security reasons.",
    "Danke, {name}!": "Thanks, {name}!",
    "Danke!": "Thanks!",
    "{greeting} Das Feedback wurde notiert und ein Support-Ticket erstellt. Ein Agent kümmert sich bald um das Anliegen.":
        "{greeting} Your feedback has been noted and a support ticket has been created. An agent will take care of it soon.",
    "FAQ-Platzhalter: WLAN-Verbindung, Moodle-Login, Drucker im Poolraum, …":
        "FAQ placeholder: Wi-Fi connection, Moodle login, printer in the pool room, …",
    "Ticket erstellen": "Create ticket",
    "Ja": "Yes",
    "Nein": "No",
    "**Zusammenfassung des Anliegens**": "**Summary of the issue**",
    "Hier weitere Information zum Anliegen ergänzen:": "Add further information about the issue here:",
    "Ticket absenden": "Submit ticket",
    "Bitte eine Ergänzung ein oder die Zusammenfassung ohne Änderungen bestätigen.":
        "Please add a note or confirm the summary without changes.",
    "Zusammenfassung bestätigen": "Confirm summary",
    "Informationen ergänzen": "Add information",
    "**Erkannte Geräteinformationen**\n": "**Detected device information**\n",
    "Der Browser hat diese Informationen automatisch bereitgestellt. Dadurch lässt sich besser nachvollziehen, unter welchen Bedingungen das Problem auftritt.":
        "The browser provided this information automatically. It helps to better understand the conditions under which the problem occurs.",
    "Bezieht sich das Anliegen auf ein **{device}**-Gerät?": "Does the issue relate to a **{device}** device?",
    "Welches Gerät wird verwendet?": "Which device is being used?",
    "Bezieht sich das Anliegen auf **{os_name}**?": "Does the issue relate to **{os_name}**?",
    "Welches Betriebssystem wird verwendet?": "Which operating system is being used?",
    "Bestätigen": "Confirm",
    "Bitte beide Fragen beantworten.": "Please answer both questions.",
    "Bitte das Gerät angeben.": "Please specify the device.",
    "Bitte das Betriebssystem angeben.": "Please specify the operating system.",
    "Frage {idx} von {total}": "Question {idx} of {total}",
    "Bitte eine Option wählen :": "Please choose an option:",
    "Bitte genauer angeben:": "Please specify:",
    "Antwort:": "Answer:",
    "Senden ✓": "Submit ✓",
    "Weiter →": "Next →",
    "← Zurück": "← Back",
    "Bitte die Frage beantworten, bevor es weitergeht.": "Please answer the question before continuing.",
    "Support-Annahme über ZIM Helper": "Support intake via ZIM Helper",
    "Digitaler Assistent für Support-Anfragen": "Digital assistant for support requests",
    "Mock-Modus: keine Backend- oder KI-Aufrufe.": "Mock mode: no backend or AI calls.",
    "Kontaktdaten": "Contact details",
    "E-Mail-Adresse *": "Email address *",
    "Matrikelnummer *": "Student ID *",
    "ZIM Helper": "ZIM Helper",
    "Einstellungen": "Settings",
    "**Eingeloggt als:** {name}": "**Logged in as:** {name}",
    "Student": "Student",
    "Mitarbeiter": "Staff",
    "Neu starten": "Restart",
    "Bitte zuerst die Geräteinformationen bestätigen.": "Please confirm the device information first.",
    "Das Gespräch ist abgeschlossen — bitte über 'Neu starten' ein neues Anliegen beginnen.":
        "This conversation is complete — please use 'Restart' to start a new request.",
    "Bitte E-Mail-Adresse und Matrikelnummer eingeben": "Please enter your email address and student ID",
    "Anliegen beschreiben...": "Describe your issue...",
    "Senden": "Send",
    "Aufnehmen": "Record",
    "Wird transkribiert...": "Transcribing...",
}


def t(text: str, lang: str) -> str:
    """Translate *text* to *lang*; only "en" is translated, everything else stays German."""
    return _EN.get(text, text) if lang == "en" else text
