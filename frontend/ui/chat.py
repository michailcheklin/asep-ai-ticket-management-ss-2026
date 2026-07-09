"""Shared Streamlit chat UI used by the live app and the mock clone."""
import copy
import re

import streamlit as st
from streamlit.components.v1 import html

from frontend.clients.base import ChatClient

INITIAL_STATES = {
    "messages": [
        {
            "role": "assistant",
            "content": "Hallo! Ich bin ZIM Helper. Erzähl mir bitte von deinem Anliegen.",
        }
    ],
    "bot_thinking": False,
    "chatbot_history": [],
    "issue_description": "",
    "additional_info": [],
    "priority": 0,
    "category": "",
    "additional_info_attempts": 0,
    "ask_issue_attempts": 0,
    "full_conversation": "",
    # ── Ticket confirmation (frontend-only, before finalising support ticket) ──
    "pending_ticket_confirmation": None,  # message index with unhelpful solution feedback
    "show_ticket_addendum_form": False,
    "intent": "",
    "tutorial_attempts": 0,
    # ── Q&A widget state (frontend-only, never sent to the backend) ──────────
    "pending_questions": [],   # list of {text: str, options: list[str] | None}
    "current_question_idx": 0,
    "question_answers": [],    # answers collected so far in the current round
    "_ready_to_send": None,    # combined message text waiting to be dispatched
    "scroll_target": None,     # anchor id to scroll to after rerun
}

WAITING_MESSAGE = '*:color[Bitte warten. Antwort wird generiert...]{foreground="#888888"}*'


# ── Session state helpers ────────────────────────────────────────────────────

def init_session_state() -> None:
    for key, value in INITIAL_STATES.items():
        if key not in st.session_state:
            st.session_state[key] = copy.deepcopy(value)


def reset_session_state() -> None:
    """Clear chat history and unlock the input for a fresh start."""
    for key, value in INITIAL_STATES.items():
        st.session_state[key] = copy.deepcopy(value)
    st.session_state["email_input"] = ""
    st.session_state["matrikelnummer_input"] = ""


def bot_starting_thinking() -> None:
    st.session_state.bot_thinking = True


# ── Validation & scrolling helpers ───────────────────────────────────────────


def _scroll_page_to_bottom(anchor_id: str | None = None) -> None:
    """
    Scroll the Streamlit page to a specific anchor or to the bottom.

    Important:
    components.html/html runs inside an iframe, so we must access
    window.parent.document instead of document.
    """
    anchor_id_js = repr(anchor_id) if anchor_id else "null"

    html(
        f"""
        <script>
        const anchorId = {anchor_id_js};

        function scrollNow() {{
            const parentWindow = window.parent;
            const parentDoc = parentWindow.document;

            const anchor = anchorId ? parentDoc.getElementById(anchorId) : null;

            if (anchor && typeof anchor.scrollIntoView === "function") {{
                anchor.scrollIntoView({{
                    behavior: "smooth",
                    block: "center"
                }});
                parentWindow.scrollBy({{
                    top: 120,
                    left: 0,
                    behavior: "smooth"
                }});
                return;
            }}

            parentWindow.scrollTo({{
                top: parentDoc.body.scrollHeight,
                behavior: "smooth"
            }});
        }}

        setTimeout(scrollNow, 50);
        setTimeout(scrollNow, 200);
        setTimeout(scrollNow, 500);
        setTimeout(scrollNow, 900);
        </script>
        """,
        height=0,
    )


def are_form_fields_valid() -> bool:
    is_email_valid = bool(
        re.fullmatch(
            pattern=r"[a-zA-Z0-9\._-]+@[a-zA-Z0-9\._-]+\.[a-zA-Z0-9\._-]+",
            string=st.session_state["email_input"],
        )
    )
    is_matrikelnummer_valid = bool(
        re.fullmatch(pattern=r"[0-9]+", string=st.session_state["matrikelnummer_input"])
    )
    return is_email_valid and is_matrikelnummer_valid


# ── Question parsing & formatting ────────────────────────────────────────────

