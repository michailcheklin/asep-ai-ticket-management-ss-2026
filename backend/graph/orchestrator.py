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
    return {
        "bot_response": bot_response,
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
    "extractor_node",
    route_based_on_state
)

# Route after evaluating the additional information.
workflow.add_conditional_edges(
    "ask_for_additional_info",
    route_after_evaluator
)

workflow.add_edge("classify_ticket_node", "give_solutions_node")

# Route after retrieving possible solutions.
workflow.add_conditional_edges(
    "give_solutions_node",
    route_after_solutions
)


# End the workflow after the information collection nodes.
workflow.add_edge("ask_email_node", END)
workflow.add_edge("ask_matrikel_node", END)
workflow.add_edge("ask_issue_node", END)
workflow.add_edge("finish_node", END)

# Compile the workflow into an executable LangGraph graph.
graph = workflow.compile()

