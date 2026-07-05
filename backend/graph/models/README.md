# Graph Models

This folder contains typed Pydantic models used across the graph and nodes.
Keeping models separate makes nodes and the API layer more predictable and easier to test.
Two kinds of models live here: transport models for the API boundary (`ChatRequest`)
and structured-output schemas that force the LLM to answer in a fixed shape
(`ExtractedTicketData`, `AdditionalInfoDecision`, `TicketCategoryDecision`, `IntentDecision`).

## Models

- `ChatRequest.py` — shape of an incoming chat request from the frontend. The API layer
  builds the initial `State` from it, and it carries the full conversation state on every
  request (the server itself is stateless). Key fields:
  - `user_message`, `history`
  - `user_email`, `matrikelnummer`, `issue_description`, `additional_info`
  - `priority`, `category`, `solutions`, `ticket_id`
  - `additional_info_attempts`, `ask_issue_attempts`
  - `intent`, `tutorial_attempts` — added for the two-path workflow 

- `ExtractedTicketData.py` — structured data extracted from the user's message by the
  extraction node. Fields:
  - `email`, `matrikelnummer`, `problem`
  - `additional_info` (list)
  - `priority` (int)
  - `full_conversation` (running summary of the conversation)

- `AdditionalInfoDecision.py` — decides whether more information is needed before a ticket
  can be completed. Fields:
  - `needs_additional_info` (bool)
  - `follow_up_question` (optional follow-up question(s) for the user)

- `TicketCategoryDecision.py` — ITSM ticket category assigned to a ticket. Field:
  - `category` — exactly one of: Incident, Service Request, Change, Complaint, Problem

- `IntentDecision.py` — classifies the user's intent to route the conversation
  (two-path workflow). Fields:
  - `intent` — exactly one of: `tutorial`, `problem`, `unclear`, `solved`
  - `reason` — short justification, used only for debugging / tracing

## Guidelines

- Keep models small and domain-focused.
- Use Pydantic field descriptions and validation for clarity and early error detection.
  Field descriptions on structured-output schemas are sent to the LLM and act as
  instructions, so keep them precise.
- When adding fields, update every station of the round-trip: `state.py`, `ChatRequest.py`,
  the mapping in `api/ZIM.py`, and the response dict in `orchestrator.py` — otherwise the
  field is silently lost between requests.

See `../README_BACKEND.md` and `../graph/README.md` for how these models are used in the workflow.