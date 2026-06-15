"""Streamlit-Frontend; BACKEND_URL http://backend_app:8000 in Docker."""
import os
import streamlit as st
import re
import requests
from requests import Response


# SPÄTERE BACKEND-/ZAMMAD-ANBINDUNG
# Aktuell auskommentiert, da zunächst nur die Chatbot-
# Oberfläche entwickelt wird. Man könnte es aber später nutzen,
# um automatisch Tickets in Zammad anzulegen.
# Die KI Anbindungen kommt dann natürlich auch noch später.
# from zammad_endpoints import create_ticket_by_user_email
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/")
ZAMMAD_UI_URL = os.getenv("ZAMMAD_UI_URL", "http://localhost:8080").rstrip("/")

# Timeout bei jeder KI-Anfrage auf 20 Minuten gesetzt,
# denn die Verarbeitung der Prompts erfordert insbesondere
# mit langen Chatverläufen viel Rechenleistung
AI_COMMUNICATION_TIMEOUT_IN_SECONDS:int = 1200

st.set_page_config(page_title="Support-Annahme über ZIM Helper", layout="centered")

st.title("Support-Annahme über ZIM Helper")
st.caption("Dein digitaler Assistent für Support-Anfragen")

st.subheader("Deine Kontaktdaten")

email = st.text_input("E-Mail-Adresse *", key="email_input" )
matrikelnummer = st.text_input("Matrikelnummer *",  key="matrikelnummer_input" )

st.divider()

st.header("ZIM Helper")


# Diese States werden beim ersten Öffnen des Chat-Interfaces gesetzt
initial_states = {
    # Erste Nachricht
    "messages":[
        {
            "role": "assistant",
            "content": "Hallo! Ich bin ZIM Helper. Erzähl mir bitte von deinem Anliegen."
        }
    ],

    # Mithilfe dieses State-Keys wird die Sperrung des Chatfensters gesteuert.
    "bot_thinking":False,

    # Interne History für Ollama, damit der Kontext
    # für zukünftige Chatnachrichten verwendet werden kann
    "chatbot_history":[],

    # Hier wird die Information, die der Bot aus der Benutzernachricht extrahieren konnte
    # als Text gespeichert
    "issue_description":"",

    # Hier werden die zusätzlichen Infos, die das LLM extrahieren konnte,
    # gespeichert, damit diese bei nachfolgenden Anfragen verwendet werden können
    "additional_info":[],

    # Hier wird die Priorität gespeichert, damit diese nicht
    # über Nachrichten hinweg verloren geht
    "priority":0,

}

for key, value in initial_states.items():
    if key not in st.session_state:
        st.session_state[key] = value




def bot_starting_thinking() -> None:
    """
    Diese Methode wird aufgerufen, sobald der Kunde die Chatnachricht abgeschickt hat,
    damit das Chatfenster während der Generierung der Bot-Antwort gesperrt werden kann.
    """
    st.session_state.bot_thinking = True


# Bilde die Darstellung des Chatfensters
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.write(message["content"])

# Prüfung, ob eine gültige E-Mail-Adresse und eine
# gültige Matrikelnummer (Nur Zahlen) eingegeben wurde

def all_form_fields_valid():

    is_email_valid = bool(re.fullmatch(pattern=r"[a-zA-Z0-9\._-]+@[a-zA-Z0-9\._-]+\.[a-zA-Z0-9\._-]+", string=st.session_state["email_input"]))
    is_matrikelnummer_valid = bool(re.fullmatch(pattern=r"[0-9]+", string=st.session_state["matrikelnummer_input"]))

    return is_email_valid and is_matrikelnummer_valid

