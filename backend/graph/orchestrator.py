import os
import copy
from pathlib import Path

from langchain_core.tracers import LangChainTracer
from langgraph.graph import StateGraph, START, END

from backend.graph.node_logging import langgraph_logger, truncate_long_strings_in_dicts_for_logging
from .state import ChatbotState
from .nodes import (
    extract_information,
    ask_for_issue,
    ask_for_additional_info,
    classify_ticket,
    escalate_incidents,
    give_solutions,
    finish_ticket,
    classify_intent,
    ask_intent,
    give_tutorial,
    finish_tutorial,
)

from .routing import (
    route_based_on_state,
    route_after_intent,
    route_after_evaluator,
    route_after_solutions,
    route_after_classification,
)

from langsmith import Client
from langsmith.anonymizer import create_anonymizer


# Matches E-mail addresses and censors them in LangSmith's dashboard
anonymizer = create_anonymizer([
    { "pattern": r"[a-zA-Z0-9\._-]+@[a-zA-Z0-9\._-]+\.[a-zA-Z0-9\._-]+", "replace": "<email>" }
])

tracer_client = Client(anonymizer=anonymizer)
tracer = LangChainTracer(client=tracer_client)

def __execute_langchain_workflow(state: ChatbotState):
    """
    Execute the LangGraph workflow.

    Converts the frontend request into the internal chatbot state,
    executes the workflow and returns the updated conversation state.

    :param request: Frontend request
    :return: Updated conversation state
    """

    updated_state = graph.invoke(state)
    bot_response = updated_state["messages"][-1].content

    # Creating a modified deep copy of the current state
    # to display it on the console in logs.
    # The original state is not modified.
    updated_state_display_for_logs = copy.deepcopy(updated_state)
    updated_state_display_for_logs["solutions"] = list(map(truncate_long_strings_in_dicts_for_logging, updated_state_display_for_logs["solutions"]))
    langgraph_logger.debug(f"Final updated state:\n{updated_state_display_for_logs}")
    langgraph_logger.debug(f"Run #{updated_state.get('graph_runs', 0)} — path: {' -> '.join(updated_state.get('visited_nodes', []))}")

    return {
        "bot_response": bot_response,
        "ticket_id": updated_state.get("ticket_id"),
        "user_email": updated_state.get("user_email", ""),
        "matrikelnummer": updated_state.get("matrikelnummer", ""),
        "issue_description": updated_state.get("issue_description", ""),
        "additional_info": updated_state.get("additional_info", []),
        "needs_additional_info": updated_state.get("needs_additional_info", False),
        "priority": updated_state.get("priority", 0),
        "category": updated_state.get("category", ""),
        "is_complete": updated_state.get("is_complete", False),
        "solutions": updated_state.get("solutions", []),
        "additional_info_attempts": updated_state.get("additional_info_attempts", 0),
        "ask_issue_attempts": updated_state.get("ask_issue_attempts", 0),
        "full_conversation": updated_state.get("full_conversation", ""),
        "intent": updated_state.get("intent", ""),
        "tutorial_attempts": updated_state.get("tutorial_attempts", 0),
        "display_name": updated_state.get("display_name", ""),
        "role": updated_state.get("role", ""),
        "faculty": updated_state.get("faculty", ""),
        "device": updated_state.get("device", ""),
        "os_name": updated_state.get("os_name", ""),
        "graph_runs": updated_state.get("graph_runs", 0),
    }


def build_pathmap_from_nodes_list_for_visualisation(nodes_list:list[str]):
    """
    Builds the path map for the visualization.
    The path map in a conditional edge takes the node names that are associated to the path names
    for the internal Graph object in the Langgraph graph. Without doing this, no conditional edges
    would appear if converting the graph to a PNG image
    :param nodes_list: The list of the nodes
    :return: A dictionary which is formed like this: Input: ["a", "b", "c"] - Output: {"a":"a", "b":"b", "c":"c"}
    """
    output = {}
    for node_name in nodes_list:
        output[node_name] = node_name
    return output



# Initialize the workflow using the ChatbotState schema.
workflow = StateGraph(ChatbotState)

# Register all workflow nodes.
workflow.add_node("extractor_node", extract_information)
workflow.add_node("ask_issue_node", ask_for_issue)
workflow.add_node("ask_for_additional_info", ask_for_additional_info)
workflow.add_node("classify_ticket_node", classify_ticket)
workflow.add_node("escalate_incidents_node", escalate_incidents)
workflow.add_node("give_solutions_node", give_solutions)
workflow.add_node("finish_node", finish_ticket)
workflow.add_node("classify_intent_node", classify_intent)
workflow.add_node("ask_intent_node", ask_intent)
workflow.add_node("give_tutorial_node", give_tutorial)
workflow.add_node("finish_tutorial_node", finish_tutorial)

# Define the workflow entry point.
workflow.add_edge(START, "extractor_node")

# Route based on the classified user intent
workflow.add_conditional_edges(
    source="classify_intent_node",
    path=route_after_intent,
    path_map=build_pathmap_from_nodes_list_for_visualisation(
        ["classify_ticket_node", "ask_for_additional_info", "ask_intent_node", "give_tutorial_node"]
    )
)


# Route dynamically based on the extracted conversation state.
workflow.add_conditional_edges(
    source="extractor_node",
    path=route_based_on_state,
    path_map=build_pathmap_from_nodes_list_for_visualisation(
        ["ask_issue_node", "finish_node", "classify_intent_node"]
    )
)


# Route after evaluating the additional information.
workflow.add_conditional_edges(
    source="ask_for_additional_info",
    path=route_after_evaluator,
    path_map=build_pathmap_from_nodes_list_for_visualisation(
        ["classify_ticket_node", "give_tutorial_node", "__end__"]
    )
)

workflow.add_conditional_edges(
    source="classify_ticket_node",
    path=route_after_classification,
    path_map=build_pathmap_from_nodes_list_for_visualisation(
        ["escalate_incidents_node", "finish_tutorial_node"]
    )
)

workflow.add_edge("escalate_incidents_node", "give_solutions_node")

# Route after retrieving possible solutions.
workflow.add_conditional_edges(
    source="give_solutions_node",
    path=route_after_solutions,
    path_map=build_pathmap_from_nodes_list_for_visualisation(
        ["finish_node", "__end__"]
    )
)


# End the workflow after the information collection nodes.
workflow.add_edge("ask_issue_node", END)
workflow.add_edge("finish_node", END)
workflow.add_edge("ask_intent_node", END)
workflow.add_edge("give_tutorial_node", END)
workflow.add_edge("finish_tutorial_node", END)

# Compile the workflow into an executable LangGraph graph.
graph = workflow.compile()

# Wraps the graph with the LangSmith tracer
# to create a detailed result on how the workflow went
graph = graph.with_config({'callbacks': [tracer]})


if __name__ == "__main__":
    # Runs only if run from the terminal without Docker
    filename_for_graph_image = os.path.join(Path(__file__).parent, "langgraph.png")

    with open(filename_for_graph_image, "wb") as f:
        print("Creating PNG visualisation of the graph...")
        f.write(graph.get_graph().draw_png())
        print(f'Image saved at {filename_for_graph_image}.')