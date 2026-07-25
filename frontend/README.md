
# Chatbot frontend

## How the chat interface is implemented
In the beginning the elements before the chat input are defined, such as the header. Also, there are form fields defined which must be filled out correctly. For the chat input a number of initial states are defined in the `initial_states` dictionary which then gets copied into the session state. 

The form fields are checked for validity in the `all_form_fields_valid` method which is called by the definition in the `user_input` to check whether to allow or block the user entering a chat message. If either the email or the immatriculation number are not valid, the input field for the chat is disabled.

The method `bot_starting_thinking` is called when the user presses the "Send" button in the chat input to send the chat message. This causes the input field to become disabled while the bot is generating the answer. This is to prevent the user from interrupting the bot while it generates the answer.

When the user sends a message, the user's input gets displayed in the chat history (`with st.chat_message("user"):`). Additionally, the bot shows first "Please wait... Answer is generated..." first, before the answer is generated. To generate the answer, the frontend sends a POST request to the chat endpoint in the backend along with the current chat's state. 

After the bot has replied, the answer is written into the visible chat history and the updated state that the backend returned is applied to the frontend, so that the next chat message can reuse the new state. Technically all the chat messages are Streamlit containers (`with st.chat_message("assistant"):` and then within the with statement one or more `st.write(...)`, as per https://docs.streamlit.io/develop/api-reference/chat/st.chat_message), so the chat messages can be extended to contain other elements as well.

## Further user workflow
If a problem has been recognized, and the user gave enough info, then the bot gives solutions and asks if the solutions helped. If yes, the problem gets marked as resolved. If no, then the user gets a summary and may correct if they wish. The addendum gets added to the Zammad ticket.

### Multiple-choice questions (Q&A widget)
When the bot asks follow-up questions as markdown bullets with `(options: …)`, the frontend shows them one at a time. Users can go **← Zurück** to a previous question (hidden on the first question), change an answer, and continue. Changing an answer clears later answers in that round so dependent follow-ups are re-answered; leaving an answer unchanged keeps them. Only when the last answer is confirmed are all answers sent to the backend as a single message — going back never creates a new ticket or duplicates chat messages.

## Project structure

| File | Purpose |
|------|---------|
| `app.py` | Live frontend (calls AI backend via `LiveChatClient`) |
| `app_clone.py` | Mock frontend clone (no backend calls, via `MockChatClient`) |
| `ui/chat.py` | Shared Streamlit UI and session-state handling |
| `ui/qa_navigation.py` | Pure helpers for MCQ parsing and back navigation |
| `ui/i18n.py` | App-wide UI localization: `t(text, lang)` + `get_language()` (see Localization) |
| `pages/faq.py` | Native multipage page at `/faq` for proposing new FAQ entries (see FAQ submission page) |
| `clients/live_client.py` | HTTP client for `/chat`, `/solution-feedback`, `/faq`, `/faq/contexts` |
| `clients/mock_client.py` | Keyword-based fixed responses for UI testing |

## Localization (DE/EN)

All static UI text is localized through `ui/i18n.py`. Import `t` and `get_language` and wrap every user-facing German string:

```python
from ui.i18n import t, get_language   # chat.py uses the `frontend.ui.i18n` prefix; both resolve
lang = get_language()
st.button(t("Abbrechen", lang))       # -> "Cancel" when lang == "en"
```

- `get_language()` is the single language source for every page/component: it returns `"de"`/`"en"`, resolved from IdP/chat metadata → a session cache → the browser `Accept-Language` header → `"de"` default. There is no manual language switcher.
- Translations live in the `_EN` dict, keyed by the **German source text**. Add a new string by adding a `"<German>": "<English>"` entry and wrapping the call site in `t(...)`. An untranslated/misspelled key silently falls back to German.
- Placeholders (`{name}`) stay in the string and are filled with `.format(...)` **after** `t(...)`, so both language variants share the same tokens.
- Only UI chrome is translated here; LLM-generated chat content is localized by the backend, and stored FAQ content/categories stay in their stored language.

## FAQ submission page (`/faq`)

`pages/faq.py` (reachable at `:8501/faq`) lets staff add new FAQ knowledge to the RAG database. The form has a mandatory **category** dropdown (populated from `GET /faq/contexts`), plus title/problem/solution. On submit the backend checks for redundancy; the covering entries are shown for review ("create anyway" / "cancel"). A non-redundant (or forced) proposal returns an **editable preview** (language-polished text + generated title) that is stored only after the user confirms. Backend logic: `backend/rag/faq_submission.py` and `backend/rag/README.md`.

## Starting the frontend

### Live frontend (with backend)
To test the frontend alone locally:
* run `python3 dev.py`
* open your browser at `http:localhost:5000`

Otherwise, the frontend runs on `http:localhost:8501` when the full project is started (using `docker compose`).

### Mock clone (no backend / no AI)
For layout and UI testing without starting the backend:

```bash
streamlit run app_clone.py --server.port 8502
```

Or with Docker Compose:

```bash
docker compose up frontend_clone
```

Open `http://localhost:8502`.

#### Mock keywords

| User message contains | UI effect |
|-----------------------|-----------|
| `FAQ` | FAQ placeholder (`st.info`) |
| `Ticket` | Disabled „Ticket erstellen“ button |
| `Lösung` or `solution` | Solution cards with Ja/Nein feedback buttons |
| anything else | Generic fixed mock reply |
