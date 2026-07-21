# Testfälle – Frontend Clone (Mock-Modus)

Diese Testfälle prüfen `app_clone.py` auf Port **8502**. Voraussetzung: Clone läuft ohne Backend.

```bash
cd frontend
streamlit run app_clone.py --server.port 8502
```

Oder per Docker: `docker compose up frontend_clone`

---

## Acceptance Criteria (Issue)

| ID | Testfall | Schritte | Erwartetes Ergebnis |
|----|----------|----------|---------------------|
| **AC-01** | Clone existiert | `app_clone.py` starten, Browser öffnen | App lädt auf `http://localhost:8502`, Caption „Mock-Modus: keine Backend- oder KI-Aufrufe.“ |
| **AC-02** | Feste Antworten | E-Mail + Matrikelnummer eingeben, beliebige Nachricht senden | Feste Mock-Antwort erscheint (kein echter KI-Text) |
| **AC-03** | Keine AI-Calls | Netzwerk-Tab öffnen, mehrere Nachrichten senden | Keine Requests an `localhost:8000/chat` oder `/solution-feedback` |
| **AC-04** | FAQ-Keyword | Nachricht `FAQ` senden | Bot-Antwort + blauer FAQ-Platzhalter (`st.info`) mit WLAN/Moodle/Drucker-Text |
| **AC-05** | Ticket-Keyword | Nachricht `Ticket` senden | Bot-Antwort + Button „Ticket erstellen“ (deaktiviert) |
| **AC-06** | Lösung-Keyword | Nachricht `Lösung` senden | Bot-Antwort + Buttons „Ja“ und „Nein“ |

---

## Formular-Validierung

| ID | Testfall | Schritte | Erwartetes Ergebnis |
|----|----------|----------|---------------------|
| **FV-01** | Chat ohne Kontaktdaten gesperrt | Seite laden, Felder leer lassen | Chat-Input deaktiviert, Placeholder „Bitte E-Mail-Adresse und Matrikelnummer eingeben“ |
| **FV-02** | Ungültige E-Mail | E-Mail `keine-email`, Matrikel `12345` | Chat-Input bleibt deaktiviert |
| **FV-03** | Ungültige Matrikelnummer | E-Mail `test@uni.de`, Matrikel `abc123` | Chat-Input bleibt deaktiviert |
| **FV-04** | Gültige Kontaktdaten | E-Mail `student@uni.de`, Matrikel `1234567` | Chat-Input aktiv, Placeholder „Beschreibe dein Anliegen...“ |
| **FV-05** | Nachricht nach Validierung | Gültige Daten eingeben, `Hallo` senden | Nachricht erscheint im Chat, Mock-Antwort folgt |

---

## Mock-Keywords (Groß-/Kleinschreibung)

| ID | Eingabe | Erwartete `ui_flags` | Erwartete UI |
|----|---------|----------------------|--------------|
| **MK-01** | `FAQ` | `["show_faq"]` | FAQ-Platzhalter sichtbar |
| **MK-02** | `faq` | `["show_faq"]` | FAQ-Platzhalter sichtbar (case-insensitive) |
| **MK-03** | `Mein FAQ Problem` | `["show_faq"]` | FAQ-Platzhalter (Keyword im Text) |
| **MK-04** | `Ticket` | `["show_ticket_button"]` | Ticket-Button sichtbar |
| **MK-05** | `ticket` | `["show_ticket_button"]` | Ticket-Button sichtbar |
| **MK-06** | `Ich brauche ein Ticket` | `["show_ticket_button"]` | Ticket-Button sichtbar |
| **MK-07** | `Lösung` | `[]` | Zwei Lösungsvorschläge, Ja/Nein-Buttons |
| **MK-08** | `solution` | `[]` | Zwei Lösungsvorschläge, Ja/Nein-Buttons |
| **MK-09** | `Hallo Welt` | `[]` | Generische Mock-Antwort, keine Extra-UI |
| **MK-10** | `WLAN-Verbindung` | `[]` | Generische Mock-Antwort (kein FAQ-Keyword) |

**Priorität bei Mehrfach-Treffern:** `faq` wird vor `ticket` vor `lösung` geprüft. Eingabe `FAQ Ticket` → FAQ-Ansicht.

---

## Lösungs-Feedback (Ja/Nein)

| ID | Testfall | Schritte | Erwartetes Ergebnis |
|----|----------|----------|---------------------|
| **FB-01** | Ja – hilfreich | `Lösung` senden → „Ja“ klicken | Bestätigung „Super, freut mich…“, Ja/Nein-Buttons verschwinden |
| **FB-02** | Nein – Ticket Mock | Neu starten → `Lösung` → „Nein“ | Mock-Ticket-Nachricht „Dein Support-Ticket wurde erstellt (Mock)…“ |
| **FB-03** | Buttons nur einmal | Nach Ja/Nein erneut scrollen | Keine zweiten Ja/Nein-Buttons bei derselben Nachricht |
| **FB-04** | Chat nach Feedback | Nach „Ja“ ohne Reset | Chat-Input deaktiviert (`bot_thinking = true`) |

---

## Multiple-Choice Zurück-Navigation (Live / Q&A-Widget)

Voraussetzung: Bot-Antwort mit mehreren `* Frage? (options: …)`-Bullets (Live-Backend). Automatisierte Abdeckung: `tests/test_question_back_navigation.py`.

