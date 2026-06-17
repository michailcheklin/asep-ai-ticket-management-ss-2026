import json
import pytest

from backend.main import chat_endpoint, ChatRequest

# Nur 3 Tests, um die Prompts beim Key zu sparen
testcases = [
    # Beginn einer Konversation
    {
        "user_message": "Mein WLAN geht nicht",
        "history": [

        ],  # Format: [{"role": "user", "content": "Hallo"}, {"role": "bot", "content": "Hi"}]
        "user_email":"a@example.com",
        "matrikelnummer": "123456789",
        "issue_description": "",
        "additional_info": [],
        "priority": 0
    },

    # Konversation mit einem Prompt
    {
        "user_message": "Ich probiere, meine E-Mails über den Webmailer mit Firefox 151.0.4 aufzurufen.",
        "history": [
            {"role":"user", "content":"Ich komme nicht mehr an meine E-Mails."},
            {"role":"bot", "content":"Um Ihre Anfrage genauer beantworten zu können"
                                      "benötige ich noch Informationen darüber, über welche"
                                      "Methode (Browser/Mail-App) und mit welchem Gerät Sie"
                                      "versuchten, Ihre E-Mails abzurufen."}
        ],
        "user_email": "a@example.com",
        "matrikelnummer": "123456789",
        "issue_description": "E-Mails nicht verfügbar",
        "additional_info": [],
        "priority": 0
    },

    # Konversation mit 2 Prompts
    {
        "user_message": "Ich habe alles genannte probiert, aber das Problem besteht immer noch",
        "history": [
            {"role": "user", "content": "Mein Drucker geht nicht."},
            {"role": "bot", "content": "Um Ihre Anfrage genauer beantworten zu können"
                                       "bräuchte ich die Information, um welches Modell"
                                       "es sich beim betroffenen Drucker handelt. Können Sie"
                                       "das Problem genauer beschreiben?"},
            {"role": "user", "content": "Das ist ein HP OfficeJet 3830. Der Drucker druckt nur schwarzweiß, "
                                        "obwohl ich Farbdruck eingestellt habe."},
            {"role": "bot", "content": "Haben Sie probiert, 1. den Drucker neuzustarten, "
                                       "2. Prüfen, ob die Farbpatronen nicht leer sind,"
                                       "3. Prüfen, ob der Farbdruck in den Einstellungen ausgewählt wurde."},
        ],
        "user_email": "a@example.com",
        "matrikelnummer": "123456789",
        "issue_description": "Drucker funktioniert nicht",
        "additional_info": ["HP OfficeJet 3830", "Drucker", "Farbe drucken Problem"],
        "priority": 0
    },

]


@pytest.mark.asyncio
@pytest.mark.parametrize("testcase", testcases)
async def test_chat_endpoint_returning_bot_response(testcase):
    """
    Dieser Test testet, ob das LLM überhaupt eine wohlgeformte Antwort generieren kann,
    d. h. eine gültige JSON. Dies ist Platzhalter, bis ein besseres Verständnis über DeepEval
    für die echte LLM-Analyse gewonnen werden konnte
    :param testcase: Der zu testende Prompt mit dem Kontext als JSON
    """
    test_request_as_chat_request = ChatRequest(**testcase)
    print(f"Sending following request to the chatbot: \n{json.dumps(testcase)}")
    response = await chat_endpoint(test_request_as_chat_request)
    print(f"The chatbot responded with the following response: \n{json.dumps(response)}")
    assert isinstance(response, dict), "Response should be a dictionary"
    assert "bot_response" in response, "Response should contain a 'bot_response' key"