def parse_questions_from_message(content: str) -> list[dict]:
    """Extract top-level bullet-point questions from a bot message.

    Supports two formats:
      MCQ:   "* Question? (options: A, B, C)"
      Open:  "* Question?"

    Nested answer bullets (for example lines indented under a question) are
    ignored so they remain visible in the rendered markdown.
    """
    questions: list[dict] = []
    bullet_pattern = re.compile(r"^\s*[\*\-]\s+")

    for line in content.splitlines():
        if not bullet_pattern.match(line):
            continue

        q_text = bullet_pattern.sub("", line).strip()
        options_match = re.search(r"\s*\(options:\s*(.+?)\)\s*$", q_text)
        if options_match:
            options = [o.strip().strip("[]") for o in options_match.group(1).split(",")]
            q_clean = q_text[: options_match.start()].strip()
            questions.append({"text": q_clean, "options": options})
        else:
            questions.append({"text": q_text, "options": None})
    return questions


def contains_nested_bullets(content: str) -> bool:
    """Return True when the message contains indented bullet points."""
    return any(re.match(r"^\s+[\*\-]\s+", line) for line in content.splitlines())


def format_answers_as_message(questions: list[dict], answers: list[str]) -> str:
    """Combine collected Q&A pairs into the backend-expected plain-text format.

    Example output:
        * Which OS are you using?
            * Windows
        * In which room are you?
            * Others: R11
    """
    return "\n".join(
        f"* {q['text']}\n    * {option}: {detail}" if ": " in a and (option := a.split(": ", 1)[0]) and (detail := a.split(": ", 1)[1])
        else f"* {q['text']}\n    * {a}"
        for q, a in zip(questions, answers)
    )


def _is_other_option(option: str) -> bool:
    """Return True when the chosen option is an open-ended 'other' variant."""
    return bool(
        re.search(r"\b(other|others|andere[sr]?|sonstige[sr]?)\b", option, re.IGNORECASE)
    )


# ── Payload builders ─────────────────────────────────────────────────────────

def build_chat_payload(user_input: str) -> dict:
    return {
        "user_message": user_input,
        "history": st.session_state.chatbot_history,
        "user_email": st.session_state["email_input"],
        "matrikelnummer": st.session_state["matrikelnummer_input"],
        "issue_description": st.session_state.issue_description,
        "additional_info": st.session_state.additional_info,
        "priority": st.session_state.priority,
        "category": st.session_state.category,
        "additional_info_attempts": st.session_state.additional_info_attempts,
        "ask_issue_attempts": st.session_state.ask_issue_attempts,
        "intent": st.session_state.intent,
        "tutorial_attempts": st.session_state.tutorial_attempts,
        "ticket_id": st.session_state.get("ticket_id"),
        "full_conversation": st.session_state.full_conversation,
    }


def build_feedback_payload(message_index: int, helpful: bool, user_addendum: str = "") -> dict:
    message = st.session_state.messages[message_index]
    return {
        "user_message": "",
        "history": st.session_state.chatbot_history,
        "user_email": st.session_state["email_input"],
        "matrikelnummer": st.session_state["matrikelnummer_input"],
        "issue_description": st.session_state.issue_description,
        "additional_info": st.session_state.additional_info,
        "priority": st.session_state.priority,
        "category": st.session_state.category,
        "helpful": helpful,
        "solutions": message.get("solutions"),
        "bot_message": message["content"],
        "additional_info_attempts": st.session_state.additional_info_attempts,
        "ask_issue_attempts": st.session_state.ask_issue_attempts,
        "ticket_id": st.session_state.get("ticket_id"),
        "full_conversation": st.session_state.full_conversation,
        "user_addendum": user_addendum,
    }


def get_issue_summary() -> str:
    """Return the chatbot summary shown before ticket finalisation."""
    summary = (st.session_state.full_conversation or "").strip()
    if summary:
        return summary
    parts = []
    if st.session_state.issue_description:
        parts.append(st.session_state.issue_description)
    if st.session_state.additional_info:
        parts.append(", ".join(st.session_state.additional_info))
    return "\n".join(parts) or "(keine Zusammenfassung vorhanden)"


# ── Core message processing ───────────────────────────────────────────────────

TICKET_INTRO = (
    "Ich habe für Sie gerade ein Support-Ticket erstellt. "
    "Um Sie optimal zu unterstützen, beantworten Sie bitte folgende Fragen:"
)

