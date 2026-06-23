# LLM helpers

This folder contains the LLM integration code: wrappers around the chosen model runtime and prompt templates used by extraction and summarisation nodes.

Files
- `llm.py` — LLM client wrapper. Abstracts the underlying LLM runtime (Ollama, SAIA/OpenAI-compatible endpoint). Provides convenience functions for completions, chat calls and temperature/config overrides.
- `prompts.py` — central place for prompt templates, system messages and any few-shot examples used across the graph. Keeping prompts here improves consistency and makes prompt-testing easier.

Configuration
- The backend can be configured to use an on-prem Ollama instance or a remote SAIA-compatible API. Typical environment variables:
  - `OLLAMA_HOST` / `OLLAMA_PORT`
  - `SAIA_API_URL` / `SAIA_API_KEY`

Usage
- Nodes that need LLM capabilities import `llm.llm` and call the appropriate function (e.g. `generate_extract`, `summarize_retrievals`).
- Prompt templates are stored in `prompts.py` and referenced by name. Use named templates rather than inline strings for maintainability.

Best practices
- Keep prompts focused and document expected input/output in `prompts.py`.
- Sanitize or limit user-provided content before sending it to the model to reduce prompt-injection risks.

See `../README_BACKEND.md` for higher-level architecture and `../graph/README.md` for how LLM nodes are orchestrated.

