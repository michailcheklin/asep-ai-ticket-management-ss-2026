"""App-wide UI i18n for the Streamlit frontend: DE→EN string lookup + language
resolution. Single entry point for every page/component.

Usage on any page/component:
    from ...ui.i18n import t, get_language
    lang = get_language()
    st.button(t("Abbrechen", lang))     # add the German text as a key in _EN below

Only static UI chrome passes through here; LLM-generated chat content is
translated by the backend itself. Backend hardcoded messages have their own
mirror at backend/llm/strings.py (separate process)."""
import streamlit as st

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

    # --- FAQ submission page (frontend/pages/faq.py) ---
    "FAQ hinzufügen": "Add FAQ",
    "📝 Neuen FAQ-Eintrag vorschlagen": "📝 Propose a new FAQ entry",
    "Vorschläge werden vor dem Speichern gegen die bestehende FAQ-Datenbank auf Redundanz geprüft und sprachlich überarbeitet.":
        "Before saving, proposals are checked for redundancy against the existing FAQ database and language-polished.",
    "Titel:": "Title:",
    "Leer lassen — der Titel wird automatisch als Aussage erzeugt.":
        "Leave empty — the title is generated automatically as a statement.",
    "Kategorie:": "Category:",
    "Kategorie wählen": "Choose a category",
    "Problem:": "Problem:",
    "Lösung:": "Solution:",
    "Vorschlag prüfen & absenden": "Check & submit proposal",
    "Bitte Kategorie, Problem und Lösung ausfüllen.": "Please fill in category, problem and solution.",
    "Dein Vorschlag scheint bereits durch folgende FAQ-Einträge abgedeckt zu sein. Bitte überdenke ihn – oder lege ihn dennoch an.":
        "Your proposal seems to already be covered by the following FAQ entries. Please reconsider it — or create it anyway.",
    "{id} — Ähnlichkeit {similarity}": "{id} — similarity {similarity}",
    "**Titel:** {v}": "**Title:** {v}",
    "**Problem:** {v}": "**Problem:** {v}",
    "**Lösung:** {v}": "**Solution:** {v}",
    "Dennoch anlegen": "Create anyway",
    "Abbrechen": "Cancel",
    "So wird der Eintrag gespeichert. Du kannst ihn hier noch anpassen.":
        "This is how the entry will be saved. You can still adjust it here.",
    "Speichern bestätigen": "Confirm & save",
    "FAQ-Eintrag angelegt (Titel: {title}).": "FAQ entry created (title: {title}).",
    "Fehler: {detail}": "Error: {detail}",
    "Unbekannter Fehler": "Unknown error",
}


def t(text: str, lang: str) -> str:
    """Translate *text* to *lang*; only "en" is translated, everything else stays German."""
    return _EN.get(text, text) if lang == "en" else text


def parse_language_from_header(accept_language: str) -> str:
    """Extract the primary supported UI language ("de"/"en") from an Accept-Language
    header; anything else falls back to "de"."""
    primary = accept_language.split(",")[0].strip().split("-")[0].lower()
    return primary if primary in ("de", "en") else "de"


def get_language() -> str:
    """The single UI-language resolver for every page/component. Returns "de"/"en",
    resolved once and cached in the session:
    IdP/chat metadata override -> cached value -> browser Accept-Language -> "de"."""
    meta = st.session_state.get("user_metadata") or {}
    if meta.get("language") in ("de", "en"):
        return meta["language"]
    cached = st.session_state.get("_ui_language")
    if cached in ("de", "en"):
        return cached
    lang = parse_language_from_header(st.context.headers.get("Accept-Language", ""))
    st.session_state["_ui_language"] = lang
    return lang
