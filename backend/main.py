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

def run_local_chat():
    """
        Provides a local terminal interface to test the chatbot workflow
        without running the FastAPI server or an external frontend
    """
    print("\n========================================================")
    print("🤖 IT-Support Bot V2 (Spoon-Feeding) gestartet")
    print("Tippe 'exit' zum Beenden")
    print("========================================================\n")

    current_state = {
        "messages": [],
        "customer_name": "",
        "matrikelnummer": "",
        "issue_description": "",
        "is_complete": False
    }

    print("Bot: Hallo! Willkommen beim IT-Support. Wie kann ich dir heute helfen?")

    while True:
        user_input = input("\nDu: ")
        if user_input.lower() in ["exit", "quit", "q"]:
            break

        current_state["messages"].append(HumanMessage(content=user_input))
        current_state = app.invoke(current_state)
        bot_response = current_state["messages"][-1].content
        print(f"Bot: {bot_response}")
        print(
            f"   [DEBUG STATE] Name: {current_state.get('customer_name')} | Matrikel: {current_state.get('matrikelnummer')} | Problem: {current_state.get('issue_description')}")

        if current_state.get("is_complete"):
            print("\n🎉 [SYSTEM]: backend feuert API-Call an Zammad!")
            break


if __name__ == "__main__":
    run_local_chat()