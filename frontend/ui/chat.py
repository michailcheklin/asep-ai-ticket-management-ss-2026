"""Shared Streamlit chat UI used by the live app and the mock clone."""
import copy
import os
import re

import requests
import streamlit as st
from streamlit.components.v1 import html

from frontend.clients.base import ChatClient
from frontend.ui.strings import t
from frontend.ui.qa_navigation import (
    apply_question_answer,
    can_go_back,
    contains_nested_bullets,
    format_answers_as_message,
    is_other_option,
    navigate_back,
    normalize_bullet_markers,
    parse_questions_from_message,
    split_stored_mcq_answer,
)

IDP_BASE_URL = os.getenv("IDP_BASE_URL", "http://localhost:4999")

INITIAL_STATES = {
    "messages": [
        {
            "role": "assistant",
            "content": "Hallo! Ich bin ZIM Helper. Worum geht es? Bitte das Anliegen kurz beschreiben.",
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
    "summary": "",
    "user_summary": "",
    # ── Ticket confirmation (frontend-only, before finalising support ticket) ──
    "pending_ticket_confirmation": None,  # message index with unhelpful solution feedback
    "show_ticket_addendum_form": False,
    "intent": "",
    "tutorial_attempts": 0,
    "graph_runs": 0,
    "is_complete": False,
    # ── Q&A widget state (frontend-only, never sent to the backend) ──────────
    "pending_questions": [],   # list of {text: str, options: list[str] | None}
    "current_question_idx": 0,
    "question_answers": [],    # answers collected so far in the current round
    "_ready_to_send": None,    # combined message text waiting to be dispatched
    "_qa_navigating": False,   # disables Q&A buttons during back/forward navigation
    "scroll_target": None,     # anchor id to scroll to after rerun
    "user_metadata": None,      # dict from IdP + browser UA, or None if not logged in
    "metadata_confirmed": False,   # True after user confirms browser-detected device/OS
    "_pending_first_message": None, # first user message held until metadata is confirmed
    "_last_audio_id": None,         # file_id of the last transcribed recording
}

def _waiting_message(lang: str) -> str:
    text = t("Bitte warten. Antwort wird generiert...", lang)
    return f'*:color[{text}]{{foreground="#888888"}}*'


def _lang() -> str:
    """Current UI/response language, detected from the user's Accept-Language header."""
    metadata = st.session_state.get("user_metadata") or {}
    return metadata.get("language", "de")


# ── User-Agent parsing ──────────────────────────────────────────────────────

def _parse_device_from_ua(ua: str) -> str:
    """Classify device type (Tablet/Mobile/Desktop) from User-Agent substrings."""
    ua_lower = ua.lower()
    if "ipad" in ua_lower or "tablet" in ua_lower:
        return "Tablet"
    if "iphone" in ua_lower or "mobi" in ua_lower or ("android" in ua_lower and "tablet" not in ua_lower):
        return "Mobile"
    return "Desktop"


def _parse_os_from_ua(ua: str) -> str:
    """Classify OS from User-Agent substrings; falls back to "Unbekannt" if unrecognized."""
    if "iPhone" in ua or "iPad" in ua:
        return "iOS"
    if "Windows" in ua:
        return "Windows"
    if "Android" in ua:
        return "Android"
    if "Macintosh" in ua or "Mac OS" in ua:
        return "macOS"
    if "Linux" in ua:
        return "Linux"
    return "Unbekannt"


def _parse_language_from_header(accept_language: str) -> str:
    """Extract the primary language tag from an Accept-Language header.

    Only "de"/"en" are supported UI languages; anything else falls back to "de".
    """
    primary = accept_language.split(",")[0].strip().split("-")[0].lower()
    return primary if primary in ("de", "en") else "de"


def _fetch_and_store_metadata() -> None:
    """Fetch user metadata from the IdP API and enrich with browser info."""
    # Only fetch once per session; Shibboleth login already ran before the chat page loaded.
    if st.session_state.get("user_metadata") is not None:
        return

    # No token means the user reached this page outside the Shibboleth login flow.
    token = st.query_params.get("session_token")
    if not token:
        return

    try:
        resp = requests.get(f"{IDP_BASE_URL}/api/userinfo", params={"token": token}, timeout=3)
        if resp.status_code != 200:
            return
        metadata = resp.json()
    except Exception:
        return

    # Device/OS aren't provided by the IdP, so derive them client-side from the request headers.
    ua = st.context.headers.get("User-Agent", "")
    metadata["device"] = _parse_device_from_ua(ua)
    metadata["os_name"] = _parse_os_from_ua(ua)
    metadata["language"] = _parse_language_from_header(st.context.headers.get("Accept-Language", ""))

    st.session_state["user_metadata"] = metadata

    # Pre-fill the (still-required) form fields so the user doesn't retype known IdP data.
    if metadata.get("email"):
        st.session_state["email_input"] = metadata["email"]
    if metadata.get("student_id"):
        st.session_state["student_id_input"] = metadata["student_id"]

    # Personalize the greeting with the user's first name, but only if the chat hasn't started yet.
    lang = metadata["language"]
    name = metadata.get("display_name", "").split()[0] if metadata.get("display_name") else ""
    if "messages" not in st.session_state:
        greeting = (
            t("Hallo {name}! Ich bin ZIM Helper. Worum geht es? Bitte das Anliegen kurz beschreiben.", lang).format(name=name)
            if name
            else t("Hallo! Ich bin ZIM Helper. Worum geht es? Bitte das Anliegen kurz beschreiben.", lang)
        )
        st.session_state["messages"] = [{"role": "assistant", "content": greeting}]


# ── Session state helpers ────────────────────────────────────────────────────

def init_session_state() -> None:
    for key, value in INITIAL_STATES.items():
        if key not in st.session_state:
            st.session_state[key] = copy.deepcopy(value)


def reset_session_state() -> None:
    """Clear chat history and unlock the input for a fresh start."""
    for key, value in INITIAL_STATES.items():
        if key == "messages":
            st.session_state[key] = st.session_state[key][:1]
        else:
            st.session_state[key] = copy.deepcopy(value)
    st.session_state["email_input"] = ""
    st.session_state["student_id_input"] = ""
    # Delete the ticket ID out of the frontend's session state completely
    # so that after the click on the "Neu starten" button the backend does not think
    # that a ticket still exists.
    #
    # Just setting the ticket ID to None or -1 would not have sufficed,
    # because the backend would think a ticket with ID None or -1 exists and then
    # try to do things with non-existant tickets,
    # instead of knowing that for the current conversation a ticket does not exist yet.
    st.session_state.pop('ticket_id', None)


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
    metadata = st.session_state.get("user_metadata")
    if metadata and metadata.get("role") != "student":
        return is_email_valid
    is_student_id_valid = bool(
        re.fullmatch(pattern=r"[0-9]+", string=st.session_state["student_id_input"])
    )
    return is_email_valid and is_student_id_valid


# ── Question parsing & formatting (see frontend.ui.qa_navigation) ─────────────


def clear_question_widget_keys(start_idx: int, total: int) -> None:
    """Drop Streamlit widget keys for questions at/after *start_idx*."""
    for i in range(start_idx, total):
        for prefix in ("mcq_", "other_detail_", "open_"):
            st.session_state.pop(f"{prefix}{i}", None)


# ── Payload builders ─────────────────────────────────────────────────────────

def _metadata_fields() -> dict:
    """Extract the fixed subset of client metadata sent to the backend on every request."""
    metadata = st.session_state.get("user_metadata") or {}
    return {
        "display_name": metadata.get("display_name", ""),
        "role": metadata.get("role", ""),
        "faculty": metadata.get("faculty", ""),
        "device": metadata.get("device", ""),
        "os_name": metadata.get("os_name", ""),
        "language": metadata.get("language", ""),
    }


def build_chat_payload(user_input: str) -> dict:
    return {
        "user_message": user_input,
        "history": st.session_state.chatbot_history,
        "user_email": st.session_state["email_input"],
        "student_id": st.session_state["student_id_input"],
        "issue_description": st.session_state.issue_description,
        "additional_info": st.session_state.additional_info,
        "priority": st.session_state.priority,
        "category": st.session_state.category,
        "additional_info_attempts": st.session_state.additional_info_attempts,
        "ask_issue_attempts": st.session_state.ask_issue_attempts,
        "intent": st.session_state.intent,
        "tutorial_attempts": st.session_state.tutorial_attempts,
        "graph_runs": st.session_state.graph_runs,
        "ticket_id": st.session_state.get("ticket_id"),
        "summary": st.session_state.summary,
        "user_summary": st.session_state.user_summary,
        **_metadata_fields(),
    }


def build_feedback_payload(message_index: int, helpful: bool, user_addendum: str = "") -> dict:
    message = st.session_state.messages[message_index]
    return {
        "user_message": "",
        "history": st.session_state.chatbot_history,
        "user_email": st.session_state["email_input"],
        "student_id": st.session_state["student_id_input"],
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
        "summary": st.session_state.summary,
        "user_summary": st.session_state.user_summary,
        "user_addendum": user_addendum,
        **_metadata_fields(),
    }


def get_issue_summary() -> str:
    """Return the issue summary shown before ticket finalisation.

    Prefers user_summary — the same LLM-written summary as state["summary"],
    just in the user's own language instead of the German that "summary"
    always uses (that field also feeds the Zammad ticket title/body for the
    support team, so it can't simply be localized itself). Falls back to a
    plain issue_description/additional_info listing for the early turns
    before any summary has been generated yet.
    """
    user_summary = (st.session_state.user_summary or "").strip()
    if user_summary:
        return user_summary
    parts = []
    if st.session_state.issue_description:
        parts.append(st.session_state.issue_description)
    if st.session_state.additional_info:
        parts.append("\n".join(f"- {info}" for info in st.session_state.additional_info))
    # "\n\n" so Streamlit's markdown renderer treats the bullet list as its
    # own block instead of collapsing a single "\n" into a plain space.
    return "\n\n".join(parts) or t("(keine Zusammenfassung vorhanden)", _lang())


# ── Core message processing ───────────────────────────────────────────────────

TICKET_INTRO_VARIANTS = (
    "Ich habe gerade ein Support-Ticket erstellt. "
    "Für eine optimale Bearbeitung bitte die folgenden Fragen beantworten:",
    "I've just created a support ticket. To process it optimally, please answer the following questions:",
)

def strip_redundant_ticket_intro(content: str) -> str:
    """Remove any duplicated filler text between the fixed ticket-intro
    sentence and the first bullet-point question that follows it.
    """
    content = normalize_bullet_markers(content)
    idx = -1
    intro = ""
    for variant in TICKET_INTRO_VARIANTS:
        idx = content.find(variant)
        if idx != -1:
            intro = variant
            break
    if idx == -1:
        return content
    start = idx + len(intro)
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
    st.session_state.summary = res_json.get("summary", "")
    st.session_state.user_summary = res_json.get("user_summary", "")
    st.session_state.intent = res_json.get("intent", "")
    st.session_state.tutorial_attempts = res_json.get("tutorial_attempts", 0)
    st.session_state.graph_runs = res_json.get("graph_runs", 0)
    st.session_state.is_complete = res_json.get("is_complete", False)


    if "ticket_id" in res_json:
        st.session_state.ticket_id = res_json.get("ticket_id")

    # Skip question parsing for tutorial responses — their bullet points
    # are instructional steps, not questions for the user to answer
    is_tutorial_response = (
        st.session_state.get("intent") == "tutorial"
        and st.session_state.get("tutorial_attempts", 0) > 0
    )
    if not is_tutorial_response:
        questions = parse_questions_from_message(answer)
        if questions:
            st.session_state.pending_questions = questions
            st.session_state.current_question_idx = 0
            st.session_state.question_answers = []
            st.session_state["_qa_navigating"] = False
            st.session_state["scroll_target"] = "question_widget_anchor"


def process_user_message(client: ChatClient, user_input: str) -> None:
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        placeholder = st.empty()
        placeholder.write(_waiting_message(_lang()))

        req = build_chat_payload(user_input)
        res_json = client.send_message(req)

        if "security" in res_json:
            placeholder.write(t("Die Anfrage konnte aus Sicherheitsgründen nicht verarbeitet werden.", _lang()))
            return

        answer = res_json["bot_response"]
        placeholder.markdown(answer, unsafe_allow_html=True)
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
        metadata = st.session_state.get("user_metadata") or {}
        lang = metadata.get("language", "de")
        first_name = metadata.get("display_name", "").split()[0] if metadata.get("display_name") else ""
        greeting = t("Danke, {name}!", lang).format(name=first_name) if first_name else t("Danke!", lang)
        return t(
            "{greeting} Das Feedback wurde notiert und ein Support-Ticket erstellt. Ein Agent kümmert sich bald um das Anliegen.",
            lang,
        ).format(greeting=greeting)

    # For "Yes" response, parse the JSON response
    res_json = client.send_feedback(payload)
    message["solutions"] = []
    st.session_state.is_complete = True
    return res_json.get("bot_response", "")


def start_ticket_confirmation(message_index: int) -> None:
    """Enter the summary confirmation step after an unhelpful solution."""
    st.session_state.pending_ticket_confirmation = message_index
    st.session_state.show_ticket_addendum_form = False
    st.session_state["scroll_target"] = "ticket_confirmation_anchor"


# ── Rendering ────────────────────────────────────────────────────────────────

def render_message_extras(message: dict, message_index: int, client: ChatClient) -> None:
    ui_flags = message.get("ui_flags", [])
    lang = _lang()

    if "show_faq" in ui_flags:
        st.info(t("FAQ-Platzhalter: WLAN-Verbindung, Moodle-Login, Drucker im Poolraum, …", lang))

    if "show_ticket_button" in ui_flags:
        st.button(t("Ticket erstellen", lang), disabled=True, key=f"ticket_btn_{message_index}")

    if message.get("solutions") and st.session_state.pending_ticket_confirmation is None:
        col1, col2 = st.columns(2)

        with col1:
            if st.button(t("Ja", lang), key=f"solution_yes_{message_index}"):
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": process_solution_feedback(client, message_index, True),
                })
                st.session_state.bot_thinking = True
                st.rerun()

        with col2:
            if st.button(t("Nein", lang), key=f"solution_no_{message_index}"):
                start_ticket_confirmation(message_index)
                st.rerun()