def strip_redundant_ticket_intro(content: str) -> str:
    """Remove any duplicated filler text between the fixed ticket-intro
    sentence and the first bullet-point question that follows it.
    """
    idx = content.find(TICKET_INTRO)
    if idx == -1:
        return content
    start = idx + len(TICKET_INTRO)
    star_idx = content.find("*", start)
    if star_idx == -1:
        return content
    merged = content[:start] + "\n\n" + content[star_idx:]

    return re.sub(r"(?<!\n)\*\s", "\n* ", merged)

def apply_response_to_session(user_input: str, res_json: dict) -> None:
    answer = strip_redundant_ticket_intro(res_json["bot_response"])

    st.session_state.messages.append({"role": "user", "content": user_input})
    st.session_state.chatbot_history.append({"role": "user", "content": user_input})

    st.session_state.messages.append({
        "role": "assistant",
        "content": answer,
        "solutions": res_json.get("solutions") or [],
        "ui_flags": res_json.get("ui_flags", []),
    })
    st.session_state.chatbot_history.append({"role": "assistant", "content": answer})

    st.session_state.issue_description = res_json.get("issue_description", "")
    st.session_state.additional_info = res_json.get("additional_info", [])
    st.session_state.priority = res_json.get("priority", 0)
    st.session_state.additional_info_attempts = res_json.get("additional_info_attempts", 0)
    st.session_state.ask_issue_attempts = res_json.get("ask_issue_attempts", 0)
    st.session_state.category = res_json.get("category", "")
    st.session_state.full_conversation = res_json.get("full_conversation", "")
    st.session_state.intent = res_json.get("intent", "")
    st.session_state.tutorial_attempts = res_json.get("tutorial_attempts", 0)
    if "ticket_id" in res_json:
        st.session_state.ticket_id = res_json.get("ticket_id")

    # Never try to parse the bullet points of tutorials into a Q&A mode
    # in the first tutorial.
    if st.session_state.intent != "tutorial":
        # Detect bullet-point questions → enter guided Q&A mode
        questions = parse_questions_from_message(answer)
        if questions:
            st.session_state.pending_questions = questions
            st.session_state.current_question_idx = 0
            st.session_state.question_answers = []
            # Nach unten zum Fragen-Widget scrollen
            st.session_state["scroll_target"] = "question_widget_anchor"


def process_user_message(client: ChatClient, user_input: str) -> None:
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        placeholder = st.empty()
        placeholder.write(WAITING_MESSAGE)

        req = build_chat_payload(user_input)
        res_json = client.send_message(req)

        if "security" in res_json:
            placeholder.write("Deine Anfrage konnte aus Sicherheitsgründen nicht verarbeitet werden.")
            return

        answer = res_json["bot_response"]
        placeholder.markdown(answer)
        apply_response_to_session(user_input, res_json)


def process_solution_feedback(
    client: ChatClient,
    message_index: int,
    helpful: bool,
    user_addendum: str = "",
) -> str:
    message = st.session_state.messages[message_index]
    payload = build_feedback_payload(message_index, helpful, user_addendum=user_addendum)

    # If user says "No", just append message to ticket without parsing JSON response
    if not helpful:
        client.send_feedback(payload)
        message["solutions"] = []
        st.session_state.pending_ticket_confirmation = None
        st.session_state.show_ticket_addendum_form = False
        st.session_state["scroll_target"] = None
        return "Ich habe dein Feedback notiert und ein Support-Ticket erstellt. Ein Agent wird sich bald um dein Anliegen kümmern."

    # For "Yes" response, parse the JSON response
    res_json = client.send_feedback(payload)
    message["solutions"] = []
    return res_json.get("bot_response", "")


def start_ticket_confirmation(message_index: int) -> None:
    """Enter the summary confirmation step after an unhelpful solution."""
    st.session_state.pending_ticket_confirmation = message_index
    st.session_state.show_ticket_addendum_form = False
    st.session_state["scroll_target"] = "ticket_confirmation_anchor"


# ── Rendering ────────────────────────────────────────────────────────────────

