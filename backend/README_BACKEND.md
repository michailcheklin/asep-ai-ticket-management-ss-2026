# Chatbot Backend

This is the backend code for the chatbot, based on LangGraph and FastAPI. The code has been modularised and split into logical packages; see the repository layout below for details and links to package-level READMEs.

## 1. Installation & Setup
* The chatbot relies on Zammad and the included Ollama container running within Docker. Start the required containers from the `zammad` folder:

```bash
cd ../zammad
docker compose -f docker-compose.yml -f scenarios/add-ollama.yml up -d
cd ../
```

Then build and start the ai-ticket-management stack:

```bash
docker compose up -d --build
```

Notes:
- The backend expects the Zammad instance and the LLM runtime (Ollama or compatible SAIA API) to be reachable from the container network.
- Environment variables and other runtime configuration are documented in the top-level `README.md` and `example.env`.

## 2. Architecture

High-level flow:

```text
Frontend
    │
    │ POST /chat
    ▼
FastAPI (api)
    │
    ▼
LangGraph (graph)
    │
    ├── Extract information
    ├── Ask for missing data
    ├── Classify ticket type (ITSM)
    ├── Search for solutions (RAG, rag)
    └── Create ticket (services)
    │
    ▼
Response to Frontend
```

If the chatbot cannot extract an issue it asks the user to clarify up to three times and then ends the conversation politely.

If solutions are found by the RAG pipeline the frontend will offer them to the user and ask for feedback. Feedback is handled via `POST /solution-feedback` (see API section).

## Repository layout

The backend is organised into the following folders (each folder contains its own README with more details):

- `api/` - FastAPI endpoints and request/response shaping. See `api/README.md`.
- `graph/` - LangGraph workflow, nodes and state orchestration. See `graph/README.md`.
- `graph/models/` - Pydantic models used by the graph and nodes. See `graph/models/README.md`.
- `llm/` - LLM wrappers, prompt templates and helpers. See `llm/README.md`.
- `services/` - Integrations (Zammad, ticket creation, helpers). See `services/README.md`.

## API Endpoints

See `api/README.md` for full endpoint descriptions and example requests/responses. The two main endpoints are:

- `POST /chat` – primary conversation endpoint. Receives the user message and conversation state, executes the LangGraph workflow and returns an updated state and any suggested solutions.
- `POST /solution-feedback` – called when the user indicates whether a suggested solution solved the problem. Creates/updates tickets in Zammad depending on the feedback.

### Example (short)

Request to `/chat`:

```json
{
  "user_message": "My VPN connection is not working.",
  "history": [],
  "user_email": "john.doe@example.com"
}
```

Response (when additional info is needed):

```json
{
  "bot_response": "Can you tell me which operating system you are using?",
  "needs_additional_info": true
}
```

If a solution is found, the response includes a `solutions` array with short entries:

```json
{
  "bot_response": "Please try reconnecting to the university VPN using the AnyConnect client.",
  "solutions": [ { "title": "VPN Troubleshooting", "content": "Restart the VPN client and reconnect." } ],
  "needs_additional_info": false
}
```

## RAG System

Before creating a ticket the chatbot searches the knowledge base (FAQ entries and similar past tickets) and uses it as context to summarise relevant results. The RAG components are located under `rag/` and the embedded vector stores are in `rag/faq_db` and `rag/ticket_db`.

---

## Ticket Prioritization

Tickets are automatically classified into two priority levels:

| Priority | Meaning                   |
| -------- | ------------------------- |
| 0        | Normal / non-urgent issue |
| 1        | Urgent / important issue  |

Urgent examples: unable to log in, exam/deadline affected, complete service outage, critical account access issues.

---

---

## Ticket Type Classification (ITSM)

The chatbot classifies each support request into exactly one ITSM ticket type using an LLM-based classifier implemented in `graph/nodes.py`.

### Supported Ticket Types

| Ticket type | Typical use case |
| ----------- | ---------------- |
| Incident | Current service outage or malfunction (login, WLAN, printer, app crash) |
| Service Request | Information, access request, payment status, software request |
| Change | Requested change to system, role, group, or configuration |
| Problem | Recurring or root cause behind multiple incidents |
| Complaint | Complaint about support, waiting time, or communication |

