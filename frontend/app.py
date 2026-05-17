import streamlit as st


# SPÄTERE BACKEND-/ZAMMAD-ANBINDUNG
# Aktuell auskommentiert, da zunächst nur die Chatbot-
# Oberfläche entwickelt wird. Man könnte es aber später nutzen, 
# um automatisch Tickets in Zammad anzulegen.
# Die KI Anbindungen kommt dann natürlich auch noch später. 
# from zammad_endpoints import create_ticket_by_user_email

st.set_page_config(page_title="Support-Annahme über ZIM Helper", layout="centered")

st.title("Support-Annahme über ZIM Helper")
st.caption("Dein digitaler Assistent für Support-Anfragen")

st.subheader("Deine Kontaktdaten")
# TODO: Pflichtfelder noch prüfen bzw Validierung einbauen. 
email = st.text_input("E-Mail-Adresse *")
matrikelnummer = st.text_input("Matrikelnummer *")

st.divider()

st.header("ZIM Helper")

if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": "Hallo! Ich bin ZIM Helper. Erzähl mir bitte von deinem Anliegen."
        }
    ]

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.write(message["content"])

user_input = st.chat_input("Beschreibe dein Anliegen...")

if user_input:
    st.session_state.messages.append(
        {"role": "user", "content": user_input}
    )

    with st.chat_message("user"):
        st.write(user_input)

    bot_answer = (
        "Danke für deine Nachricht. "
        "Ich nehme dein Anliegen auf."
    )

    st.session_state.messages.append(
        {"role": "assistant", "content": bot_answer}
    )

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
#     f"""
#     E-Mail: {email}
#
#     Matrikelnummer: {matrikelnummer}
#
#     Anliegen:
#     {anliegen if anliegen else "Hier würde das Ergebnis der KI präsentiert werden."}
#     """
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


# Ticket manuell erstellen
# (2. Idee wäre eher ein Schritt zurück.
# Daher vielleicht doch eher die 1. Idee,
# die eine manuelle Eingabe integriert.)
# st.divider()
# st.subheader("Kommst du mit dem Chatbot nicht weiter?")
# st.write("Dann kannst du hier alternativ direkt ein Ticket erstellen.")
#
# if st.button("Ticket manuell erstellen"):
#
#     if not email or not matrikelnummer:
#         st.error("Bitte E-Mail-Adresse und Matrikelnummer ausfüllen.")
#
#     else:
#         body = "\n\n".join(
#             [
#                 f"{message['role']}: {message['content']}"
#                 for message in st.session_state.messages
#             ]
#         )
#
#         create_ticket_by_user_email(
#             email=email,
#             title=f"Support-Anfrage von {matrikelnummer}",
#             body=body
#         )
#
#         st.success("Ticket wurde erfolgreich erstellt.")