def render_message_extras(message: dict, message_index: int, client: ChatClient) -> None:
    ui_flags = message.get("ui_flags", [])

    if "show_faq" in ui_flags:
        st.info("FAQ-Platzhalter: WLAN-Verbindung, Moodle-Login, Drucker im Poolraum, …")

    if "show_ticket_button" in ui_flags:
        st.button("Ticket erstellen", disabled=True, key=f"ticket_btn_{message_index}")

    if message.get("solutions") and st.session_state.pending_ticket_confirmation is None:
        col1, col2 = st.columns(2)

        with col1:
            if st.button("Ja", key=f"solution_yes_{message_index}"):
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": process_solution_feedback(client, message_index, True),
                })
                st.session_state.bot_thinking = True
                st.rerun()

        with col2:
            if st.button("Nein", key=f"solution_no_{message_index}"):
                start_ticket_confirmation(message_index)
                st.rerun()


def render_ticket_confirmation_widget(client: ChatClient) -> None:
    """Let the user confirm the issue summary or add free-text before finalising."""
    message_index = st.session_state.pending_ticket_confirmation
    if message_index is None:
        return

    with st.container(border=True):
        st.markdown("**Zusammenfassung deines Anliegens**")
        st.info(get_issue_summary())

        if st.session_state.show_ticket_addendum_form:
            st.markdown(
                '<div id="ticket_addendum_anchor"></div>',
                unsafe_allow_html=True,
            )

            addendum = st.text_area(
                "Ergänze hier weitere Informationen zu deinem Anliegen:",
                key="ticket_addendum_input",
                height=120,
            )
            if st.button("Ticket absenden", key="ticket_submit_with_addendum", use_container_width=True):
                if not addendum.strip():
                    st.error("Bitte gib eine Ergänzung ein oder bestätige die Zusammenfassung ohne Änderungen.")
                else:
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": process_solution_feedback(
                            client, message_index, False, user_addendum=addendum.strip()
                        ),
                    })
                    st.session_state.bot_thinking = True
                    st.rerun()
        else:
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Zusammenfassung bestätigen", key="ticket_confirm_summary", use_container_width=True):
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": process_solution_feedback(client, message_index, False),
                    })
                    st.session_state.bot_thinking = True
                    st.rerun()
            with col2:
                if st.button("Informationen ergänzen", key="ticket_show_addendum", use_container_width=True):
                    st.session_state.show_ticket_addendum_form = True
                    st.session_state["scroll_target"] = "ticket_addendum_anchor"
                    st.rerun()

        # Anchor am Ende des Widgets: ermöglicht gezieltes Scrollen beim Auftauchen.
        st.markdown(
            '<div id="ticket_confirmation_anchor"></div>',
            unsafe_allow_html=True,
        )


def render_chat_history(client: ChatClient) -> None:
    for i, message in enumerate(st.session_state.messages):
        with st.chat_message(message["role"]):
            parsed = parse_questions_from_message(message["content"])
            # Preserve nested answer bullets exactly as authored. Only rewrite
            # messages that contain simple top-level question bullets and no
            # indented sub-bullets.
            if parsed and not contains_nested_bullets(message["content"]):
                non_bullet_lines = [
                    line
                    for line in message["content"].split("\n")
                    if not re.match(r"^\s*[\*\-]\s+", line)
                ]
                display_text = "\n".join(non_bullet_lines + [f"* {q['text']}" for q in parsed])
            else:
                display_text = message["content"]
            st.markdown(display_text)
            render_message_extras(message, i, client)


