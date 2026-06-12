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


### Security Checks

Before a user message is processed by the chatbot workflow, multiple security checks are performed.

The backend currently validates:

* Prompt Injection attempts
* Illegal or harmful topics
* Off-topic requests unrelated to ZIM support

If a request violates one of these security checks, it is blocked and not forwarded to the chatbot workflow.

Blocked requests are logged together with:

* timestamp
* detected category
* model classification
* risk score

The security layer is executed before any chatbot processing or future RAG-based retrieval takes place.

#### Current Limitations

The prompt injection detector (`deepset/deberta-v3-base-injection`) occasionally produces false positives for legitimate ZIM support requests.

To mitigate this issue, additional rule-based validation is currently used.

The legality check also contains a temporary keyword-based workaround for ZIM-related requests because the zero-shot classifier may incorrectly classify legitimate support tickets as harmful or unrelated.

These workarounds should be replaced by a more robust classifier-based solution in future iterations.



### Expected Request
```json
{
  "user_message": "Meine Nachricht an den Bot",
  "history": [],
  "user_email": "",
  "matrikelnummer": "",
  "issue_description": "",
  "priority": 0
}
```

### Response from the Server
```json
{
  "bot_response": "Antwort der KI auf die Nachricht",
  "user_email": "abc",
  "matrikelnummer": "123",
  "issue_description": "WLAN funktioniert nicht",
  "priority": 1,
  "is_complete": false
}
```
* The Fields **user_email**, **matrikelnummer** and **issue_description** will be populated if this information was present in a message from the user


### Ticket Prioritization

The chatbot automatically classifies tickets into two priority levels:

| Priority | Meaning                   |
| -------- | ------------------------- |
| 0        | Normal / non-urgent issue |
| 1        | Urgent / important issue  |

Examples for urgent tickets include:

* User cannot log in
* Exam or deadline is affected
* Complete service outage
* Critical account access problems

The priority is extracted together with the ticket information and is included in the chatbot state and API response. The value can later be used when creating tickets in Zammad to assign a higher ticket priority.


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