def render_ticket_confirmation_widget(client: ChatClient) -> None:
    """Let the user confirm the issue summary or add free-text before finalising."""
    message_index = st.session_state.pending_ticket_confirmation
    if message_index is None:
        return

    lang = _lang()
    with st.container(border=True):
        st.markdown(t("**Zusammenfassung des Anliegens**", lang))
        st.info(get_issue_summary())

        if st.session_state.show_ticket_addendum_form:
            st.markdown(
                '<div id="ticket_addendum_anchor"></div>',
                unsafe_allow_html=True,
            )

            addendum = st.text_area(
                t("Hier weitere Information zum Anliegen ergänzen:", lang),
                key="ticket_addendum_input",
                height=120,
            )
            if st.button(t("Ticket absenden", lang), key="ticket_submit_with_addendum", use_container_width=True):
                if not addendum.strip():
                    st.error(t("Bitte eine Ergänzung ein oder die Zusammenfassung ohne Änderungen bestätigen.", lang))
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
                if st.button(t("Zusammenfassung bestätigen", lang), key="ticket_confirm_summary", use_container_width=True):
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": process_solution_feedback(client, message_index, False),
                    })
                    st.session_state.bot_thinking = True
                    st.rerun()
            with col2:
                if st.button(t("Informationen ergänzen", lang), key="ticket_show_addendum", use_container_width=True):
                    st.session_state.show_ticket_addendum_form = True
                    st.session_state["scroll_target"] = "ticket_addendum_anchor"
                    st.rerun()

        # Anchor at the end of the widget: enables targeted scrolling when it appears.
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
            st.markdown(display_text, unsafe_allow_html=True)
            render_message_extras(message, i, client)


