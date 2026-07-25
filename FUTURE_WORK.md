# Future Work

This document lists open topics for whoever continues this project. It covers work that was planned but not implemented during this project phase, plus a few additional recommendations based on the current state of the codebase.

## 1. Knowledge base reporting / observability (Obsidian-style)

There is currently no dashboard or report showing *what* is in the RAG knowledge base, *how* it's being used, or where it's failing.

Useful signals to surface:
- Which FAQ/ticket entries in `backend/rag/faq_db` and `backend/rag/ticket_db` are retrieved most/least often, and with what similarity scores.
- Queries that came back with no match above threshold (`0.30` for FAQ, `0.50` for tickets, see `backend/rag/`) — these are the clearest signal of knowledge base gaps.
- How many tickets ingested via the `/zammad/ticket-closed` webhook actually get reused later vs. sit unused.
- A simple link-graph / backlink view (Obsidian-style) between FAQ entries, ingested tickets, and the queries they resolved, to spot duplicate or contradictory knowledge.

LangSmith tracing is already enabled and captures every RAG call — the fastest path here is building a report off existing LangSmith traces rather than instrumenting the RAG layer from scratch.

## 2. Local model → API fallback

Today the model backend is a static choice via `USE_SAIA_API` (`backend/llm/llm.py`) — either Ollama or SAIA, chosen once at startup, no runtime fallback.

Not implemented because during development there was no local compute capacity to run a local model at all, so development relied entirely on the SAIA API (GWDG). The models used there (e.g. Llama 3.x) were chosen specifically because they're also self-hostable via Ollama, keeping this fallback path realistic for later.

What's needed:
- Detect local model failure/unavailability (Ollama connection error, timeout, OOM) in `backend/llm/llm.py`.
- Fall back to SAIA API on failure, respecting the existing 3,000 req/month cap (would need a request counter/guard so a broken local model doesn't silently burn the monthly quota).
- Decide the reverse direction too: if SAIA is primary and hits its cap, whether to fall back to local Ollama automatically.

## 3. Voicebot preparation

The conversation engine (`backend/graph/`) assumes text input end-to-end. To support a future voicebot (spoken concern → transcription → existing chat flow), the concern-intake path needs to be decoupled from "text typed in Streamlit":
- Add a transcription step (e.g. Whisper, local or API) ahead of `extract_information` in the graph, producing the same text shape the graph already expects.
- Check whether `extract_information` and the intent/category classifiers are robust to transcription artifacts (disfluencies, missing punctuation, ASR errors) — they were tuned against typed text.
- Decide where transcription happens: frontend (upload/record audio, send text to backend) vs. backend (accept audio, transcribe server-side) — the latter keeps the API contract audio-and-text agnostic.
- No text-to-speech / response side was discussed — only inbound transcription. If a voicebot needs spoken responses too, that's a separate, unscoped piece of work.

## 4. Email intake channel

Same idea as the voicebot, different channel: allow a concern to arrive as an email rather than a chat message.

- Needs an inbound mailbox listener (Zammad already receives/sends mail via Mailpit in dev — check whether Zammad's own email-to-ticket ingestion can be reused instead of building a parallel path).
- An incoming email would need to be mapped onto the same `ChatbotState` (`backend/graph/state.py`) shape the chat flow uses — likely treating the email body as the first user message and running it through `extract_information` once, since there's no back-and-forth turn structure like chat has.
- Multi-turn follow-up (the bot asking clarifying questions) is awkward over email compared to chat — decide whether email tickets skip `ask_for_additional_info` and go straight to best-effort classification, or whether follow-ups are sent as reply emails.

## 5. Persistent login session (localStorage/cookie instead of URL token)

The IdP `session_token` currently lives in the URL query string; `keep_session_token()` (`frontend/ui/session.py`) caches it in `session_state` and re-asserts it into the URL so identity survives page navigation and reloads **within** the running browser session. It does **not** survive a new tab or a browser restart, and carrying the token in the URL exposes it (XSS / shoulder-surfing / history).

This was deliberately left minimal: **this frontend exists only to demonstrate the backend's functionality.** Customers are expected to integrate the backend (`/chat`, `/faq`, …) into their own frontend later, which would bring its own authentication/session handling — so investing in production-grade session persistence in this demo UI is out of scope.

If a future demo does need cross-tab / restart persistence:
- Streamlit cannot **set** cookies from Python (`st.context.cookies` is read-only), and the IdP runs on a different origin (`:5000`/`:4999`) than the app (`:8501`), so a cookie set by the IdP isn't sent to the app. A JS-based component (e.g. `extra-streamlit-components` CookieManager, `streamlit-local-storage`) would be needed — a new dependency.
- Prefer a **same-origin HttpOnly cookie** (behind a shared reverse proxy) over localStorage/URL for the token, since HttpOnly is not readable by JS. That means fronting IdP + app under one origin, which is an infrastructure change, not just a frontend one.

## Additional recommendations (not from prior discussion)

- **Known open issue**: when no FAQ/ticket solution matches, the fallback to auto-create a ticket doesn't always trigger, and the bot can loop asking follow-up questions instead. This pre-dates this document and should probably be prioritized before any of the above, since it affects the core flow today.
- **Prompt security / penetration testing**: While testing of the chatbot we did not test sending potentially dangerous (illegal / prompt injection) prompts to the SAIA API to avoid misunderstandings with the GWDG SAIA API admins about the intent of our prompts. The LLM has a guard against prompt injections and illegal topics built-in from its manufacturer. Using our agent file (`backend/llm/agents/ZIM.md`) we additionally instruct the bot to not answer questions that are not ZIM related which is tested in `tests/test_llm_off_topic_reactions.py`. The implementation of the DeepEval tests has been modularized to facilitate adding more chat tests in the future. The template class for such test suites can be found in `tests/llm_benchmark_template.py`. In the future, when deploying the chatbot on university servers, more advanced prompt security tests can be done locally using DeepEval. 
- **SAIA quota tracking**: there's currently no visible counter for the 3,000 req/month SAIA limit, unless manually sending a curl request to the SAIA API according to the instructions in the SAIA documentation (https://docs.hpc.gwdg.de/services/ai-services/saia/index.html#api-limits) — a lightweight usage counter/log would help avoid finding out about the cap by hitting it mid-sprint, and becomes more important if the local/API fallback (#2) is added. 
- **Incident escalation thresholds**: `backend/config.py` exposes `INCIDENT_ESCALATION_MIN_COUNT`, `INCIDENT_RECENCY_WINDOW_HOURS`, `INCIDENT_SIMILARITY_THRESHOLD` — these were set during development but haven't been validated against real usage volume; worth revisiting once real ticket traffic exists.
