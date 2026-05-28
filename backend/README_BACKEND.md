# Chatbot Backend

This is the backend code for the chatbot, based on LangGraph and FastAPI.
  
## 1. Installation & Setup
* The chatbot relies on Zammad and the included Ollama container running within a Docker. 
Therefore, these containers need to by started by:

```bash
$ cd zammad
```
and then:
```bash
docker compose -f docker-compose.yml -f scenarios/add-ollama.yml up -d
```
* after that switch to backend directory
  ```bash
  cd ../backend
  ```
* Make sure you are operating within a Python Virtual Environment 
(indicated by `(.venv)` at the beginning of your terminal prompt)
* Install all required Python dependencies using the following command:
  ```bash
  pip install -r requirements.txt
  ```
  
## 2. Starting the Local Server
* Start the local FastAPI server via your terminal:
  ```bash 
  uvicorn api:app --reload
* The server is now accessible at http://127.0.0.1:8000
* The Server can be stopped via:
  ``` 
  Strg + C/Control + C

## 3. API Interface
* POST /chat
* This endpoint processes the user's input and communicates with the AI model
### Expected Request
```json
{
  "user_message": "Meine Nachricht an den Bot",
  "history": [],
  "user_email": "",
  "matrikelnummer": "",
  "issue_description": ""
}
```

### Response from the Server
```json
{
  "bot_response": "Antwort der KI auf die Nachricht",
  "user_email": "abc",
  "matrikelnummer": "123",
  "issue_description": "WLAN funktioniert nicht",
  "is_complete": false
}
```
* The Fields **user_email**, **matrikelnummer** and **issue_description** will be populated if this information was present in a message from the user

### Example of a Request with Populated History
```json
{
  "user_message": "Meine email ist abc@stud.uni-due.de und meine Matrikelnummer lautet 1234567.",
  "history": [
    {
      "role": "user",
      "content": "Hallo, mein WLAN funktioniert seit heute Morgen nicht mehr."
    },
    {
      "role": "bot",
      "content": "Das tut mir leid. Um ein Ticket zu erstellen, benötige ich noch deine email und deine Matrikelnummer."
    }
  ],
  "customer_email": "",
  "matrikelnummer": "",
  "issue_description": "WLAN funktioniert nicht"
}
```
* Requests must always include the existing history with role and content for the bot to function correctly

> **Note for Dockerization:** When creating the `docker-compose.yml` for this backend, ensure `OLLAMA_BASE_URL` is set to point to the internal Docker network name of the Ollama container (e.g., `http://ollama:11434`).