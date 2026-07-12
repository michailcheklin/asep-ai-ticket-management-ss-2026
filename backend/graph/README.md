# Graph (LangGraph)

## Prerequisites for LangSmith tracing:
To be able to trace the LangGraph flow using LangSmith you need to do following steps:
1. Go to https://smith.langchain.com/
2. Select the **EU** Data Region
3. Sign up with an e-mail and set a password to create an account
4. On account confirmation choose "Technical" and then "LangSmith".
5. Go to ⚙️ Settings > Access and Security > API Keys
6. Click "+ API Key"
7. Choose "Personal Access Token" and choose a name for the LangSmith API key
8. Copy your API key
9. Paste the following text into your .env file:
```
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=(langsmith API key copied in step 8)
LANGSMITH_ENDPOINT=https://eu.api.smith.langchain.com
```

This folder contains the LangGraph workflow used to orchestrate extraction, clarification and retrieval steps. The graph is responsible for executing small, composable nodes that together implement the backend conversation logic.

## Structure
- `nodes.py` — implementation of individual LangGraph nodes. Nodes encapsulate single responsibilities such as extracting entities, classifying priority, or formatting output.
- `orchestrator.py` — graph assembly and execution. The orchestrator composes nodes into a workflow and provides an entry point for the API layer.
- `state.py` — Pydantic models and the runtime `State` object passed between nodes.
- `models/` — typed models used by nodes (see `graph/models/README.md`).

## Concepts
- Nodes are small functions or classes that accept a `State` and return an updated `State` (or raise a controlled error). This design improves testability and makes the workflow easy to extend.
- The orchestrator wires nodes together and manages retry/loop logic (e.g. asking for missing information up to N times).

## Agent behavior across nodes
- Behavior that should apply regardless of which node is active (bot identity, topical scope, off-topic handling, truthfulness, tone/conciseness) is centralized in `../llm/AGENTS/<name>.md`, selected via the `AGENT` environment variable and loaded once as `AGENT_PROMPT` by `../llm/llm.py` (see `../llm/README.md`).
- Nodes that build a system prompt import `AGENT_PROMPT` and prepend it (`AGENT_PROMPT + "\n\n" + <node-specific prompt>`). Keep the node-specific prompt limited to what's actually unique to that node's task — don't re-state identity, scope, or tone rules that already live in the agent file.

## Extending the graph
1. Add small, focused node functions in `nodes.py` or a new module.
2. Add any required typed models to `graph/models`.
3. Update `orchestrator.py` to include the new node in the appropriate place in the workflow.
4. If the node builds its own system prompt, prepend `AGENT_PROMPT` per "Agent behavior across nodes" above.
5. Write unit tests that validate the node behaviour on edge cases.

## Runtime
- The API layer (`api/ZIM.py`) calls into `graph.orchestrator` with a `State` constructed from the incoming request. The graph returns the final state which is then serialized and returned to the client.

## Common responsibilities implemented by nodes
- Information extraction (issue description, affected services, OS, etc.)
- Priority classification
- Missing information detection and question generation
- Triggering RAG retrieval nodes (calls out to `rag/` components)
- Preparing final ticket payload for `services/TicketService`

See `../README_BACKEND.md` for overall architecture and `../llm/README.md` for LLM and prompt details.


## Visualisation of the graph in a PNG image:

