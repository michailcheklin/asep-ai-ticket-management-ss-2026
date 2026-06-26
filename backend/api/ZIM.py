"""Backend API for the AI ticket management system with optional Zammad integration."""
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from ..graph.models.ChatRequest import ChatRequest
from langchain_core.messages import HumanMessage, AIMessage
from ..graph.state import ChatbotState
from ..graph.orchestrator import __execute_langchain_workflow, graph
from ..graph.nodes import _resolve_ticket_category
from ..services.TicketService import TicketService

ticket_service = TicketService()

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
ZAMMAD_TOKEN = os.getenv("ZAMMAD_API_TOKEN", "").strip()



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
    langchain_messages = []
    for msg in request.history:
        if msg["role"] == "user":
            langchain_messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "bot":
            langchain_messages.append(AIMessage(content=msg["content"]))

    langchain_messages.append(HumanMessage(content=request.user_message))

    current_state : ChatbotState = {
        "messages": langchain_messages,
        "user_email": request.user_email,
        "matrikelnummer": request.matrikelnummer,
        "issue_description": request.issue_description,
        "additional_info": request.additional_info,
        "needs_additional_info": False,
        "priority": request.priority,
        "category": request.category,
        "is_complete": False,
        "solutions": request.solutions,
        "additional_info_attempts": request.additional_info_attempts,
        "ask_issue_attempts": request.ask_issue_attempts
    }
    return __execute_langchain_workflow(current_state)

@app.post("/solution-feedback")
async def solution_feedback(request: ChatRequest):
    """
    Process the user's feedback on the suggested solutions.

    If the solution was helpful, close and tag the ticket as AI solved.
    Otherwise, create a support ticket and return a confirmation.

    :param request: Feedback request
    :return: Backend response
    """
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
        "category": request.category,
        "is_complete": False,
        "solutions": request.solutions,
        "ask_issue_attempts": request.ask_issue_attempts,
        "additional_info_attempts": request.additional_info_attempts
    }

    if request.helpful:
        updated_state = ticket_service.create_ai_solved_ticket(current_state)
    else:
        current_state["category"] = _resolve_ticket_category(current_state)
        updated_state = ticket_service.create_support_ticket(current_state)

    return {
        "bot_response": updated_state["messages"][-1].content,
        "category": current_state.get("category", ""),
    }

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