def render_question_widget(client: ChatClient) -> None:
    """Step-by-step Q&A widget for pending bullet-point questions.

    Shows one question at a time:
      - MCQ  → radio buttons; selecting an "other" variant reveals a free-text field.
      - Open → text area.

    On the final question the user presses 'Senden'; all answers are then
    combined into a single message and queued for dispatch to the backend.
    The actual API call happens at the top level of run_app (via _ready_to_send)
    so that process_user_message renders outside this widget's container.
    """
    questions: list[dict] = st.session_state.pending_questions
    idx: int = st.session_state.current_question_idx

    if idx >= len(questions):
        return

    question = questions[idx]
    is_last = idx == len(questions) - 1
    total = len(questions)

    st.progress((idx + 1) / total, text=f"Frage {idx + 1} von {total}")

    with st.container(border=True):
        st.markdown(
            '<div id="question_widget_anchor"></div>',
            unsafe_allow_html=True,
        )
        st.markdown(f"**{question['text']}**")
        answer: str | None = None

        if question["options"]:
            selected: str | None = st.radio(
                "Wähle eine Option:",
                question["options"],
                key=f"mcq_{idx}",
                index=None,
            )
            other_detail = ""
            if selected and _is_other_option(selected):
                other_detail = st.text_input(
                    "Bitte genauer angeben:",
                    key=f"other_detail_{idx}",
                )
            if selected is not None:
                answer = f"{selected}: {other_detail}" if other_detail else selected
        else:
            open_text: str = st.text_area("Deine Antwort:", key=f"open_{idx}")
            if open_text and open_text.strip():
                answer = open_text.strip()

        btn_label = "Senden ✓" if is_last else "Weiter →"
        if st.button(btn_label, key=f"next_btn_{idx}", use_container_width=True):
            if answer is None:
                st.error("Bitte beantworte die Frage, bevor du fortfährst.")
            else:
                st.session_state.question_answers.append(answer)
                if is_last:
                    # Assemble the combined message and hand off to the send loop
                    st.session_state["_ready_to_send"] = format_answers_as_message(
                        questions, st.session_state.question_answers
                    )
                    st.session_state.pending_questions = []
                    st.session_state.current_question_idx = 0
                    st.session_state.question_answers = []
                else:
                    st.session_state.current_question_idx += 1
                st.rerun()


def run_app(client: ChatClient, *, mock_mode: bool = False) -> None:
    st.set_page_config(page_title="Support-Annahme über ZIM Helper", layout="centered")

    with st.sidebar:
        st.header("Einstellungen")
        if st.button("Neu starten", type="secondary"):
            reset_session_state()
            st.rerun()

    st.title("Support-Annahme über ZIM Helper")
    st.caption("Dein digitaler Assistent für Support-Anfragen")
    if mock_mode:
        st.caption("Mock-Modus: keine Backend- oder KI-Aufrufe.")

    st.subheader("Deine Kontaktdaten")
    st.text_input("E-Mail-Adresse *", key="email_input")
    st.text_input("Matrikelnummer *", key="matrikelnummer_input")
    st.divider()
    st.header("ZIM Helper")

    init_session_state()
    render_chat_history(client)

    # Priority 1: a finished Q&A round is ready — dispatch it to the backend.
    # process_user_message is called here (top level) so the in-progress
    # user/assistant messages render below the chat history, not inside the
    # question widget's bordered container.
    ready = st.session_state.get("_ready_to_send")
    if ready:
        st.session_state["_ready_to_send"] = None
        process_user_message(client, ready)
        st.session_state.bot_thinking = False
        st.rerun()

    # Priority 2: confirm issue summary before finalising the support ticket.
    elif st.session_state.pending_ticket_confirmation is not None:
        render_ticket_confirmation_widget(client)
        scroll_target = st.session_state.get("scroll_target")
        if scroll_target:
            _scroll_page_to_bottom(scroll_target)
            st.session_state["scroll_target"] = None

    # Priority 3: guide the user through pending questions one at a time.
    elif st.session_state.pending_questions:
        render_question_widget(client)
        scroll_target = st.session_state.get("scroll_target")
        if scroll_target:
            _scroll_page_to_bottom(scroll_target)
            st.session_state["scroll_target"] = None

    # Priority 4: normal freeform chat input.
    else:
        has_pending_solutions = any(msg.get("solutions") for msg in st.session_state.messages)
        chat_disabled = (
            st.session_state.bot_thinking
            or not are_form_fields_valid()
            or has_pending_solutions
            or st.session_state.pending_ticket_confirmation is not None
        )
        if user_input := st.chat_input(
            placeholder=(
                "Bitte E-Mail-Adresse und Matrikelnummer eingeben"
                if not are_form_fields_valid()
                else "Beschreibe dein Anliegen..."
            ),
            disabled=chat_disabled,
            on_submit=bot_starting_thinking,
        ):
            process_user_message(client, user_input)
            st.session_state.bot_thinking = False
            st.rerun()