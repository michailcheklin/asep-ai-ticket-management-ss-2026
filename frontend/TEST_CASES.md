# Test Cases – Frontend Clone (Mock Mode)

These test cases verify `app_clone.py` on port **8502**. Prerequisite: Clone runs without backend.

```bash
cd frontend
streamlit run app_clone.py --server.port 8502
```

Or via Docker: `docker compose up frontend_clone`

---

## Acceptance Criteria (Issue)

| ID | Test Case | Steps | Expected Result |
|----|-----------|-------|-----------------|
| **AC-01** | Clone exists | Start `app_clone.py`, open browser | App loads on `http://localhost:8502`, caption „Mock-Modus: keine Backend- oder KI-Aufrufe.“ |
| **AC-02** | Fixed responses | Enter email + student ID, send any message | Fixed mock response appears (no real AI text) |
| **AC-03** | No AI calls | Open network tab, send multiple messages | No requests to `localhost:8000/chat` or `/solution-feedback` |
| **AC-04** | FAQ keyword | Send message `FAQ` | Bot response + blue FAQ placeholder (`st.info`) with WLAN/Moodle/printer text |
| **AC-05** | Ticket keyword | Send message `Ticket` | Bot response + button „Ticket erstellen“ (disabled) |
| **AC-06** | Solution keyword | Send message `Lösung` | Bot response + buttons „Ja“ and „Nein“ |

---

## Form Validation

| ID | Test Case | Steps | Expected Result |
|----|-----------|-------|-----------------|
| **FV-01** | Chat locked without contact details | Load page, leave fields empty | Chat input disabled, placeholder „Bitte E-Mail-Adresse und Matrikelnummer eingeben“ |
| **FV-02** | Invalid email | Email `keine-email`, student ID `12345` | Chat input remains disabled |
| **FV-03** | Invalid student ID | Email `test@uni.de`, student ID `abc123` | Chat input remains disabled |
| **FV-04** | Valid contact details | Email `student@uni.de`, student ID `1234567` | Chat input active, placeholder „Beschreibe dein Anliegen...“ |
| **FV-05** | Message after validation | Enter valid data, send `Hallo` | Message appears in chat, mock response follows |

---

## Mock Keywords (Case Sensitivity)

| ID | Input | Expected `ui_flags` | Expected UI |
|----|-------|----------------------|-------------|
| **MK-01** | `FAQ` | `["show_faq"]` | FAQ placeholder visible |
| **MK-02** | `faq` | `["show_faq"]` | FAQ placeholder visible (case-insensitive) |
| **MK-03** | `Mein FAQ Problem` | `["show_faq"]` | FAQ placeholder (keyword in text) |
| **MK-04** | `Ticket` | `["show_ticket_button"]` | Ticket button visible |
| **MK-05** | `ticket` | `["show_ticket_button"]` | Ticket button visible |
| **MK-06** | `Ich brauche ein Ticket` | `["show_ticket_button"]` | Ticket button visible |
| **MK-07** | `Lösung` | `[]` | Two solution suggestions, Ja/Nein buttons |
| **MK-08** | `solution` | `[]` | Two solution suggestions, Ja/Nein buttons |
| **MK-09** | `Hallo Welt` | `[]` | Generic mock response, no extra UI |
| **MK-10** | `WLAN-Verbindung` | `[]` | Generic mock response (no FAQ keyword) |

**Priority for multiple matches:** `faq` is checked before `ticket` before `lösung`. Input `FAQ Ticket` → FAQ view.

---

## Solution Feedback (Yes/No)

| ID | Test Case | Steps | Expected Result |
|----|-----------|-------|-----------------|
| **FB-01** | Yes – helpful | Send `Lösung` → click „Ja“ | Confirmation „Super, freut mich…“, Ja/Nein buttons disappear |
| **FB-02** | No – Ticket Mock | Restart → `Lösung` → „Nein“ | Mock ticket message „Dein Support-Ticket wurde erstellt (Mock)…“ |
| **FB-03** | Buttons only once | After Ja/Nein, scroll again | No second Ja/Nein buttons for the same message |
| **FB-04** | Chat after feedback | After „Ja“ without reset | Chat input disabled (`bot_thinking = true`) |