def render_metadata_confirmation() -> None:
    """Let the user confirm or correct browser-detected device and OS.

    Shown after the first message is sent. On confirmation the held
    message is released for dispatch to the backend.
    """
    metadata = st.session_state.get("user_metadata")
    if not metadata:
        return

    lang = metadata.get("language", "de")
    yes_no = [t("Ja", lang), t("Nein", lang)]
    with st.container(border=True):
        st.markdown(t("**Erkannte Geräteinformationen**\n", lang))
        st.markdown(t(
            "Der Browser hat diese Informationen automatisch bereitgestellt. Dadurch lässt sich besser nachvollziehen, unter welchen Bedingungen das Problem auftritt.",
            lang,
        ))

        device_correct = st.radio(
            t("Bezieht sich das Anliegen auf ein **{device}**-Gerät?", lang).format(
                device=metadata.get("device", "Unbekannt")
            ),
            yes_no,
            key="confirm_device",
            index=None,
        )
        custom_device = ""
        if device_correct == t("Nein", lang):
            custom_device = st.text_input(t("Welches Gerät wird verwendet?", lang), key="custom_device_input")

        os_correct = st.radio(
            t("Bezieht sich das Anliegen auf **{os_name}**?", lang).format(
                os_name=metadata.get("os_name", "Unbekannt")
            ),
            yes_no,
            key="confirm_os",
            index=None,
        )
        custom_os = ""
        if os_correct == t("Nein", lang):
            custom_os = st.text_input(t("Welches Betriebssystem wird verwendet?", lang), key="custom_os_input")

        if st.button(t("Bestätigen", lang), key="confirm_metadata_btn", use_container_width=True):
            if device_correct is None or os_correct is None:
                st.error(t("Bitte beide Fragen beantworten.", lang))
                return
            if device_correct == t("Nein", lang) and not custom_device.strip():
                st.error(t("Bitte das Gerät angeben.", lang))
                return
            if os_correct == t("Nein", lang) and not custom_os.strip():
                st.error(t("Bitte das Betriebssystem angeben.", lang))
                return

            if device_correct == t("Nein", lang):
                metadata["device"] = custom_device.strip()
            if os_correct == t("Nein", lang):
                metadata["os_name"] = custom_os.strip()

            st.session_state["metadata_confirmed"] = True
            st.session_state["_ready_to_send"] = st.session_state.pop("_pending_first_message", None)
            st.rerun()


