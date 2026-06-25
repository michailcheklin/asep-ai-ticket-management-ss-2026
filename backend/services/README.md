# Services (Integrations)

This folder contains integration code responsible for creating and updating tickets and bridging the backend to external systems (Zammad).

Files
- `TicketService.py` — high-level ticket creation and update logic. The service composes ticket payloads from the graph's `State` and calls the low-level Zammad helpers.

Responsibilities
- Create new tickets (open or closed)
- Add tags and metadata (e.g. `AISolved`)
- Attach chat history and offered solutions to tickets when appropriate
- Map internal priority values to Zammad priority fields

Low-level Zammad helpers
- The low-level HTTP calls to Zammad are implemented in `api/Zammad.py`. Services should not call the Zammad REST API directly but go through these helpers to keep concerns separated.

Testing
- Services should be unit-tested with mocked Zammad responses. When running integration tests, provide a test Zammad instance or mock responses with a local HTTP server.

See `../README_BACKEND.md` and `../api/README.md` for full request/response flows.

