import asyncio

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

testcases = [ChatRequest(**testcase) for testcase in testcases]

def test_chat_endpoint():
    for testcase in testcases:
        print("-"*50)
        response = asyncio.run(chat_endpoint(testcase))
        print(str(response))




if __name__ == '__main__':
    test_chat_endpoint()