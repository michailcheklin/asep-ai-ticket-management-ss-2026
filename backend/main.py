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
    finish_ticket
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


@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    """
    API Endpoint to chat with the llm
    :param request: the state of the conversation
    :return: returns the updated state, after the llm processed the request
    """

    # Validate the user input for potential prompt injection attempts before
    # passing it to the chatbot workflow. If the request is classified as unsafe
    # it is blocked and not forwarded to the chatbot or the RAG-based knowledge base. 
    # Execute the checks all at the same time
    prompt:str = request.user_message
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

    indications = [not evaluation_result["allowed"] for evaluation_result in complete_evaluation]

    if len([indication for indication in indications if indication]) > 0:
        return {
            "bot_response": "Diese Anfrage wurde aus Sicherheitsgründen blockiert. Bitte formuliere eine normale Anfrage zu einem ZIM-Thema.",
            "security": complete_evaluation,
            "user_email": request.user_email,
            "matrikelnummer": request.matrikelnummer,
            "issue_description": request.issue_description,
            "is_complete": False
        }
  


    
    # translates JSON objects into LangChain objects
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
        "is_complete": False
    }

    updated_state = graph.invoke(current_state)
    bot_response = updated_state["messages"][-1].content
    return {
        "bot_response": bot_response,
        "user_email": updated_state.get("user_email", ""),
        "matrikelnummer": updated_state.get("matrikelnummer", ""),
        "issue_description": updated_state.get("issue_description", ""),
        "is_complete": updated_state.get("is_complete", False)
    }


# TODO: Prüfung des Prompts aus dem Mock-Prototyp in einen Endpunkt im Backend übertragen

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
        return "finish_node"



# Initialize the state graph configuration with the defined ChatbotState schema
workflow = StateGraph(ChatbotState)

# Register all functional nodes within the workflow
workflow.add_node("extractor_node", extract_information)
workflow.add_node("ask_email_node", ask_for_email)
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

workflow.add_edge("ask_email_node", END)
workflow.add_edge("ask_matrikel_node", END)
workflow.add_edge("ask_issue_node", END)
workflow.add_edge("finish_node", END)

# Compile the graph architecture into an executable LangGraph application
graph = workflow.compile()

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
        "user_email": "",
        "matrikelnummer": "",
        "issue_description": "",
        "is_complete": False
    }

    print("Bot: Hallo! Willkommen beim IT-Support. Wie kann ich dir heute helfen?")

    while True:
        user_input = input("\nDu: ")

        if user_input.lower() in ["exit", "quit", "q"]:
            break

        # Validate the user input for potential prompt injection attempts
        # before passing it to the chatbot workflow.
        prompt: str = user_input
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

        indications = [not evaluation_result["allowed"] for evaluation_result in complete_evaluation]

        if len([indication for indication in indications if indication]) > 0:
            print(
                "Bot: Diese Anfrage wurde aus Sicherheitsgründen blockiert. "
                "Bitte formuliere eine normale Anfrage zu einem ZIM-Thema."
            )
            print(f"   [SECURITY DEBUG] {complete_evaluation}")
            continue

        current_state["messages"].append(HumanMessage(content=user_input))
        current_state = graph.invoke(current_state)

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