def render_question_widget(client: ChatClient) -> None:
    """Step-by-step Q&A widget for pending bullet-point questions.

    Shows one question at a time:
      - MCQ  → radio buttons; selecting an "other" variant reveals a free-text field.
      - Open → text area.

    Users can step back to earlier questions (except the first) to correct an
    answer. Changing an answer clears dependent later answers; leaving it
    unchanged keeps them.

    On the final question the user presses 'Senden'; all answers are then
    combined into a single message and queued for dispatch to the backend.
    The actual API call happens at the top level of run_app (via _ready_to_send)
    so that process_user_message renders outside this widget's container.
    """
    questions: list[dict] = st.session_state.pending_questions
    idx: int = st.session_state.current_question_idx
    answers: list[str] = st.session_state.question_answers

    if idx >= len(questions):
        return

    question = questions[idx]
    is_last = idx == len(questions) - 1
    total = len(questions)
    show_back = can_go_back(idx)
    stored_answer = answers[idx] if idx < len(answers) else None
    lang = _lang()

    st.progress((idx + 1) / total, text=t("Frage {idx} von {total}", lang).format(idx=idx + 1, total=total))

    with st.container(border=True):
        st.markdown(
            '<div id="question_widget_anchor"></div>',
            unsafe_allow_html=True,
        )
        st.markdown(f"**{question['text']}**")
        answer: str | None = None

        if question["options"]:
            radio_key = f"mcq_{idx}"
            detail_key = f"other_detail_{idx}"
            selected_option, other_detail_default = split_stored_mcq_answer(
                stored_answer, question["options"]
            )
            # Seed widget state so a revisited question shows the prior choice.
            if selected_option is not None and radio_key not in st.session_state:
                st.session_state[radio_key] = selected_option
            if other_detail_default and detail_key not in st.session_state:
                st.session_state[detail_key] = other_detail_default

            selected: str | None = st.radio(
                t("Bitte eine Option wählen :", lang),
                question["options"],
                key=radio_key,
                index=None,
            )
            other_detail = ""
            if selected and is_other_option(selected):
                other_detail = st.text_input(
                    t("Bitte genauer angeben:", lang),
                    key=detail_key,
                )
            if selected is not None:
                answer = f"{selected}: {other_detail}" if other_detail else selected
        else:
            open_key = f"open_{idx}"
            if stored_answer is not None and open_key not in st.session_state:
                st.session_state[open_key] = stored_answer

            open_text: str = st.text_area(t("Antwort:", lang), key=f"open_{idx}")
            if open_text and open_text.strip():
                answer = open_text.strip()

        btn_label = t("Senden ✓", lang) if is_last else t("Weiter →", lang)
        if show_back:
            back_col, next_col = st.columns(2)
            with back_col:
                back_clicked = st.button(
                    t("← Zurück", lang),
                    key=f"back_btn_{idx}",
                    use_container_width=True,
                    type="secondary",
                    disabled=bool(st.session_state.get("_qa_navigating")),
                )
            with next_col:
                next_clicked = st.button(
                    btn_label,
                    key=f"next_btn_{idx}",
                    use_container_width=True,
                    disabled=bool(st.session_state.get("_qa_navigating")),
                )
        else:
            back_clicked = False
            next_clicked = st.button(
                btn_label,
                key=f"next_btn_{idx}",
                use_container_width=True,
                disabled=bool(st.session_state.get("_qa_navigating")),
            )

        # Prefer Back over Weiter if both somehow fire in one run.
        if back_clicked and show_back and not st.session_state.get("_qa_navigating"):
            st.session_state["_qa_navigating"] = True
            new_idx, new_answers = navigate_back(idx, answers)
            st.session_state.current_question_idx = new_idx
            st.session_state.question_answers = new_answers
            st.session_state["scroll_target"] = "question_widget_anchor"
            st.session_state["_qa_navigating"] = False
            st.rerun()
        elif next_clicked and not st.session_state.get("_qa_navigating"):
            if answer is None:
                st.error(t("Bitte die Frage beantworten, bevor es weitergeht.", lang))
            else:
                st.session_state["_qa_navigating"] = True
                answer_changed = not (idx < len(answers) and answers[idx] == answer)
                new_idx, new_answers, is_complete = apply_question_answer(
                    idx, answers, answer, is_last=is_last
                )
                if answer_changed:
                    clear_question_widget_keys(idx + 1, total)

                if is_complete:
                    st.session_state["_ready_to_send"] = format_answers_as_message(
                        questions, new_answers
                    )
                    st.session_state.pending_questions = []
                    st.session_state.current_question_idx = 0
                    st.session_state.question_answers = []
                    clear_question_widget_keys(0, total)
                else:
                    st.session_state.current_question_idx = new_idx
                    st.session_state.question_answers = new_answers
                    st.session_state["scroll_target"] = "question_widget_anchor"

                st.session_state["_qa_navigating"] = False
                st.rerun()