| ID | Testfall | Schritte | Erwartetes Ergebnis |
|----|----------|----------|---------------------|
| **QB-01** | Kein Zurück bei Frage 1 | Erste MCQ-Frage anzeigen | Button „← Zurück“ nicht sichtbar |
| **QB-02** | Zurück zur vorherigen Frage | Frage 1 beantworten → Weiter → „← Zurück“ | Frage 1 wird wieder angezeigt |
| **QB-03** | Auswahl wiederhergestellt | Zurück nach Auswahl | Zuvor gewählte Option ist vorausgewählt |
| **QB-04** | Antwort ändern | Zurück → andere Option → Weiter | Neue Antwort ersetzt die alte; spätere Antworten der Runde entfallen |
| **QB-05** | Mehrere Schritte zurück | Mehrere Fragen beantworten, mehrfach „← Zurück“ | Schrittweise Rückkehr ohne neue Tickets/Doppel-Nachrichten |
| **QB-06** | Ohne Zurück unverändert | Fragen nur mit Weiter/Senden beantworten | Bisheriger Ablauf unverändert |

---

## Neu starten (Reset)

| ID | Testfall | Schritte | Erwartetes Ergebnis |
|----|----------|----------|---------------------|
| **RS-01** | Chat zurücksetzen | Mehrere Nachrichten senden → Sidebar „Neu starten“ | Nur Begrüßungsnachricht des Bots sichtbar |
| **RS-02** | Formular zurücksetzen | Kontaktdaten eingeben → „Neu starten“ | E-Mail und Matrikelnummer leer |
| **RS-03** | Input entsperren | `Lösung` → „Ja“ (Input gesperrt) → „Neu starten“ | Chat-Input wieder aktiv (nach gültigen Kontaktdaten) |
| **RS-04** | Seiten-Reload | F5 nach Reset | Zustand bleibt zurückgesetzt (Session erhalten) |
| **RS-05** | Neuer Tab | Tab schließen, `localhost:8502` neu öffnen | Frischer Start mit Begrüßungsnachricht |

---

## UI-Layout & Darstellung

| ID | Testfall | Schritte | Erwartetes Ergebnis |
|----|----------|----------|---------------------|
| **UI-01** | Initiale Begrüßung | App frisch laden | Eine Assistant-Nachricht: „Hallo! Ich bin ZIM Helper…“ |
| **UI-02** | User/Assistant Icons | Nachricht senden | User-Nachricht mit rotem Icon, Bot mit orangem Icon |
| **UI-03** | Warte-Status | Nachricht senden (kurz beobachten) | Kurz „Bitte warten. Antwort wird generiert…“, dann Mock-Antwort |
| **UI-04** | Ticket-Button nicht klickbar | `Ticket` senden | Button sichtbar, aber `disabled` (keine Aktion) |
| **UI-05** | FAQ-Platzhalter Inhalt | `FAQ` senden | Info-Box mit „WLAN-Verbindung, Moodle-Login, Drucker im Poolraum“ |
| **UI-06** | Sidebar sichtbar | App laden | Sidebar mit „Einstellungen“ und Button „Neu starten“ |

---

## Isolation vom Backend

| ID | Testfall | Schritte | Erwartetes Ergebnis |
|----|----------|----------|---------------------|
| **ISO-01** | Clone ohne Backend | Nur `frontend_clone` starten, Backend gestoppt | App funktioniert normal |
| **ISO-02** | Docker ohne depends_on | `docker compose config` prüfen | `frontend_clone` hat kein `depends_on: backend_app` |
| **ISO-03** | Live vs. Clone getrennt | Beide parallel: 8501 + 8502 | Clone mockt, Live-Frontend (8501) braucht Backend |

---

## Regression Live-Frontend (`app.py`, Port 8501)

| ID | Testfall | Schritte | Erwartetes Ergebnis |
|----|----------|----------|---------------------|
| **LV-01** | Live startet | Backend + `frontend_app` laufen | App auf 8501, **kein** Mock-Hinweis |
| **LV-02** | Echter Chat | Gültige Daten, Nachricht senden | Request an `BACKEND_URL/chat`, echte KI-Antwort |
| **LV-03** | Reset auch live | „Neu starten“ in Sidebar | Chat und Formular zurückgesetzt |

---

## Schnell-Checkliste (Smoke Test, ~5 Min.)

1. [ ] Clone auf 8502 öffnen → Mock-Caption sichtbar  
2. [ ] Ohne Kontaktdaten → Chat gesperrt  
3. [ ] `student@uni.de` + `1234567` → Chat frei  
4. [ ] `FAQ` → FAQ-Platzhalter  
5. [ ] `Ticket` → Ticket-Button (disabled)  
6. [ ] `Lösung` → Ja/Nein → beide Antworten prüfen  
7. [ ] „Neu starten“ → alles leer, Begrüßung zurück  
8. [ ] Netzwerk: keine Calls an Port 8000  

---

## Automatisierbare Unit-Tests (MockChatClient)

Diese Logik kann ohne Streamlit per Python getestet werden:

| Funktion | Input | Erwartung |
|----------|-------|-----------|
| `send_message` | `{"user_message": "FAQ"}` | `"show_faq" in ui_flags` |
| `send_message` | `{"user_message": "Ticket"}` | `"show_ticket_button" in ui_flags` |
| `send_message` | `{"user_message": "Lösung"}` | `len(solutions) == 2` |
| `send_message` | `{"user_message": "Hallo"}` | `ui_flags == []`, generischer Text |
| `send_feedback` | `{"helpful": True}` | Text enthält „Super“ |
| `send_feedback` | `{"helpful": False}` | Text enthält „Mock“ |