---

## Restart (Reset)

| ID | Test Case | Steps | Expected Result |
|----|-----------|-------|-----------------|
| **RS-01** | Reset chat | Send multiple messages → sidebar „Neu starten“ | Only bot greeting message visible |
| **RS-02** | Reset form | Enter contact details → „Neu starten“ | Email and student ID empty |
| **RS-03** | Unlock input | `Lösung` → „Ja“ (input locked) → „Neu starten“ | Chat input active again (after valid contact details) |
| **RS-04** | Page reload | F5 after reset | State remains reset (session preserved) |
| **RS-05** | New tab | Close tab, reopen `localhost:8502` | Fresh start with greeting message |

---

## UI Layout & Appearance

| ID | Test Case | Steps | Expected Result |
|----|-----------|-------|-----------------|
| **UI-01** | Initial greeting | Fresh load of app | One assistant message: „Hallo! Ich bin ZIM Helper…“ |
| **UI-02** | User/Assistant icons | Send message | User message with red icon, bot with orange icon |
| **UI-03** | Waiting status | Send message (observe briefly) | Briefly „Bitte warten. Antwort wird generiert…“, then mock response |
| **UI-04** | Ticket button not clickable | Send `Ticket` | Button visible but `disabled` (no action) |
| **UI-05** | FAQ placeholder content | Send `FAQ` | Info box with „WLAN-Verbindung, Moodle-Login, Drucker im Poolraum“ |
| **UI-06** | Sidebar visible | Load app | Sidebar with „Einstellungen“ and button „Neu starten“ |

---

## Isolation from Backend

| ID | Test Case | Steps | Expected Result |
|----|-----------|-------|-----------------|
| **ISO-01** | Clone without backend | Start only `frontend_clone`, backend stopped | App works normally |
| **ISO-02** | Docker without depends_on | Check `docker compose config` | `frontend_clone` has no `depends_on: backend_app` |
| **ISO-03** | Live vs. Clone separated | Both in parallel: 8501 + 8502 | Clone mocks, live frontend (8501) needs backend |

---

## Regression Live Frontend (`app.py`, Port 8501)

| ID | Test Case | Steps | Expected Result |
|----|-----------|-------|-----------------|
| **LV-01** | Live starts | Backend + `frontend_app` running | App on 8501, **no** mock notice |
| **LV-02** | Real chat | Valid data, send message | Request to `BACKEND_URL/chat`, real AI response |
| **LV-03** | Reset also live | „Neu starten“ in sidebar | Chat and form reset |

---

## Quick Checklist (Smoke Test, ~5 Min.)

1. [ ] Open clone on 8502 → mock caption visible  
2. [ ] Without contact details → chat locked  
3. [ ] `student@uni.de` + `1234567` → chat unlocked  
4. [ ] `FAQ` → FAQ placeholder  
5. [ ] `Ticket` → ticket button (disabled)  
6. [ ] `Lösung` → Ja/Nein → check both responses  
7. [ ] „Neu starten“ → everything empty, greeting back  
8. [ ] Network: no calls to port 8000  

---

## Automatable Unit Tests (MockChatClient)

This logic can be tested in Python without Streamlit:

| Function | Input | Expectation |
|----------|-------|-------------|
| `send_message` | `{"user_message": "FAQ"}` | `"show_faq" in ui_flags` |
| `send_message` | `{"user_message": "Ticket"}` | `"show_ticket_button" in ui_flags` |
| `send_message` | `{"user_message": "Lösung"}` | `len(solutions) == 2` |
| `send_message` | `{"user_message": "Hallo"}` | `ui_flags == []`, generic text |
| `send_feedback` | `{"helpful": True}` | Text contains „Super“ |
| `send_feedback` | `{"helpful": False}` | Text contains „Mock“ |