def run_app(client: ChatClient, *, mock_mode: bool = False) -> None:
    st.set_page_config(page_title="Support-Annahme über ZIM Helper", layout="centered")

    _fetch_and_store_metadata()

    metadata = st.session_state.get("user_metadata")
    lang = _lang()

    with st.sidebar:
        st.header(t("Einstellungen", lang))
        if metadata:
            role_label = t("Student", lang) if metadata.get("role") == "student" else t("Mitarbeiter", lang)
            st.markdown(t("**Eingeloggt als:** {name}", lang).format(name=metadata.get("display_name", "")))
            st.caption(f"{role_label} · {metadata.get('faculty', '')}")
            if metadata.get("device") or metadata.get("os_name"):
                st.caption(f"{metadata.get('device', '')} · {metadata.get('os_name', '')}")
        if st.button(t("Neu starten", lang), type="secondary"):
            reset_session_state()
            st.rerun()

    st.title(t("Support-Annahme über ZIM Helper", lang))
    st.caption(t("Digitaler Assistent für Support-Anfragen", lang))
    if mock_mode:
        st.caption(t("Mock-Modus: keine Backend- oder KI-Aufrufe.", lang))

    st.subheader(t("Kontaktdaten", lang))
    is_logged_in = metadata is not None
    st.text_input(t("E-Mail-Adresse *", lang), key="email_input", disabled=is_logged_in)
    if not metadata or metadata.get("role") == "student":
        st.text_input(t("Matrikelnummer *", lang), key="student_id_input", disabled=is_logged_in)
    st.divider()
    st.header(t("ZIM Helper", lang))

    init_session_state()
    render_chat_history(client)

    metadata_needs_confirm = metadata and not st.session_state.get("metadata_confirmed")

    # Priority 0: first message sent — confirm metadata before dispatching to backend.
    if metadata_needs_confirm and st.session_state.get("_pending_first_message"):
        render_metadata_confirmation()
        st.chat_input(placeholder=t("Bitte zuerst die Geräteinformationen bestätigen.", lang), disabled=True)
        return

    # Priority 1: a finished Q&A round or released first message is ready.
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

    # Priority 4: normal freeform chat input, with the audio recorder below it.
    else:
        has_pending_solutions = any(msg.get("solutions") for msg in st.session_state.messages)
        chat_disabled = (
            st.session_state.bot_thinking
            or not are_form_fields_valid()
            or has_pending_solutions
            or st.session_state.pending_ticket_confirmation is not None
            or st.session_state.is_complete
        )
        placeholder = (
            t("Das Gespräch ist abgeschlossen — bitte über 'Neu starten' ein neues Anliegen beginnen.", lang)
            if st.session_state.is_complete
            else t("Bitte E-Mail-Adresse und Matrikelnummer eingeben", lang)
            if not are_form_fields_valid()
            else t("Anliegen beschreiben...", lang)
        )

        # A placeholder container reserves the text field's visual position
        # above the audio recorder; it's filled in further down. This lets
        # the audio widget + transcription run (and write to
        # session_state["chat_text_input"]) *before* the text_input is
        # actually instantiated below - Streamlit forbids writing to a
        # widget's session-state key after that widget has been created in
        # the same run - while still rendering the recorder underneath.
        text_container = st.container()
        recording = st.audio_input(t("Aufnehmen", lang), disabled=chat_disabled)

        if recording is not None and recording.file_id != st.session_state.get("_last_audio_id"):
            st.session_state["_last_audio_id"] = recording.file_id
            with st.spinner(t("Wird transkribiert...", lang)):
                result = client.transcribe_audio(recording.getvalue(), lang)
            st.session_state["chat_text_input"] = result.get("text", "")
            st.rerun()

        with text_container:
            with st.form("chat_form", clear_on_submit=True, border=False):
                form_col_input, form_col_submit = st.columns([5, 1])
                user_input = form_col_input.text_input(
                    placeholder,
                    key="chat_text_input",
                    disabled=chat_disabled,
                    label_visibility="collapsed",
                )
                submitted = form_col_submit.form_submit_button(t("Senden", lang), disabled=chat_disabled)

        if submitted and user_input:
            bot_starting_thinking()
            if metadata_needs_confirm:
                st.session_state["_pending_first_message"] = user_input
                st.rerun()
            else:
                process_user_message(client, user_input)
                st.session_state.bot_thinking = False
                st.rerun()