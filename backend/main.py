"""API für AI Ticket System; optionale Anbindung an Zammad (REST)."""
import concurrent.futures
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import HumanMessage, AIMessage
from state import ChatbotState
from nodes import (
    extract_information,
    ask_for_email,
    ask_for_matrikelnummer,
    ask_for_issue,
    finish_ticket,
    ask_for_additional_info
)
from pydantic import BaseModel
from typing import List, Dict
from prompt_security_result import (
    evaluate_prompt_injection,
    evaluate_legality,
    evaluate_off_topic
)

# Create FastAPI application instance
app = FastAPI(title="AI Ticket API", version="1.0.0")

# Enable CORS so frontend applications can access the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Read Zammad configuration from environment variables
ZAMMAD_BASE = os.getenv("ZAMMAD_INTERNAL_URL", "").rstrip("/")
ZAMMAD_TOKEN = os.getenv("ZAMMAD_API_TOKEN", "").strip()
ZAMMAD_GROUP_ID = int(os.getenv("ZAMMAD_DEFAULT_GROUP_ID", "1"))



def _zammad_headers() -> dict[str, str]:
    """Create authentication headers for Zammad API requests."""
    if not ZAMMAD_TOKEN:
        return {}
    return {"Authorization": f"Token token={ZAMMAD_TOKEN}"}


@app.get("/")
def root():
    """Root endpoint of the backend API."""
    return {
        "message": "AI Ticket Management Backend läuft"
    }




@app.get("/status")
def status():
    """Return current backend status."""
    return {
        "status": "online"
    }


@app.get("/health")
def health():
    """Health check endpoint for monitoring and Docker checks."""
    return {
        "healthy": True
    }

class ChatRequest(BaseModel):
    """
    datastructure for frontend requests
    """
    user_message: str
    history: List[Dict[str, str]]  # Format: [{"role": "user", "content": "Hallo"}, {"role": "bot", "content": "Hi"}]
    user_email: str = ""
    matrikelnummer: str = ""
    issue_description: str = ""
    additional_info: List[str] = []
    priority: int = 0

def __check_prompt (prompt:str) -> list[dict]:
    """
    Diese Methode prüft einen Prompt auf Prompt Injection, illegale Themen
    und auf nicht-ZIM-bezogene Themen und gibt für die Logs eine strukturierte Ausgabe
    :param prompt: Der Prompt, der auf seine Sicherheit geprüft werden soll
    :return: Die Ergebnisse als eine Liste von Objekten, die jeweils beschreiben was und mit welchem Ergebnis der Prompt geprüft wird
    """
    # Validate the user input for potential prompt injection attempts before
    # passing it to the chatbot workflow. If the request is classified as unsafe
    # it is blocked and not forwarded to the chatbot or the RAG-based knowledge base.
    # Execute the checks all at the same time
    with (concurrent.futures.ThreadPoolExecutor() as executor):
        prompt_injection_detection = executor.submit(evaluate_prompt_injection, prompt)
        illegal_topics_detection = executor.submit(evaluate_legality, prompt)
        off_topic_detection = executor.submit(evaluate_off_topic, prompt)

        prompt_injection_detection_result = prompt_injection_detection.result()
        illegal_topics_detection_result = illegal_topics_detection.result()
        off_topic_detection_result = off_topic_detection.result()

    complete_evaluation = [
        prompt_injection_detection_result,
        illegal_topics_detection_result,
        off_topic_detection_result
    ]

    return complete_evaluation

def __formulate_prompt_rejection_reason(failed_checks:list[dict]) -> str:
    """
    Diese Methode formuliert basierend darauf, warum der Prompt abgelehnt wurde,
    den Grund als Text.
    :param failed_checks: Die Liste der nicht bestandenen Sicherheitschecks, die
    aus der Liste, die nach der Nutzung der __check_prompt-Methode entsteht,
    gefiltert wurde
    :return: Der Grund, warum ein Prompt abgelehnt wurde als Text
    """

    # Leaving the code format like that, so that if separate user-visible rejection messages
    # are needed, only the return strings have to be changed here.
    reason = ""
    if len(failed_checks) == 0:
        return ""
    if failed_checks[0]["checked_for"] == "legality of prompt":
        reason = "Diese Anfrage wurde blockiert, weil diese gegen die Richtlinien des Chatbots verstößt."
    elif failed_checks[0]["checked_for"] == "prompt injection":
        reason = "Diese Anfrage wurde blockiert, weil diese gegen die Richtlinien des Chatbots verstößt."
    elif failed_checks[0]["checked_for"] == "off-topic":
        reason = "Diese Anfrage wurde blockiert, weil diese gegen die Richtlinien des Chatbots verstößt."
    return reason

@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    """
    API Endpoint to chat with the llm
    :param request: the state of the conversation
    :return: returns the updated state, after the llm processed the request
    """

    # Temporarily disabled our own security implementation
    # Now the chatbot's AI model itself stops bad prompts
    """
    complete_evaluation = __check_prompt(request.user_message)

    failed_checks = [check_result for check_result in complete_evaluation if not check_result["allowed"]]
    if len(failed_checks) > 0:
        print(failed_checks)
        reason = __formulate_prompt_rejection_reason(failed_checks)

        return {
            "bot_response": f"{reason} Bitte formuliere eine normale Anfrage zu einem ZIM-Thema.",
            "security": complete_evaluation,
            "user_email": request.user_email,
            "matrikelnummer": request.matrikelnummer,
            "issue_description": request.issue_description,
            "is_complete": False,
            "priority": request.priority,
        }

    """


    return __execute_langchain_workflow(request)
  


    


