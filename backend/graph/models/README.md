# Graph Models

This folder contains typed Pydantic models used across the graph and nodes. Keeping models separate makes nodes and the API layer more predictable and easier to test.

Included models (examples)
- `ExtractedTicketData.py` — representation of the extracted issue data. Typical fields:
  - `title` / `summary`
  - `description`
  - `priority`
  - `additional_info` (list)
- `ChatRequest.py` — the shape of an incoming chat request (used by the API to build the initial `State`). Typical fields:
  - `user_message`
  - `history`
  - `user_email`
  - `matrikelnummer`
- `AdditionalInfoDecision.py` — model describing which additional info is required and the follow-up question(s).

Guidelines
- Keep models small and domain-focused.
- Use Pydantic field descriptions and validation for clarity and early error detection.
- When adding fields, update serialization in the API and any node that consumes the model.

See `../README_BACKEND.md` and `../graph/README.md` for how these models are used in the workflow.

