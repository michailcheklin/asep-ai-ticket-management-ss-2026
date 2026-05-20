# Chatbot Backend

DThis is the backend code for the chatbot, based on LangGraph and FastAPI.

## 1. Prerequisites

* **Ollama** must be installed on your system and running in the background.
* Download the required language model once via your terminal:
  ```bash
  ollama pull llama3.2
  
## 2. Installation
* Install all required Python dependencies using the following command:
  ```bash
  pip install -r requirements.txt
  
## 3. Starting the Local Server
* Start the local FastAPI server via your terminal:
  ```bash 
  uvicorn api:app --reload
* The server is now accessible at http://127.0.0.1:8000
* The Server can be stopped via:
  ``` 
  Strg + C/Control + C

## 4. API Interface
* Post /chat
* This endpoint processes the user's input and communicates with the AI model
### Expected Request
```json
{
  "user_message": "Meine Nachricht an den Bot",
  "history": [],
  "customer_name": "",
  "matrikelnummer": "",
  "issue_description": ""
}
```

### Response from the Server
```json
{
  "bot_response": "Antwort der KI auf die Nachricht",
  "customer_name": "abc",
  "matrikelnummer": "123",
  "issue_description": "WLAN funktioniert nicht",
  "is_complete": false
}
```
* The Fields **customer_name**, **matrikelnummer** and **issue_description** will be populated if this information was present in a message from the user

### Example of a Request with Populated History
```json
{
  "user_message": "Mein Name ist Peter und meine Matrikelnummer lautet 1234567.",
  "history": [
    {
      "role": "user",
      "content": "Hallo, mein WLAN funktioniert seit heute Morgen nicht mehr."
    },
    {
      "role": "bot",
      "content": "Das tut mir leid. Um ein Ticket zu erstellen, benötige ich noch deinen Namen und deine Matrikelnummer."
    }
  ],
  "customer_name": "",
  "matrikelnummer": "",
  "issue_description": "WLAN funktioniert nicht"
}
```
* Requests must always include the existing history with role and content for the bot to function correctly