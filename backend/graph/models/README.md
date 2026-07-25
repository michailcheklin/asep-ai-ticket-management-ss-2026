# Graph Models

This folder contains typed Pydantic models used across the graph and nodes.
Keeping models separate makes nodes and the API layer more predictable and easier to test.
Two kinds of models live here: transport models for the API boundary (`ChatRequest`,
`FaqSubmission`) and structured-output schemas that force the LLM to answer in a fixed shape
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
  - `language` — detected response/UI language (`"de"`/`"en"`), threaded through the state so
    the LLM answers in that language (see Internationalization in the root `CLAUDE.md`)

- `FaqSubmission.py` — transport model for `POST /faq` (FAQ knowledge submission). Fields:
  `id` (title, optional — auto-generated if empty), `context` (category, required),
  `problem`, `solution` (list of `{faq_content, extracted_urls}`), and the control flags
  `force` (skip redundancy check) and `confirmed` (store the previewed entry as-is). Handled by
  `rag/faq_submission.py`.

- `ExtractedTicketData.py` — structured data extracted from the user's message by the
  extraction node. Fields:
  - `email`, `matrikelnummer`, `problem`
  - `additional_info` (list)
  - `priority` (int)
  - `summary` (running summary of the conversation)

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

- `TranscribeRequest.py` — request body for `POST /transcribe` (speech-to-text, not part
  of the graph state). Fields:
  - `audio_base64` — base64-encoded audio recorded via the frontend's `st.audio_input`
  - `language` — optional ISO language hint (`"de"`/`"en"`) passed to faster-whisper

## Guidelines

- Keep models small and domain-focused.
- Use Pydantic field descriptions and validation for clarity and early error detection.
  Field descriptions on structured-output schemas are sent to the LLM and act as
  instructions, so keep them precise.
- When adding fields, update every station of the round-trip: `state.py`, `ChatRequest.py`,
  the mapping in `api/ZIM.py`, and the response dict in `orchestrator.py` — otherwise the
  field is silently lost between requests.

See `../README_BACKEND.md` and `../graph/README.md` for how these models are used in the workflow.