### How It Works

The main function is `classify_ticket_category()` in `graph/nodes.py`. It uses a structured LLM output (`TicketCategoryDecision`) and prompt rules (`_CATEGORY_RULES`) to choose one ITSM ticket type based on the user's main intent.

Classification uses the full conversation context, not only the latest message:

* user messages from the chat history
* extracted issue description
* extracted additional information

The workflow node `classify_ticket_node` (defined in `classify_ticket()`) runs after additional information has been collected and before solution retrieval (`give_solutions_node`).

When a ticket is created, `_resolve_ticket_category()` reuses an already stored category from the chatbot state. If no valid category exists yet, classification is performed once at ticket creation.

The determined ticket type is:

* stored in the chatbot state (`category` field in `graph/state.py`)
* returned in the `/chat` API response
* included in the Zammad ticket body as `Kategorie: ...`

If the LLM returns an unknown type, the fallback is `Service Request`.

Ticket type classification is separate from information extraction. The extractor node only collects ticket data; type assignment is handled by the dedicated classification node.

### Tests

Category classification tests live in three files:

| File | Purpose |
| ---- | ------- |
| `test_ticket_category.py` | Unit tests with mocked LLM (no Ollama/SAIA required) |
| `test_ticket_category_live.py` | Live LLM integration, regression, and holdout suites |
| `category_test_support.py` | Shared fixtures and live-suite runner helpers |

Run from `backend/`:

```bash
python test_ticket_category.py
```

This discovers and runs both unit and live test modules.

#### Live LLM tests

Enable with:

```bash
RUN_LLM_CATEGORY_TESTS=1 python test_ticket_category.py
```

PowerShell:

```powershell
$env:RUN_LLM_CATEGORY_TESTS="1"; python test_ticket_category.py
```

#### Regression vs. holdout

| Suite | Fixture file | Purpose |
| ----- | ------------ | ------- |
| **REGRESSION** | `rag/old_tickets.json` | Prompt tuning on known template tickets (56 cases) |
| **HOLDOUT** | `rag/category_holdout_tests.json` | Generalization on unseen tickets — do **not** use for prompt tuning |

Optional environment variables:

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `CATEGORY_REGRESSION_MIN_ACCURACY` | `0.90` | Minimum pass rate for regression suite |
| `CATEGORY_HOLDOUT_MIN_ACCURACY` | `0.80` | Minimum pass rate for holdout suite |
| `CATEGORY_REGRESSION_LIMIT` | (none) | Cap regression cases, e.g. `10` for a quick run |

Add new real-world edge cases to `category_holdout_tests.json`, not to `old_tickets.json`.

---

## Zammad Integration

Ticket creation and updates are implemented in `services/TicketService.py` and the lower-level Zammad helpers live in `api/Zammad.py`. Tickets created after an AI-resolve contain:

- Title, Email, Student ID (Matrikelnummer)
- Issue description, Priority, Category, Additional information
- Chat history and offered solutions (for AISolved tickets)
- Tags and status (e.g. `AISolved`, closed)

---

## Prompt Security

Optional security checks are available to detect prompt injection, illegal content or off-topic requests. The detection logic is implemented in `tests/prompt_security_result.py` and related helpers. Blocked requests are logged to `blocked_prompts.log` with timestamp, category, model classification and risk score.

## Current Limitations

- The prompt-injection model (`deepset/deberta-v3-base-injection`) sometimes yields false positives; additional rule-based checks are used as a fallback.
- Some temporary keyword-based workarounds exist in the legality checks and should be replaced by more robust classifiers in the future.

---

## Technologies

- Python
- FastAPI
- LangGraph
- LangChain
- Ollama / SAIA-compatible API
- Pydantic
- Zammad API

---

## Summary

The backend workflow consists of five main steps:

1. Extract information from the conversation.
2. Request missing information.
3. Classify the ITSM ticket type.
4. Search for suitable solutions using RAG.
5. Create a support ticket in Zammad if no solution resolves the issue.

The separation into `api`, `graph`, `llm` and `services` keeps the workflow modular, maintainable and easy to extend. Each package contains a README with more implementation details.
