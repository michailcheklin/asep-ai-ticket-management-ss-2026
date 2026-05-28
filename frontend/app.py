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

# Erste Nachricht
if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": "Hallo! Ich bin ZIM Helper. Erzähl mir bitte von deinem Anliegen."
        }
    ]

# Bilde die Darstellung des Chatfensters
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.write(message["content"])

# Interne History für Ollama, damit der Kontext
# für zukünftige Chatnachrichten verwendet werden kann
if "chatbot_history" not in st.session_state:
    st.session_state.chatbot_history: list[dict[str, str]] = []

# Hier wird die Information, die der Bot aus der Benutzernachricht extrahieren konnte
# als Text gespeichert
if "issue_description" not in st.session_state:
    st.session_state.issue_description: str = ""

# Prüfung, ob eine gültige E-Mail-Adresse und eine
# gültige Matrikelnummer (Nur Zahlen) eingegeben wurde
is_email_valid = bool(re.fullmatch(pattern=r"[a-zA-Z0-9\._-]+@[a-zA-Z0-9\._-]+\.[a-zA-Z0-9\._-]+", string=st.session_state["email_input"]))
is_matrikelnummer_valid = bool(re.fullmatch(pattern=r"[0-9]+", string=st.session_state["matrikelnummer_input"]))

# Ist die Matrikelnummer oder die E-Mail-Adresse
# ungültig, kann der Benutzer keine Nachrichten an den Chatbot schreiben
# denn sonst kann ein mögliches Ticket keiner Person zugeordnet werden
# und das ZIM-Team kann keine Nachfragen per E-Mail stellen
if not (is_email_valid and is_matrikelnummer_valid):
    user_input = st.chat_input(
        disabled=True,
        placeholder="Bitte E-Mail-Adresse und Matrikelnummer eingeben",
    )
else:
    user_input = st.chat_input(
        disabled=False,
        placeholder="Beschreibe dein Anliegen..."
    )


# Wenn Nutzer etwas in den Chat eintippt, wird dies ausgeführt
if user_input:
    user_input_history_entry = {"role": "user", "content": user_input}

    st.session_state.messages.append(
        user_input_history_entry
    )
    st.session_state.chatbot_history.append(user_input_history_entry)

    with st.chat_message("user"):
        st.write(user_input)

    # TODO: Solange der Bot die Nachricht generiert,
    #  das Chatfenster sperren und wenn der Bot fertig ist,
    #  dann wieder entsperren
    # Hier wird die Bot-Antwort generiert
    bot_answer_http_response:Response = requests.post(
        url=f"{BACKEND_URL}/chat",
        json={
            "user_message": user_input,
            "history": st.session_state.chatbot_history,
            "user_email": st.session_state["email_input"],
            "matrikelnummer": st.session_state["matrikelnummer_input"],
            "issue_description": st.session_state.issue_description,

        },
        timeout=AI_COMMUNICATION_TIMEOUT_IN_SECONDS,
    )

    # Hier werden die Informationen aus dem JSON-Objekt,
    # womit auf den POST-Request geantwortet wurde, extrahiert
    bot_answer_http_response_json:dict = bot_answer_http_response.json()
    bot_answer:str = bot_answer_http_response_json["bot_response"]
    # Vor jeden Zeilenumbruch werden 2 Leerzeichen eingefügt, damit die
    # Bot-Antwort korrekt im Chatfenster dargestellt werden kann.
    # Die Streamlit-Funktion st.write() schreibt ein Markdown-Objekt,
    # wenn ein String übergeben wird (s. https://docs.streamlit.io/develop/api-reference/write-magic/st.write)
    # Der Markdown-Standard fordert, um einen Zeilenumbruch zu erzwingen, 2 Leerzeichen davor
    # (s. https://markdown-guide.readthedocs.io/en/latest/basics.html#line-return)
    bot_answer = bot_answer.replace("\n", "  \n")
    st.session_state.issue_description = bot_answer_http_response_json["issue_description"]

    bot_answer_history_entry_for_chat = {"role": "assistant", "content": bot_answer}
    bot_answer_history_entry_for_bot_history = {"role": "bot", "content": bot_answer}
    st.session_state.messages.append(
        bot_answer_history_entry_for_chat
    )

    st.session_state.chatbot_history.append(bot_answer_history_entry_for_bot_history)

    with st.chat_message("assistant"):
        st.write(bot_answer)


# Geplante Logik für die spätere Ticket-Erstellung:

# 1.Idee:
# Zusammenfassung durch KI
# Dieser Bereich soll später erscheinen, nachdem die KI den Chat analysiert und eine Zusammenfassung erstellt hat.
# Nutzer können dann bestätigen oder korrigieren,
# ob ihr Anliegen richtig verstanden wurde.
# user_messages = [
#     message["content"]
#     for message in st.session_state.messages
#     if message["role"] == "user"
# ]
#
# anliegen = "\n".join(user_messages)
#
# st.divider()
# st.subheader("Ticket Erstellung")
#
# st.info(
#     f" <-- Here should be 3 consecutive double quotes, if the code is not commented out anymore.
#        This change was applied to address the Teamscale warning as described in
#        https://gitlab.git.nrw/ude-sse/asep-sose26/team1-zim/ai-ticket-management/-/merge_requests/7#note_598152
#     E-Mail: {email}
#
#     Matrikelnummer: {matrikelnummer}
#
#     Anliegen:
#     {anliegen if anliegen else "Hier würde das Ergebnis der KI präsentiert werden."}
#     " <-- Here should be 3 consecutive double quotes, if the code is not commented out anymore.
#          This change was applied to address the Teamscale warning as described in
#          https://gitlab.git.nrw/ude-sse/asep-sose26/team1-zim/ai-ticket-management/-/merge_requests/7#note_598152
# )
#
# feedback = st.radio(
#     "Habe ich dein Anliegen richtig verstanden?. Bitte auswählen.",
#     ["Ja", "Nein"]
# )
#
# if feedback == "Ja":
#     st.success(
#         "Super! Dein Anliegen kann nun an den Support weitergeleitet werden."
#     )
#
# elif feedback == "Nein":
#
#     correction = st.text_area(
#         "Bitte beschreibe, was ich falsch verstanden habe:"
#     )
#
#     if correction:
#         st.warning(
#             "Danke für die Korrektur. "
#             "Ich berücksichtige deine Ergänzung "
#             "und leite dein Anliegen weiter."
#         )
