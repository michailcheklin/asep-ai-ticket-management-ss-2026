# Chatbot Backend

This is the backend code for the chatbot, based on LangGraph and FastAPI.
  
## 1. Installation & Setup
* The chatbot relies on Zammad and the included Ollama container running within a Docker. 
Therefore, these containers need to by started by:

```bash
$ cd ../zammad
```
and then:
```bash
docker compose -f docker-compose.yml -f scenarios/add-ollama.yml up -d
```
after that switch to base directory
  ```bash
  cd ../
  ```
then start the ai-ticket-management container
```bash
docker compose up -d --build
```

## 2. API Interface
* POST /chat
* This endpoint processes the user's input and communicates with the AI model
### Expected Request
```json
{
  "user_message": "Meine Nachricht an den Bot",
  "history": [],
  "user_email": "",
  "matrikelnummer": "",
  "additional_info": [],
  "issue_description": ""
}
```

### Response from the Server
```json
{
  "bot_response": "Dein Ticket ist fertiggestellt...", 
  "user_email": "peter@uni.de",
  "matrikelnummer": "1234567",
  "issue_description": "WLAN Problem",
  "additional_info": [
    "Essen",
    "Gebäude R14"
  ],
  "is_complete": true
}
```
* The Fields **user_email**, **matrikelnummer** and **issue_description** will be populated if this information was present in a message from the user

### Example of a Request with Populated History
```json
{
  "user_message": "es handelt sich um ein wlan problem, ich bin in essen im gebäude R14 und ich habe noch keine schritte unternommen",
  "history": [
    {
      "role": "user",
      "content": "Hallo, meine email ist peter@uni.de, meine matrikelnummer ist 1234567 und ich habe internet probleme"
    },
    {
      "role": "bot",
      "content": "Könnten Sie uns bitte mehr Details zu Ihrem Internetproblem geben? Zum Beispiel, ob es sich um ein WLAN- oder ein kabelgebundenes Problem handelt, welcher Ort oder welches Gebäude betroffen ist..."
    }
  ],
  "user_email": "peter@uni.de",
  "matrikelnummer": "1234567",
  "issue_description": "internet probleme",
  "additional_info": []
}
```
* Requests must always include the existing history with role and content for the bot to function correctly

> **Note for Dockerization:** When creating the `docker-compose.yml` for this backend, ensure `OLLAMA_BASE_URL` is set to point to the internal Docker network name of the Ollama container (e.g., `http://ollama:11434`).