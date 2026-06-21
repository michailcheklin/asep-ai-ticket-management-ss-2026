"""Backend API for the AI ticket management system with optional Zammad integration."""
import concurrent.futures
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import HumanMessage, AIMessage
from backend.state import ChatbotState
from backend.nodes import (
    extract_information,
    ask_for_email,
    ask_for_matrikelnummer,
    ask_for_issue,
    ask_for_additional_info,
    give_solutions,
    finish_ticket
)
from pydantic import BaseModel
from typing import List, Dict
from backend.prompt_security_result import (
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
    Data model representing the request payload sent by the frontend.
    """
    user_message: str
    history: List[Dict[str, str]]  # Format: [{"role": "user", "content": "..."}, {"role": "bot", "content": "..."}]
    user_email: str = ""
    matrikelnummer: str = ""
    issue_description: str = ""
    additional_info: List[str] = []
    priority: int = 0
    helpful: bool = False
    solutions: List[Dict] = []
    bot_message: str = ""
    additional_info_attempts: int = 0
    ask_issue_attempts: int = 0



def __check_prompt (prompt:str) -> list[dict]:
    """
    Run all prompt safety checks in parallel.

    The user input is checked for prompt injection, illegal content
    and off-topic requests before being processed by the chatbot.

    :param prompt: User input to validate
    :return: List containing the results of all safety checks
    """
    # Execute all prompt safety checks concurrently.
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
    Generate a user-facing rejection message based on the failed
    prompt safety checks.

    :param failed_checks: List of failed safety checks
    :return: Rejection message shown to the user
    """

    # Keep the mapping centralized so only these return values
    # need to be changed if different user messages are required.
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
    Process a chat request.

    The request is forwarded to the LangGraph workflow after
    passing the prompt safety checks.

    :param request: Current conversation state
    :return: Updated conversation state
    """

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
            "needs_additional_info": False,
            "priority": request.priority,
            "is_complete": False
        }
    """

    return __execute_langchain_workflow(request)
  
@app.post("/solution-feedback")
async def solution_feedback(request: ChatRequest):
    """
    Process the user's feedback on the suggested solutions.

    If the solution was helpful, return a goodbye message.
    Otherwise, create a support ticket and return a confirmation.

    :param request: Feedback request
    :return: Backend response
    """
    if request.helpful:
        return {
            "bot_response": "Super. Freut mich, dass ich dir helfen konnte! Wenn du in Zukunft weitere Fragen hast, stehe ich gerne zur Verfügung. Hab einen schönen Tag!"
        }
    else:
        langchain_messages = []
        for msg in request.history:
            if msg["role"] == "user":
                langchain_messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "bot":
                langchain_messages.append(AIMessage(content=msg["content"]))

        langchain_messages.append(HumanMessage(content=request.user_message))

        current_state: ChatbotState = {
            "messages": langchain_messages,
            "user_email": request.user_email,
            "matrikelnummer": request.matrikelnummer,
            "issue_description": request.issue_description,
            "additional_info": request.additional_info,
            "needs_additional_info": False,
            "priority": request.priority,
            "is_complete": False,
            "solutions": request.solutions,
            "additional_info_attempts": request.additional_info_attempts,
            "ask_issue_attempts": request.ask_issue_attempts
        }

        updated_state = finish_ticket(current_state)
        bot_response = updated_state["messages"][-1].content

        try:
            return {"bot_response": bot_response}
        except Exception as e:
            print(f"Error extracting bot response: {e}")
            return {
                "bot_response": "Es tut mir leid, aber es gab ein Problem bei der Verarbeitung deines Feedbacks. Bitte versuche es erneut oder kontaktiere den Support direkt."
            }

def __execute_langchain_workflow(request: ChatRequest):
    """
    Execute the LangGraph workflow.

    Converts the frontend request into the internal chatbot state,
    executes the workflow and returns the updated conversation state.

    :param request: Frontend request
    :return: Updated conversation state
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
        "needs_additional_info": False,
        "priority": request.priority,
        "is_complete": False,
        "additional_info_attempts": request.additional_info_attempts,
        "ask_issue_attempts": request.ask_issue_attempts
    }

    updated_state = graph.invoke(current_state)
    bot_response = updated_state["messages"][-1].content
    return {
        "bot_response": bot_response,
        "user_email": updated_state.get("user_email", ""),
        "matrikelnummer": updated_state.get("matrikelnummer", ""),
        "issue_description": updated_state.get("issue_description", ""),
        "additional_info": updated_state.get("additional_info", []),
        "needs_additional_info": updated_state.get("needs_additional_info", False),
        "priority": updated_state.get("priority", 0),
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
        return "give_solutions_node"
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

def run_local_chat():
    """
    [TESTING ONLY]

    Run the chatbot locally in a terminal without starting
    the FastAPI server or the frontend.
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
        "needs_additional_info": False,
        # Set to True to skip the solution step and directly create
        # a ticket during testing.
        "is_complete": False,
    }

    print("Bot: Hallo! Willkommen beim IT-Support. Wie kann ich dir heute helfen?")

    while True:
        user_input = input("\nDu: ")

        if user_input.lower() in ["exit", "quit", "q"]:
            break

        # Prompt safety validation.
        # Currently disabled because the chatbot's built-in safety
        # mechanisms are used instead.

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

        # This never becomes True while solutions are available.
        # The workflow waits for explicit user feedback before
        # continuing with ticket creation.
        if current_state.get("is_complete"):
            print("\n🎉 [SYSTEM]: backend feuert API-Call an Zammad!")
            break


if __name__ == "__main__":
    run_local_chat() 