# Contributing

## Language convention

**English** is the standard language for all source code and technical documentation in this repository.

| Use English for | Keep German when |
|---|---|
| Variable, function, class, and constant names | User-facing UI copy (Streamlit labels, buttons, placeholders) |
| Comments and docstrings | Chatbot replies shown to end users |
| Developer-facing log and print messages | LLM system prompts that drive German product dialogue |
| Technical / CI error messages | Zammad ticket body text intended for German support agents |
| Development and contribution docs | FAQ / RAG corpora and other localized content data |
| New tests, mocks, and fixtures (except asserted UI strings) | Translation / localization files; Pydantic `Field(description=...)` text that steers LLM structured output for German dialogue |

### Naming

- Prefer clear English identifiers (`resolve_zammad_category`, `update_ticket_category`).
- Do **not** rename external contracts solely for consistency:
  - Zammad custom field API key: `"kategorie"`
  - Chat / state field: `matrikelnummer`
  - Environment variable names already in use
  - Database attributes and third-party API field names
- When an external name must stay non-English, document it near the boundary (comment or docstring) and use an English name for the internal Python parameter/helper.

### Behaviour

Language cleanup must not change application behaviour. Do not translate intentional German product text as part of a naming cleanup.
