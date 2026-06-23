# Graph (LangGraph)

This folder contains the LangGraph workflow used to orchestrate extraction, clarification and retrieval steps. The graph is responsible for executing small, composable nodes that together implement the backend conversation logic.

Structure
- `nodes.py` — implementation of individual LangGraph nodes. Nodes encapsulate single responsibilities such as extracting entities, classifying priority, or formatting output.
- `orchestrator.py` — graph assembly and execution. The orchestrator composes nodes into a workflow and provides an entry point for the API layer.
- `state.py` — Pydantic models and the runtime `State` object passed between nodes.
- `models/` — typed models used by nodes (see `graph/models/README.md`).

Concepts
- Nodes are small functions or classes that accept a `State` and return an updated `State` (or raise a controlled error). This design improves testability and makes the workflow easy to extend.
- The orchestrator wires nodes together and manages retry/loop logic (e.g. asking for missing information up to N times).

Extending the graph
1. Add small, focused node functions in `nodes.py` or a new module.
2. Add any required typed models to `graph/models`.
3. Update `orchestrator.py` to include the new node in the appropriate place in the workflow.
4. Write unit tests that validate the node behaviour on edge cases.

Runtime
- The API layer (`api/ZIM.py`) calls into `graph.orchestrator` with a `State` constructed from the incoming request. The graph returns the final state which is then serialized and returned to the client.

Common responsibilities implemented by nodes
- Information extraction (issue description, affected services, OS, etc.)
- Priority classification
- Missing information detection and question generation
- Triggering RAG retrieval nodes (calls out to `rag/` components)
- Preparing final ticket payload for `services/TicketService`

See `../README_BACKEND.md` for overall architecture and `../llm/README.md` for LLM and prompt details.

