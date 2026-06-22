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

## 2. Architecture

```text
Frontend
    │
    │ POST /chat
    ▼
FastAPI
    │
    ▼
LangGraph
    │
    ├── Extract information
    ├── Ask for missing data
    ├── Search for solutions (RAG)
    └── Create ticket
    │
    ▼
Response to Frontend
```
If the chatbot cannot extract an issue, it attempts to ask the user to describe its issue again three times.  
After the third time, the chatbot ends the conversation referring to come back if there is a problem relevant for the ZIM.

If solutions are found, the frontend asks the user whether they solved the issue.

```text
Frontend
    │
    │ POST /solution-feedback
    ▼
Backend
    │
    ├── Helpful
    │      └── End conversation
    │
    └── Not helpful
           └── Create ticket in Zammad
```

# API Endpoints

## POST /chat

Main communication endpoint between frontend and backend.

Responsibilities:
- Receive user input
- Build the current chatbot state
- Execute the LangGraph workflow
- Return the updated state

#### Request

```json
{
  "user_message": "My VPN connection is not working.",
  "history": [
    {
      "role": "assistant",
      "content": "Hello! How can I help you?"
    },
    {
      "role": "user",
      "content": "My VPN connection is not working."
    }
  ],
  "user_email": "john.doe@example.com",
  "matrikelnummer": "12345678",
  "issue_description": "",
  "additional_info": [],
  "priority": 0
}
```

#### Response

```json
{
  "bot_response": "Can you tell me which operating system you are using?",
  "issue_description": "VPN connection does not work",
  "additional_info": [
    "VPN"
  ],
  "priority": 2,
  "solutions": [],
  "needs_additional_info": true,
  "is_complete": false
}
```

If the chatbot already knows a suitable solution, the response contains one or more solution objects instead of asking another question.

Example:

```json
{
  "bot_response": "Please try reconnecting to the university VPN using the AnyConnect client.",
  "issue_description": "VPN connection does not work",
  "additional_info": [
    "Windows 11"
  ],
  "priority": 2,
  "needs_additional_info": false,
  "is_complete": false,
  "solutions": [
    {
      "title": "VPN Troubleshooting",
      "content": "Restart the VPN client and reconnect."
    }
  ]
}
```


## POST /solution-feedback

Called after the user indicates whether the proposed solution solved the problem.

#### Request

```json
{
  "user_message": "",
  "history": [],
  "user_email": "john.doe@example.com",
  "matrikelnummer": "12345678",
  "issue_description": "VPN connection does not work",
  "additional_info": [
    "Windows 11"
  ],
  "priority": 2,
  "helpful": false,
  "solutions": [
    {
      "title": "VPN Troubleshooting",
      "content": "Restart the VPN client and reconnect."
    }
  ],
  "message": "Please try reconnecting to the university VPN using the AnyConnect client."
}
```

#### Response

If the solution was helpful, the backend returns a confirmation message.

```json
{
  "bot_response": "I'm glad the solution helped. Have a nice day!"
}
```

Otherwise, the backend creates a support ticket in Zammad and returns a confirmation.

```json
{
  "bot_response": "Your support ticket has been created successfully. Our support team will contact you soon."
}
```

---

# RAG System

Before creating a ticket, the chatbot searches the knowledge base for relevant information.

The retrieval component searches:
- FAQ entries
- Similar support tickets

The LLM summarizes the retrieved content into a concise response.

---

# Ticket Prioritization

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

---

# Zammad Integration

Communication with Zammad is implemented in `zammad_endpoints.py`.

Each ticket contains:
- Title
- Email
- Student ID
- Issue description
- Priority
- Additional information

---

# Prompt Security

The project contains optional security checks against:
- Prompt injection
- Illegal content
- Off-topic requests

These checks are implemented in `prompt_security_result.py` and can be enabled if required.

## Security Checks

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

## Current Limitations

The prompt injection detector (`deepset/deberta-v3-base-injection`) occasionally produces false positives for legitimate ZIM support requests.

To mitigate this issue, additional rule-based validation is currently used.

The legality check also contains a temporary keyword-based workaround for ZIM-related requests because the zero-shot classifier may incorrectly classify legitimate support tickets as harmful or unrelated.

These workarounds should be replaced by a more robust classifier-based solution in future iterations.

---

# Technologies

- Python
- FastAPI
- LangGraph
- LangChain
- Ollama
- OpenAI-compatible SAIA API
- Pydantic
- Zammad API

---

# Summary

The backend workflow consists of four main steps:

1. Extract information from the conversation.
2. Request missing information.
3. Search for suitable solutions using RAG.
4. Create a support ticket in Zammad if no solution resolves the issue.

The separation into **State**, **Nodes**, and **Graph** keeps the workflow modular, maintainable, and easy to extend.