def __execute_langchain_workflow(request: ChatRequest):
    """
    Diese Methode generiert eine Antwort basierend auf dem Chatverlauf und dem Prompt. Diese Methode wird nur dann ausgeführt,
    wenn der Prompt alle Sicherheitschecks bestanden hat.
    :param request: Das JSON-Objekt, das an den Chat-Endpoint gesendet wurde
    :return: Das Antwort-JSON-Objekt, nachdem darauf der Langchain-Workflow ausgeführt wurde
    """
    langchain_messages = []
    for msg in request.history:
        if msg["role"] == "user":
            langchain_messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "bot":
            langchain_messages.append(AIMessage(content=msg["content"]))

    langchain_messages.append(HumanMessage(content=request.user_message))

    current_state = {
        "messages": langchain_messages,
        "user_email": request.user_email,
        "matrikelnummer": request.matrikelnummer,
        "issue_description": request.issue_description,
        "additional_info": request.additional_info,
        "is_complete": False,
        "priority": request.priority
    }

    updated_state = graph.invoke(current_state)
    bot_response = updated_state["messages"][-1].content
    return {
        "bot_response": bot_response,
        "user_email": updated_state.get("user_email", ""),
        "matrikelnummer": updated_state.get("matrikelnummer", ""),
        "issue_description": updated_state.get("issue_description", ""),
        "additional_info": updated_state.get("additional_info", []),
        "is_complete": updated_state.get("is_complete", False),
        "priority": updated_state.get("priority", 0),
    }

def route_based_on_state(state: ChatbotState):
    """
    Checks state and decides which node is called next. Depended on missing relevant information
    """
    if not state.get("user_email"):
        return "ask_email_node"

    elif not state.get("matrikelnummer"):
        return "ask_matrikel_node"

    elif not state.get("issue_description"):
        return "ask_issue_node"

    else:
        return "ask_for_additional_info"

def route_after_evaluator(state: ChatbotState):
    """
    Checks result of additional information node. If all needed information are collected the finish node
    is called, otherwise the workflow start all over again
    """
    if state.get("is_complete"):
        return "finish_node"
    else:
        return END



# Initialize the state graph configuration with the defined ChatbotState schema
workflow = StateGraph(ChatbotState)

# Register all functional nodes within the workflow
workflow.add_node("extractor_node", extract_information)
workflow.add_node("ask_email_node", ask_for_email)
workflow.add_node("ask_matrikel_node", ask_for_matrikelnummer)
workflow.add_node("ask_issue_node", ask_for_issue)
workflow.add_node("ask_for_additional_info", ask_for_additional_info)
workflow.add_node("finish_node", finish_ticket)

# Set the mandatory entry point of the graph execution
workflow.add_edge(START, "extractor_node")

# Dynamically route to the next node based missing information
workflow.add_conditional_edges(
    "extractor_node",
    route_based_on_state
)

# Switch after the additional information node
workflow.add_conditional_edges(
    "ask_for_additional_info",
    route_after_evaluator
)

workflow.add_edge("ask_email_node", END)
workflow.add_edge("ask_matrikel_node", END)
workflow.add_edge("ask_issue_node", END)
workflow.add_edge("finish_node", END)

# Compile the graph architecture into an executable LangGraph application
graph = workflow.compile()

def run_local_chat():
    """
        [ONLY FOR TESTING]
        Provides a local terminal interface to test the chatbot workflow
        without running the FastAPI server or an external frontend
    """
    print("\n========================================================")
    print("🤖 IT-Support Bot V2 (Spoon-Feeding) gestartet")
    print("Tippe 'exit' zum Beenden")
    print("========================================================\n")

    current_state = {
        "messages": [],
        "user_email": "",
        "matrikelnummer": "",
        "issue_description": "",
        "additional_info": [],
        "is_complete": False
    }

    print("Bot: Hallo! Willkommen beim IT-Support. Wie kann ich dir heute helfen?")

    while True:
        user_input = input("\nDu: ")

        if user_input.lower() in ["exit", "quit", "q"]:
            break

        # Validate the user input for potential prompt injection attempts
        # before passing it to the chatbot workflow.
        # Temporarily disabled security check - Now the chatbot's built in filter is used

        """
        complete_evaluation = __check_prompt(user_input)
        failed_checks = [check_result for check_result in complete_evaluation if not check_result["allowed"]]
        if len(failed_checks) > 0:
            print(failed_checks)
            reason = __formulate_prompt_rejection_reason(failed_checks)

            print(
                f"Bot: {reason} "
                "Bitte formuliere eine normale Anfrage zu einem ZIM-Thema."
            )
            print(f"   [SECURITY DEBUG] {complete_evaluation}")
            continue
        """


        current_state["messages"].append(HumanMessage(content=user_input))
        current_state = graph.invoke(current_state)

        print(str(current_state))
        bot_response = current_state["messages"][-1].content
        print(f"Bot: {bot_response}")
        print(
            f"   [DEBUG STATE] email: {current_state.get('user_email')} | "
            f"Matrikel: {current_state.get('matrikelnummer')} | "
            f"Problem: {current_state.get('issue_description')}"
        )

        if current_state.get("is_complete"):
            print("\n🎉 [SYSTEM]: backend feuert API-Call an Zammad!")
            break


if __name__ == "__main__":
    run_local_chat() 