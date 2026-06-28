"""Shared Streamlit chat UI used by the live app and the mock clone."""
import copy
import re

import streamlit as st

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
    "category": "",
}

WAITING_MESSAGE = '*:color[Bitte warten. Antwort wird generiert...]{foreground="#888888"}*'


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
        "category": st.session_state.category,
    }


def build_feedback_payload(message_index: int, helpful: bool) -> dict:
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
    }


def apply_response_to_session(user_input: str, res_json: dict) -> None:
    answer = res_json["bot_response"]

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


def process_user_message(client: ChatClient, user_input: str) -> None:
    with st.chat_message("user"):
        st.write(user_input)

    with st.chat_message("assistant"):
        placeholder = st.empty()
        placeholder.write(WAITING_MESSAGE)

        req = build_chat_payload(user_input)
        res_json = client.send_message(req)

        if "security" in res_json:
            placeholder.write("Deine Anfrage konnte aus Sicherheitsgründen nicht verarbeitet werden.")
            return

        answer = res_json["bot_response"]
        placeholder.write(answer)
        apply_response_to_session(user_input, res_json)


def process_solution_feedback(client: ChatClient, message_index: int, helpful: bool) -> str:
    message = st.session_state.messages[message_index]
    payload = build_feedback_payload(message_index, helpful)
    res_json = client.send_feedback(payload)
    message["solutions"] = []
    return res_json.get("bot_response", "")


def render_message_extras(message: dict, message_index: int, client: ChatClient) -> None:
    ui_flags = message.get("ui_flags", [])

    if "show_faq" in ui_flags:
        st.info("FAQ-Platzhalter: WLAN-Verbindung, Moodle-Login, Drucker im Poolraum, …")

    if "show_ticket_button" in ui_flags:
        st.button("Ticket erstellen", disabled=True, key=f"ticket_btn_{message_index}")

    if message.get("solutions"):
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
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": process_solution_feedback(client, message_index, False),
                })
                st.session_state.bot_thinking = True
                st.rerun()


def render_chat_history(client: ChatClient) -> None:
    for i, message in enumerate(st.session_state.messages):
        with st.chat_message(message["role"]):
            st.write(message["content"])
            render_message_extras(message, i, client)


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

    if user_input := st.chat_input(
        placeholder=(
            "Bitte E-Mail-Adresse und Matrikelnummer eingeben"
            if not are_form_fields_valid()
            else "Beschreibe dein Anliegen..."
        ),
        disabled=st.session_state.bot_thinking or not are_form_fields_valid(),
        on_submit=bot_starting_thinking,
    ):
        process_user_message(client, user_input)
        st.session_state.bot_thinking = False
        st.rerun()