The Langgraph is converted to a PNG image using the `draw_png` method from Langchain (cf. https://reference.langchain.com/python/langchain-core/runnables/graph/Graph/draw_png), after the Graph object has been extracted from the Langgraph using the `get_graph` method (cf. https://reference.langchain.com/python/langgraph/graph/state/CompiledStateGraph and https://reference.langchain.com/python/langgraph/pregel/main/Pregel/get_graph). The Langchain methods require the `pygraphviz` library to be installed (cf https://reference.langchain.com/python/langchain-core/runnables/graph_png/PngDrawer).

To get the most up-to-date PNG image of the Langgraph's nodes and their connections, do the following steps:
1. Switch to the project root in the terminal
2. Execute `python -m backend.graph.orchestrator`
3. When the script has finished, an image at `<project root>/backend/graph/langgraph.png` has been created

In the image each node is written with its name. The START node is named `__start__` and the END node is named `__end__`. A dotted arrow means that that is a conditional edge. A non-dotted arrow means an unconditional edge. A limitation of the automatic generation of the image is that it is not shown, what the exact condition is. Instead, to check the condition on which it is decided what node to change to, do these steps:
1. Go to the file `<project root>/backend/graph/orchestrator.py`
2. Search the `workflow.add_conditional_edges()` call that has as the `source` parameter the wanted start node
3. From there, go to the definition of the function that was passed as the `path` parameter

When you do changes on the Langgraph, that add conditional edges with `workflow.add_conditional_edges`, or modify existing conditional edges, you need to explicitely set these arguments to ensure that the image of the graph gets created correctly:
* `source`= [name of the source node as a string],
* `path`= [name of the routing function as function reference] - **Do not call this function by adding `"()"` at the end**
* `path_map = build_pathmap_from_nodes_list_for_visualisation(string_array)`, where `string_array` is the list of all node names that occur in the return statements of the function that was provided to the `path` argument. If the END node is returned, add `"__end__"` in this string array to represent the END node.

```mermaid
graph TD
    %% --- START & END ---
    Start(((START)))
    End(((END)))


     %% --- KLASSIFIKATION & ZWEI PFADE  ---
    classify_intent_node[classify_intent_node <br> classify_intent]
    ask_intent_node[ask_intent_node <br> ask_intent]
    give_tutorial_node[give_tutorial_node <br> give_tutorial]
    finish_tutorial_node[finish_tutorial_node <br> finish_tutorial]
    escalate_incidents_node[escalate_incidents_node <br> escalate issue]

    %% --- ALLE REGISTRIERTEN NODES ---
    extractor_node[extractor_node <br> extract_information]
    ask_email_node[ask_email_node <br> ask_for_email]
    ask_issue_node[ask_issue_node <br> ask_for_issue]
    ask_for_additional_info[ask_for_additional_info]
    classify_ticket_node[classify_ticket_node <br> classify_ticket]
    give_solutions_node[give_solutions_node <br> give_solutions]
    finish_node[finish_node <br> finish_ticket]

    %% --- ROUTER (CONDITIONAL EDGES) ---
    route_after_intent{route_after_intent}
    route_based_on_state{route_based_on_state}
    route_after_evaluator{route_after_evaluator}
    route_after_solutions{route_after_solutions}

    %% --- VERBINDUNGEN NACH CODE-LOGIK ---
    
    %% Entry Point
    Start --> classify_intent_node
    
    %% Erster Conditional Router
    classify_intent_node --> route_after_intent
    
    route_after_intent -->|not user_email| ask_email_node
    route_after_intent -->|intent solved & tutorial_attempts > 0| finish_tutorial_node
    route_after_intent -->|intent tutorial & tutorial_attempts < 2| give_tutorial_node
    route_after_intent -->|intent tutorial & tutorial_attempts >= 2| extractor_node
    route_after_intent -->|intent problem| extractor_node
    route_after_intent -->|else / unclear| ask_intent_node


    %% --- Tutorial-Pfad endet und wartet auf Nutzer ---
    give_tutorial_node --> End
    ask_intent_node --> End
    finish_tutorial_node --> End

    %% --- Ticket-Pfad: Vollstaendigkeit pruefen ---
    extractor_node --> route_based_on_state
    route_based_on_state -->|not user_email| ask_email_node
    route_based_on_state -->|not issue & attempts < 3| ask_issue_node
    route_based_on_state -->|not issue & attempts >= 3| finish_node
    route_based_on_state -->|else| ask_for_additional_info

    ask_email_node --> End
    ask_issue_node --> End

    %% --- Zusatzinfos auswerten ---
    ask_for_additional_info --> route_after_evaluator
    route_after_evaluator -->|needs_additional_info == True| classify_ticket_node
    route_after_evaluator -->|else| End

    classify_ticket_node --> escalate_incidents_node
    escalate_incidents_node --> give_solutions_node

    %% --- Loesungen anbieten ---
    give_solutions_node --> route_after_solutions
    route_after_solutions -->|solutions & is_complete| finish_node
    route_after_solutions -->|solutions & not is_complete| End
    route_after_solutions -->|not solutions| finish_node

    finish_node --> End

    %% --- STYLING ---
    style Start fill:#dcedc8,stroke:#689f38
    style End fill:#ffcdd2,stroke:#c62828

    style classify_intent_node fill:#c8e6c9,stroke:#2e7d32
    style ask_intent_node fill:#c8e6c9,stroke:#2e7d32
    style give_tutorial_node fill:#c8e6c9,stroke:#2e7d32
    style finish_tutorial_node fill:#c8e6c9,stroke:#2e7d32

    style extractor_node fill:#bbdefb,stroke:#1976d2
    style classify_ticket_node fill:#bbdefb,stroke:#1976d2
    style give_solutions_node fill:#bbdefb,stroke:#1976d2
    style escalate_incidents_node fill:#bbdefb,stroke:#1976d2
    style finish_node fill:#bbdefb,stroke:#1976d2

    style ask_email_node fill:#ffecb3,stroke:#ff8f00
    style ask_issue_node fill:#ffecb3,stroke:#ff8f00
    style ask_for_additional_info fill:#ffecb3,stroke:#ff8f00
```