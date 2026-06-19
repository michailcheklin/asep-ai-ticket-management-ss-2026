"""Streamlit frontend; BACKEND_URL defaults to http://backend_app:8000 inside Docker."""
import os
import streamlit as st
import re
import requests
from requests import Response, JSONDecodeError

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/")
ZAMMAD_UI_URL = os.getenv("ZAMMAD_UI_URL", "http://localhost:8080").rstrip("/")

# Timeout for every AI request (20 minutes).
# Long conversations require significantly more processing time.
AI_COMMUNICATION_TIMEOUT_IN_SECONDS: int = 1200

st.set_page_config(page_title="Support-Annahme über ZIM Helper", layout="centered")

st.title("Support-Annahme über ZIM Helper")
st.caption("Dein digitaler Assistent für Support-Anfragen")
st.subheader("Deine Kontaktdaten")
email = st.text_input("E-Mail-Adresse *", key="email_input" )
matrikelnummer = st.text_input("Matrikelnummer *",  key="matrikelnummer_input" )
st.divider()
st.header("ZIM Helper")


# Initialize all session state values when the chat interface is opened
# for the first time.
initial_states = {

    # Initial assistant message
    "messages": [
        {
            "role": "assistant",
            "content": "Hallo! Ich bin ZIM Helper. Erzähl mir bitte von deinem Anliegen."
        }
    ],

    # Controls whether the chat input is disabled while
    # the assistant is generating a response.
    "bot_thinking": False,

    # Conversation history sent to the backend to preserve context.
    "chatbot_history": [],

    # Stores the extracted issue description across requests.
    "issue_description": "",

    # Stores additional extracted information for future requests.
    "additional_info": [],

    # Stores the calculated ticket priority.
    "priority": 0,
}

# Initialize missing session state entries.
for key, value in initial_states.items():
    if key not in st.session_state:
        st.session_state[key] = value


def bot_starting_thinking() -> None:
    """
    Disable the chat input while the assistant is generating a response.
    """
    st.session_state.bot_thinking = True


def are_form_fields_valid() -> bool:
    """
    Validate the required contact information.

    Returns True only if the email address has a valid format
    and the matriculation number consists of digits only.
    """
    is_email_valid = bool(re.fullmatch(pattern=r"[a-zA-Z0-9\._-]+@[a-zA-Z0-9\._-]+\.[a-zA-Z0-9\._-]+", string=st.session_state["email_input"]))
    is_matrikelnummer_valid = bool(re.fullmatch(pattern=r"[0-9]+", string=st.session_state["matrikelnummer_input"]))

    return is_email_valid and is_matrikelnummer_valid


def process_user_message(user_input: str) -> None:
    """
    Process a user message.

    Sends the current conversation state to the backend,
    updates the UI with the assistant response and synchronizes
    the frontend state with the backend state.
    """

    #
    with st.chat_message("user"):
        st.write(user_input)

    with st.chat_message("assistant"):

        # Display a temporary status message while waiting for the backend.
        placeholder = st.empty()
        placeholder.write('*:color[Bitte warten. Antwort wird generiert...]{foreground="#888888"}*')

        # Build the request payload containing the current conversation state.
        req = {
            "user_message": user_input,
            "history": st.session_state.chatbot_history,
            "user_email": st.session_state["email_input"],
            "matrikelnummer": st.session_state["matrikelnummer_input"],
            "issue_description": st.session_state.issue_description,
            "additional_info": st.session_state.additional_info,
            "priority": st.session_state.priority,

        }
        print(f"Sending the request to the chatbot with {str(req)}")
        # Send the request to the backend.
        res = requests.post(
            url=f"{BACKEND_URL}/chat",
            json=req,
            timeout=AI_COMMUNICATION_TIMEOUT_IN_SECONDS,
        )

        try:
            # Try to parse the backend response as JSON.
            res_json = res.json()
        except JSONDecodeError:
            # Fallback in case the backend returns a plain text error
            # instead of a JSON response (e.g. when SAIA is unavailable).
            res_json = {
                "bot_response": res.text,
                "user_email": st.session_state["email_input"],
                "matrikelnummer": st.session_state["matrikelnummer_input"],
                "issue_description": st.session_state.issue_description,
                "additional_info": st.session_state.additional_info,
                "needs_additional_info": False,
                "priority": st.session_state.priority,
                "is_complete": False,
                "solutions": []
            }

        # Continue only if the backend did not detect a prompt safety violation.
        if "security" not in res_json:
            print("Prompt Safety Check passed!")

            answer = res_json["bot_response"]
            placeholder.write(answer)

            st.session_state.messages.append({
                "role": "user",
                "content": user_input,
            })
            st.session_state.chatbot_history.append({
                "role": "user",
                "content": user_input,
            })

            st.session_state.messages.append({
                "role": "assistant",
                "content": answer,
                "solutions": res_json.get("solutions")
            })

            st.session_state.chatbot_history.append({
                "role": "assistant",
                "content": answer
            })

            # Synchronize the frontend state with the backend state.
            st.session_state.issue_description = res_json.get("issue_description", "")
            st.session_state.additional_info = res_json.get("additional_info", [])
            st.session_state.priority = res_json.get("priority", 0)

        else:
            print("Prompt Safety Check failed!")


