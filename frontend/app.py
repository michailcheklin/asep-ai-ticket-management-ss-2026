"""Streamlit-Frontend; BACKEND_URL http://backend_app:8000 in Docker."""
import os
import streamlit as st
import re
import requests
from requests import Response


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


def are_form_fields_valid() -> bool:
    """
    Prüfung, ob eine gültige E-Mail-Adresse und eine
    gültige Matrikelnummer (Nur Zahlen) eingegeben wurde
    """
    is_email_valid = bool(re.fullmatch(pattern=r"[a-zA-Z0-9\._-]+@[a-zA-Z0-9\._-]+\.[a-zA-Z0-9\._-]+", string=st.session_state["email_input"]))
    is_matrikelnummer_valid = bool(re.fullmatch(pattern=r"[0-9]+", string=st.session_state["matrikelnummer_input"]))

    return is_email_valid and is_matrikelnummer_valid


def process_user_message(user_input: str) -> None:
    """
    Method that processes the user message. Based on the user's input, it sends a request to the backend and updates the chat history with the bot's response.
    :param user_input:
    :return: void
    """

    #
    with st.chat_message("user"):
        st.write(user_input)

    with st.chat_message("assistant"):

        placeholder = st.empty()
        placeholder.write('*:color[Bitte warten. Antwort wird generiert...]{foreground="#888888"}*')

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
        # Response vom Backend als JSON
        res = requests.post(
            url=f"{BACKEND_URL}/chat",
            json=req,
            timeout=AI_COMMUNICATION_TIMEOUT_IN_SECONDS,
        ).json()

        if "security" not in res:
            print("Prompt Safety Check passed!")

            answer = res["bot_response"]
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
                "solutions": res.get("solutions")
            })

            st.session_state.chatbot_history.append({
                "role": "assistant",
                "content": answer
            })

            # 🔥 WICHTIG: Backend-State synchronisieren
            st.session_state.issue_description = res.get("issue_description", "")
            st.session_state.additional_info = res.get("additional_info", [])
            st.session_state.priority = res.get("priority", 0)

        else:
            print("Prompt Safety Check failed!")


def process_solution_feedback(message_index: int, helpful: bool):
    """
    Generiert ein Ticket abhängig vom Feedback des Nutzers.
    Wenn helpful, dann kein Ticket und nette Abschiedsnachricht, sonst Ticketerstellung inkl. Bestätiungsnachricht + Übersicht
    :param message_index: letzte message des bots (hier: die solution)
    :param helpful: ob diese message hilfreich war oder nicht
    :return:
    """
    message = st.session_state.messages[message_index]

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

    res = requests.post(
        f"{BACKEND_URL}/solution-feedback",
        json=payload,
        timeout=AI_COMMUNICATION_TIMEOUT_IN_SECONDS
    ).json()

    # UI State updaten
    message["solutions"] = []

    return res.get("bot_response")

# Bilde die Darstellung des Chatfensters
for i, message in enumerate(st.session_state.messages):
    with st.chat_message(message["role"]):
        st.write(message["content"])

        # Wenn es Lösungen gibt, dann wird die displayed message[content] die in Text verpackte Lösung.
        # Hier if solutions, nicht if message, weil wir die message nach Ja/Nein behalten wollen ABER solutions danach leeren
        # so wird beim rerun() gewährleistet, dass die Buttons nicht wieder gerendert werden aber die message weiterhin im Chatverlauf sichtbar bleibt
        if message.get("solutions"):
            col1, col2 = st.columns(2)

            with col1:
                if st.button("Ja"): # hat gefolfen
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": process_solution_feedback(i, True)
                    })
                    st.session_state.bot_thinking = True # Chat ist Ende, User darf so nicht mehr schreiben
                    st.rerun()
                    # API Endpoint rufen für bot-tag-complete
            with col2:
                if st.button("Nein"): # hat nicht geholfen
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": process_solution_feedback(i, False)
                    })
                    st.session_state.bot_thinking = True # s.o.
                    st.rerun()








# Ist die Matrikelnummer oder die E-Mail-Adresse
# ungültig, kann der Benutzer keine Nachrichten an den Chatbot schreiben
# denn sonst kann ein mögliches Ticket keiner Person zugeordnet werden
# und das ZIM-Team kann keine Nachfragen per E-Mail stellen
# Wenn Nutzer nach Eingabe der E-Mail-Adresse und der Matrikelnummer
# etwas in den Chat eintippt, beginnt die Generierung der Antwort auf die Eingabe des Nutzers.
# Direkt nach der Eingabe wird das Chatfenster gesperrt, bis der Bot geantwortet hat (s. Methode bot_starting_thinking()).
if user_input:= st.chat_input(
    placeholder = "Bitte E-Mail-Adresse und Matrikelnummer eingeben" if not are_form_fields_valid()
    else "Beschreibe dein Anliegen...",
    disabled=st.session_state.bot_thinking or not are_form_fields_valid(),
    on_submit=bot_starting_thinking
):
    process_user_message(user_input)

    # Hier wird das Chatfenster wieder entsperrt
    st.session_state.bot_thinking = False
    st.rerun()
