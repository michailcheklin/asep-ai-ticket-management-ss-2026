# API (FastAPI) Documentation

This folder contains the FastAPI endpoints that receive frontend requests, validate/shape input, and forward actions to the graph and service layers.

Files
- `Zammad.py` — low-level Zammad helpers and wrappers used by service layer. Contains methods to call the Zammad REST API (create ticket, add tag, update status, etc.).
- `ZIM.py` — FastAPI endpoint definitions. Routes are responsible for building the request state, calling into the graph workflow, and returning the response to the frontend.
- `channel_email.py` — FastAPI router handling email webhook integrations. Responsible for receiving incoming emails, filtering out auto-replies, and forwarding the payload to the email-specific LangGraph workflow.

Main endpoints
- `POST /chat` — main conversation endpoint. Accepts a JSON payload with the user message, optional history and user metadata. Returns the updated chatbot state, any found solutions, and whether additional data is required.
- `POST /solution-feedback` — receives user feedback about a proposed solution. Depending on the feedback it may create or close a ticket in Zammad and return a confirmation message.
- `POST /api/webhook/email` — email webhook endpoint. Accepts parsed email payloads. Filters out system auto-replies (like `support@localhost`) to prevent infinite loops, extracts the email context, and triggers the graph workflow to automatically generate a fully categorized Zammad ticket.

Responsibilities of the API layer
- Validate incoming requests (Pydantic models)
- Build the state object passed to the LangGraph workflow
- Call `graph.orchestrator` or equivalent entry point
- Return standardized responses to the frontend and handle error cases

Examples

Request to `/chat`:

```json
{
  "user_message": "My VPN connection is not working.",
  "history": [],
  "user_email": "john.doe@example.com"
}
```

Typical internal flow for `/chat`:
1. API validates request and creates a State object
2. State is passed to the graph/orchestrator
3. Graph runs nodes: extraction, missing info, RAG retrieval
4. Result is returned to the API which forwards it to the client

See the package-level READMEs (`../graph/README.md`, `../services/README.md`) for more details on the workflow and integrations.