# Ist die Matrikelnummer oder die E-Mail-Adresse
# ungültig, kann der Benutzer keine Nachrichten an den Chatbot schreiben
# denn sonst kann ein mögliches Ticket keiner Person zugeordnet werden
# und das ZIM-Team kann keine Nachfragen per E-Mail stellen
# Wenn Nutzer nach Eingabe der E-Mail-Adresse und der Matrikelnummer
# etwas in den Chat eintippt, beginnt die Generierung der Antwort auf die Eingabe des Nutzers.
# Direkt nach der Eingabe wird das Chatfenster gesperrt, bis der Bot geantwortet hat (s. Methode bot_starting_thinking()).
if user_input:= st.chat_input(
    placeholder = "Bitte E-Mail-Adresse und Matrikelnummer eingeben" if not all_form_fields_valid()
    else "Beschreibe dein Anliegen...",
    disabled=st.session_state.bot_thinking or not all_form_fields_valid(),
    on_submit=bot_starting_thinking
):


    with st.chat_message("user"):
        st.write(user_input)
        user_input_history_entry = {"role": "user", "content": user_input}
        st.session_state.messages.append(user_input_history_entry)


    with st.chat_message("assistant"):
        # Hier wird die Bot-Antwort generiert. Während die Antwort generiert wird,
        # wird ein grauer kursiver Platzhaltertext bei der Bot-Antwort erscheinen, bis
        # der Bot geantwortet hat.
        st.write('*:color[Bitte warten. Antwort wird generiert...]{foreground="#888888"}*')
        json_body_for_request = {
                "user_message": user_input,
                "history": st.session_state.chatbot_history,
                "user_email": st.session_state["email_input"],
                "matrikelnummer": st.session_state["matrikelnummer_input"],
                "issue_description": st.session_state.issue_description,
                "additional_info": st.session_state.additional_info,
                "priority": st.session_state.priority,

            }

        print(f"Sending the request to the chatbot with {str(json_body_for_request)}")

        bot_answer_http_response:Response = requests.post(
            url=f"{BACKEND_URL}/chat",
            json=json_body_for_request,
            timeout=AI_COMMUNICATION_TIMEOUT_IN_SECONDS,
        )

        print(f"The HTTP response: {str(bot_answer_http_response)}")

        # Sobald der Bot geantwortet hat, werden die Informationen aus dem JSON-Objekt
        # womit auf den POST-Request geantwortet wurde, extrahiert
        bot_answer_http_response_json: dict ={}
        try:
            bot_answer_http_response_json = bot_answer_http_response.json()
            bot_answer: str = bot_answer_http_response_json["bot_response"]
        except requests.exceptions.JSONDecodeError:
            bot_answer = str(bot_answer_http_response.text)
        print(f"The bot answered '{bot_answer}'.")

        # Wenn ein Prompt den Sicherheitscheck nicht bestanden hat, hat die JSON-Antwort
        # das Feld "security", sonst nicht
        prompt_safety_checks_passed:bool = "security" not in bot_answer_http_response_json

        # Formatiere die Bot-Antwort und aktualisiere den State
        bot_answer = bot_answer.replace("\n", "  \n")
        st.session_state.issue_description = bot_answer_http_response_json.get("issue_description", st.session_state.issue_description)
        st.session_state.additional_info = bot_answer_http_response_json.get("additional_info", st.session_state.additional_info)
        st.session_state.priority = bot_answer_http_response_json.get("priority", st.session_state.priority)


        bot_answer_history_entry_for_chat = {"role": "assistant", "content": bot_answer}
        st.session_state.messages.append(bot_answer_history_entry_for_chat)

        # Wenn ein Prompt den Sicherheitscheck nicht bestand, wird dieser nicht in den Bot-Kontext
        # geschrieben, damit der Nutzer noch die Chance hat, einen zulässigen Prompt zu schreiben
        if prompt_safety_checks_passed:
            st.session_state.chatbot_history.append(user_input_history_entry)
            bot_answer_history_entry_for_bot_history = {"role": "bot", "content": bot_answer}
            st.session_state.chatbot_history.append(bot_answer_history_entry_for_bot_history)

        st.write(bot_answer)

    # Hier wird das Chatfenster wieder entsperrt
    st.session_state.bot_thinking = False
    st.rerun()
