# LLM helpers

This folder contains the LLM integration code: wrappers around the chosen model runtime and prompt templates used by extraction and summarisation nodes.

Files
- `llm.py` — LLM client wrapper. Abstracts the underlying LLM runtime (Ollama, SAIA/OpenAI-compatible endpoint). Provides convenience functions for completions, chat calls and temperature/config overrides. Also loads the shared agent behavior file (see "Agent behavior" below) into `AGENT_PROMPT` at import time.
- `prompts.py` — central place for prompt templates, system messages and any few-shot examples used across the graph. Keeping prompts here improves consistency and makes prompt-testing easier.
- `AGENTS/` — markdown files defining agent-wide LLM behavior (see "Agent behavior" below).

Configuration
- The backend can be configured to use an on-prem Ollama instance or a remote SAIA-compatible API.  
- Environment Variables:
  - `USE_SAIA_API`: `true`/`false`- whether to use the SAIA API or not
  - `SAIA_API_KEY`: The API key to be used (here: SAIA)
  - `AGENT`: name of the agent behavior file to load from `AGENTS/`, without the `.md` extension (e.g. `AGENT=ZIM` loads `AGENTS/ZIM.md`). Required — `llm.py` raises an exception at import time if it is unset or the file doesn't exist.

Agent behavior
- `AGENTS/<name>.md` holds the behavior that should apply across *all* LangGraph nodes, regardless of which node currently has control — e.g. the bot's identity, its topical scope, how to handle off-topic requests, truthfulness expectations, and tone/conciseness. It is a single flat block of text, not per-node sections.
- `llm.py` reads the file named by `AGENT` once at import time and exposes it as the plain string `AGENT_PROMPT`.
- Node-specific prompts in `graph/nodes.py` prepend `AGENT_PROMPT` to their own system prompt (`AGENT_PROMPT + "\n\n" + <node-specific prompt>`) rather than repeating the shared rules — keep node prompts limited to what's actually specific to that node's task.

Usage
- Nodes that need LLM capabilities import `llm.llm` and call the appropriate function 
- Prompt templates are stored in `prompts.py` and referenced by name. Use named templates rather than inline strings for maintainability.
- Nodes that build their own system prompt should import `AGENT_PROMPT` from `llm.py` and prepend it, per the "Agent behavior" section above.

Best practices
- Keep prompts focused and document expected input/output in `prompts.py`.
- Sanitize or limit user-provided content before sending it to the model to reduce prompt-injection risks.

See `../README_BACKEND.md` for higher-level architecture and `../graph/README.md` for how LLM nodes are orchestrated.

