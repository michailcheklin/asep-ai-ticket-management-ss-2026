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

# Mithilfe dieses State-Keys wird die Sperrung des Chatfensters gesteuert.
if "bot_thinking" not in st.session_state:
    st.session_state.bot_thinking: bool = False

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

# Interne History für Ollama, damit der Kontext
# für zukünftige Chatnachrichten verwendet werden kann
if "chatbot_history" not in st.session_state:
    st.session_state.chatbot_history: list[dict[str, str]] = []

# Hier wird die Information, die der Bot aus der Benutzernachricht extrahieren konnte
# als Text gespeichert
if "issue_description" not in st.session_state:
    st.session_state.issue_description: str = ""

# Hier werden die zusätzlichen Infos, die das LLM extrahieren konnte,
# gespeichert, damit diese bei nachfolgenden Anfragen verwendet werden können
if "additional_info" not in st.session_state:
    st.session_state.additional_info: list[str] = []

# Hier wird die Priorität gespeichert, damit diese nicht
# über Nachrichten hinweg verloren geht
if "priority" not in st.session_state:
    st.session_state.priority: int = 0

# Prüfung, ob eine gültige E-Mail-Adresse und eine
# gültige Matrikelnummer (Nur Zahlen) eingegeben wurde
is_email_valid = bool(re.fullmatch(pattern=r"[a-zA-Z0-9\._-]+@[a-zA-Z0-9\._-]+\.[a-zA-Z0-9\._-]+", string=st.session_state["email_input"]))
is_matrikelnummer_valid = bool(re.fullmatch(pattern=r"[0-9]+", string=st.session_state["matrikelnummer_input"]))

# Ist die Matrikelnummer oder die E-Mail-Adresse
# ungültig, kann der Benutzer keine Nachrichten an den Chatbot schreiben
# denn sonst kann ein mögliches Ticket keiner Person zugeordnet werden
# und das ZIM-Team kann keine Nachfragen per E-Mail stellen
# Wenn Nutzer nach Eingabe der E-Mail-Adresse und der Matrikelnummer
# etwas in den Chat eintippt, beginnt die Generierung der Antwort auf die Eingabe des Nutzers.
# Direkt nach der Eingabe wird das Chatfenster gesperrt, bis der Bot geantwortet hat (s. Methode bot_starting_thinking()).
if user_input:= st.chat_input(
    placeholder = "Bitte E-Mail-Adresse und Matrikelnummer eingeben" if not (is_email_valid and is_matrikelnummer_valid)
    else "Beschreibe dein Anliegen...",
    disabled=st.session_state.bot_thinking or not (is_email_valid and is_matrikelnummer_valid),
    on_submit=bot_starting_thinking
):


    with st.chat_message("user"):
        st.write(user_input)
        user_input_history_entry = {"role": "user", "content": user_input}
        st.session_state.messages.append(user_input_history_entry)


    with st.chat_message("assistant"):
        # Hier wird die Bot-Antwort generiert. Während die Antwort generiert wird,
        # wird ein grauer Platzhaltertext bei der Bot-Antwort erscheinen, bis
        # der Bot geantwortet hat.
        #
        # Die Streamlit-Funktion st.write() schreibt ein Markdown-Objekt, wenn ein String übergeben wird
        # (s. https://docs.streamlit.io/develop/api-reference/write-magic/st.write)
        # Der Markdown-Standard erfordert folgende Sytnax für die Färbung von Text:
        # :color[Text]{foreground="<Farbcode in Hex>"}.
        # Ein Sternchen an beiden Seiten des Textes macht diesen kursiv.
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

        # Vor jeden Zeilenumbruch werden 2 Leerzeichen eingefügt, damit die
        # Bot-Antwort korrekt im Chatfenster dargestellt werden kann.
        # Die Streamlit-Funktion st.write() schreibt ein Markdown-Objekt, wenn ein String übergeben wird
        # (s. https://docs.streamlit.io/develop/api-reference/write-magic/st.write)
        # Der Markdown-Standard fordert, um einen Zeilenumbruch zu erzwingen, 2 Leerzeichen davor
        # (s. https://markdown-guide.readthedocs.io/en/latest/basics.html#line-return)
        bot_answer = bot_answer.replace("\n", "  \n")
        st.session_state.issue_description = bot_answer_http_response_json.get("issue_description", st.session_state.issue_description)
        st.session_state.additional_info = bot_answer_http_response_json.get("additional_info", st.session_state.additional_info)
        st.session_state.priority = bot_answer_http_response_json.get("priority", st.session_state.priority)


        bot_answer_history_entry_for_chat = {"role": "assistant", "content": bot_answer}
        st.session_state.messages.append(bot_answer_history_entry_for_chat)

        # Wenn ein Prompt den Sicherheitscheck nicht bestand, wird dieser nicht in den Bot-Kontext
        # geschrieben, damit der Nutzer noch die Chance hat, einen zulässigen Prompt zu schreiben
        # Erfüllt das Acceptance Criterion
        # "Prompts that trigger the detection do not get written into the chatbot history for the backend
        # to not pollute the context if a legit prompt is sent afterwards" aus Issue #111
        if prompt_safety_checks_passed:
            st.session_state.chatbot_history.append(user_input_history_entry)
            bot_answer_history_entry_for_bot_history = {"role": "bot", "content": bot_answer}
            st.session_state.chatbot_history.append(bot_answer_history_entry_for_bot_history)

        st.write(bot_answer)

    # Hier wird das Chatfenster wieder entsperrt
    st.session_state.bot_thinking = False
    st.rerun()

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
