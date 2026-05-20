import sys
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import HumanMessage
from state import ChatbotState
from nodes import (
    extract_information,
    ask_for_name,
    ask_for_matrikelnummer,
    ask_for_issue,
    finish_ticket
)


def route_based_on_state(state: ChatbotState):
    """
    Checks state and decides which node is called next. Depended on missing relevant information
    """
    if not state.get("customer_name"):
        return "ask_name_node"

    elif not state.get("matrikelnummer"):
        return "ask_matrikel_node"

    elif not state.get("issue_description"):
        return "ask_issue_node"

    else:
        return "finish_node"



# Initialize the state graph configuration with the defined ChatbotState schema
workflow = StateGraph(ChatbotState)

# Register all functional nodes within the workflow
workflow.add_node("extractor_node", extract_information)
workflow.add_node("ask_name_node", ask_for_name)
workflow.add_node("ask_matrikel_node", ask_for_matrikelnummer)
workflow.add_node("ask_issue_node", ask_for_issue)
workflow.add_node("finish_node", finish_ticket)

# Set the mandatory entry point of the graph execution
workflow.add_edge(START, "extractor_node")

# Dynamically route to the next node based missing information
workflow.add_conditional_edges(
    "extractor_node",
    route_based_on_state
)

workflow.add_edge("ask_name_node", END)
workflow.add_edge("ask_matrikel_node", END)
workflow.add_edge("ask_issue_node", END)
workflow.add_edge("finish_node", END)

# Compile the graph architecture into an executable LangGraph application
app = workflow.compile()