def process_solution_feedback(message_index: int, helpful: bool):
    """
    Process the user's feedback on the suggested solutions.

    If the solution was helpful, the conversation ends.
    Otherwise, the backend creates a support ticket and returns
    a confirmation message.
    """
    message = st.session_state.messages[message_index]

    # Build the request payload for the solution feedback endpoint.
    payload = {
        "user_message": "",
        "history": st.session_state.chatbot_history,
        "user_email": st.session_state["email_input"],
        "matrikelnummer": st.session_state["matrikelnummer_input"],
        "issue_description": st.session_state.issue_description,
        "additional_info": st.session_state.additional_info,
        "priority": st.session_state.priority,
        "helpful": helpful,
        "solutions": message.get("solutions"),
        "message": message["content"],
    }

    for key, value in payload.items():
        print(f"[Debug]: {key}: {value}")

    # Send the feedback to the backend.
    res = requests.post(
        f"{BACKEND_URL}/solution-feedback",
        json=payload,
        timeout=AI_COMMUNICATION_TIMEOUT_IN_SECONDS
    ).json()

    # Remove the solutions from the message so the feedback buttons
    # are not rendered again after the next rerun.
    message["solutions"] = []

    return res.get("bot_response")

# Render the complete chat history.
for i, message in enumerate(st.session_state.messages):
    with st.chat_message(message["role"]):
        st.write(message["content"])

        # Solution messages display feedback buttons.
        # Once feedback is submitted, the solutions list is cleared
        # while the message itself remains visible in the chat history.
        if message.get("solutions"):
            col1, col2 = st.columns(2)

            with col1:
                if st.button("Ja"): # Solution was helpful.
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": process_solution_feedback(i, True)
                    })
                    st.session_state.bot_thinking = True # Lock the chat because the conversation has ended.
                    st.rerun()
                    # possible point to place tag endpoint in the future
            with col2:
                if st.button("Nein"): # Solution was not helpful.
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": process_solution_feedback(i, False)
                    })
                    st.session_state.bot_thinking = True # s.o.
                    st.rerun()

# The user can only send messages after entering a valid
# email address and matriculation number. Otherwise a ticket
# could not be assigned to the correct person.
#
# While the assistant is generating a response, the chat input
# remains disabled.
if user_input:= st.chat_input(
    placeholder = "Bitte E-Mail-Adresse und Matrikelnummer eingeben" if not are_form_fields_valid()
    else "Beschreibe dein Anliegen...",
    disabled=st.session_state.bot_thinking or not are_form_fields_valid(),
    on_submit=bot_starting_thinking
):
    process_user_message(user_input)

    # Re-enable the chat input after the assistant has responded.
    st.session_state.bot_thinking = False
    st.rerun()
