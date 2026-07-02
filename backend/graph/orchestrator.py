import os
from pathlib import Path

from langchain_core.tracers import LangChainTracer
from langgraph.graph import StateGraph, START, END
from .state import ChatbotState
from .nodes import (
    extract_information,
    ask_for_email,
    ask_for_matrikelnummer,
    ask_for_issue,
    ask_for_additional_info,
    classify_ticket,
    give_solutions,
    finish_ticket,
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

    print("\n===== FINAL UPDATED STATE =====")
    print(f"Email:       {updated_state.get('user_email')}")
    print(f"Matrikelnr.:    {updated_state.get('matrikelnummer')}")
    print(f"Problem:     {updated_state.get('issue_description')}")
    print(f"Additional Info: {updated_state.get('additional_info')}")
    print("==============================================\n")

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
    }

def route_based_on_state(state: ChatbotState):
    """
    Determine the next workflow node based on the missing
    required information.
    """
    if not state.get("user_email"):
        return "ask_email_node"

    elif not state.get("matrikelnummer"):
        return "ask_matrikel_node"

    elif not state.get("issue_description"):
        print(f"[DEBUG]: Attempts for ask_for_issue node: {state.get('ask_issue_attempts')}")
        if state.get("ask_issue_attempts") >= 3:
            return "finish_node"
        else:
            return "ask_issue_node"

    else:
        return "ask_for_additional_info"

def route_after_evaluator(state: ChatbotState):
    """
    Determine whether enough information has been collected.

    If all required information is available, search for suitable
    solutions. Otherwise, end the current workflow so the user can
    provide additional information.
    """
    if state.get("needs_additional_info"):
        return "classify_ticket_node"
    else:
        return END

def route_after_solutions(state: ChatbotState):
    """
    Determine the next step after searching for solutions.

    If solutions were found, wait for user feedback unless the
    conversation is already complete. If no solutions were found,
    create a ticket immediately.

    :param state: Current chatbot state
    :return: Next workflow node
    """
    if state.get("solutions"):
        if state.get("is_complete"):
            return "finish_node"
        else:
            return END
    else:
        return "finish_node"


def build_pathmap_from_nodes_list_for_visualisation(nodes_list:list[str]):
    output = {}
    for node_name in nodes_list:
        output[node_name] = node_name
    return output



# Initialize the workflow using the ChatbotState schema.
workflow = StateGraph(ChatbotState)

# Register all workflow nodes.
workflow.add_node("extractor_node", extract_information)
workflow.add_node("ask_email_node", ask_for_email)
workflow.add_node("ask_matrikel_node", ask_for_matrikelnummer)
workflow.add_node("ask_issue_node", ask_for_issue)
workflow.add_node("ask_for_additional_info", ask_for_additional_info)
workflow.add_node("classify_ticket_node", classify_ticket)
workflow.add_node("give_solutions_node", give_solutions)
workflow.add_node("finish_node", finish_ticket)

# Define the workflow entry point.
workflow.add_edge(START, "extractor_node")

# Route dynamically based on the extracted conversation state.
workflow.add_conditional_edges(
    source="extractor_node",
    path=route_based_on_state,
    path_map=build_pathmap_from_nodes_list_for_visualisation(
        ["ask_email_node", "ask_matrikel_node", "ask_issue_node",
         "ask_for_additional_info", "finish_node"]
    )
)

# Route after evaluating the additional information.
workflow.add_conditional_edges(
    source="ask_for_additional_info",
    path=route_after_evaluator,
    path_map=build_pathmap_from_nodes_list_for_visualisation(
        ["classify_ticket_node", "__end__"]
    )
)

workflow.add_edge("classify_ticket_node", "give_solutions_node")

# Route after retrieving possible solutions.
workflow.add_conditional_edges(
    source="give_solutions_node",
    path=route_after_solutions,
    path_map=build_pathmap_from_nodes_list_for_visualisation(
        ["finish_node", "__end__"]
    )
)


# End the workflow after the information collection nodes.
workflow.add_edge("ask_email_node", END)
workflow.add_edge("ask_matrikel_node", END)
workflow.add_edge("ask_issue_node", END)
workflow.add_edge("finish_node", END)

# Compile the workflow into an executable LangGraph graph.
graph = workflow.compile()

# Wraps the graph with the LangSmith tracer
# to create a detailed result on how the workflow went
graph = graph.with_config({'callbacks': [tracer]})


if __name__ == "__main__":
    filename_for_graph_image = os.path.join(Path(__file__).parent, "langgraph.png")

    with open(filename_for_graph_image, "wb") as f:
        print("Creating PNG visualisation of the graph...")
        f.write(graph.get_graph().draw_mermaid_png())
        print(f'Image saved at {filename_for_graph_image}.')