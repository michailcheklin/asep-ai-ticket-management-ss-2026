"""Backend API for the AI ticket management system with optional Zammad integration."""
import os
import re

import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.messages import AIMessage, HumanMessage
from . import channel_email

from ..api.zammad import get_ticket_tags, log_ticket_close_event
from ..graph.models.ChatRequest import ChatRequest
from ..graph.nodes import _resolve_ticket_category
from ..graph.orchestrator import __execute_langchain_workflow, graph
from ..graph.state import ChatbotState
from ..rag import recent_incidents
from ..rag.rag_store_tickets import store_ticket_state_to_rag
from ..services.BackendLoggingService import BackendLogger
from ..services.TicketService import TicketService

zim_logger = BackendLogger("ZIM")
ticket_service = TicketService()

# Create FastAPI application instance
app = FastAPI(title="AI Ticket API", version="1.0.0")

# Register the email webhook routes
app.include_router(channel_email.router)

# Enable CORS so frontend applications can access the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Read Zammad configuration from environment variables
ZAMMAD_URL = os.getenv("ZAMMAD_INTERNAL_URL", "").strip()
ZAMMAD_TOKEN = os.getenv("ZAMMAD_API_TOKEN", "").strip()

# Parsing helper variables
BOT_SUMMARY_MARKER  = "GESPRÄCHSZUSAMMENFASSUNG"
BOT_SOLUTIONS_MARKER = "VOM BOT ANGEBOTENE LÖSUNGEN"
BOT_HANDOFF_MARKER   = "Das Gespräch mit dem Chatbot wurde abgeschlossen"


def _zammad_headers() -> dict[str, str]:
    """Create authentication headers for Zammad API requests."""
    if not ZAMMAD_TOKEN:
        return {}
    return {"Authorization": f"Token token={ZAMMAD_TOKEN}"}


def _history_to_langchain_messages(history: list[dict]) -> list:
    """Convert frontend chat history to LangChain message objects."""
    messages = []
    for msg in history:
        role = msg.get("role")
        if role == "user":
            messages.append(HumanMessage(content=msg["content"]))
        elif role in ("bot", "assistant"):
            messages.append(AIMessage(content=msg["content"]))
    return messages


@app.get("/")
def root():
    """Root endpoint of the backend API."""
    return {
        "message": "AI Ticket Management Backend is running"
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

    zim_logger.info(f"Received request to the chat endpoint\n{request}")
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
            "student_id": request.student_id,
            "issue_description": request.issue_description,
            "needs_additional_info": False,
            "priority": request.priority,
            "is_complete": False
        }
    """
    langchain_messages = _history_to_langchain_messages(request.history)
    langchain_messages.append(HumanMessage(content=request.user_message))

    current_state : ChatbotState = {
        "messages": langchain_messages,
        "user_email": request.user_email,
        "student_id": request.student_id,
        "issue_description": request.issue_description,
        "additional_info": request.additional_info,
        "needs_additional_info": False,
        "priority": request.priority,
        "category": request.category,
        "is_complete": False,
        "solutions": request.solutions,
        "additional_info_attempts": request.additional_info_attempts,
        "ask_issue_attempts": request.ask_issue_attempts,
        "ticket_id": request.ticket_id,
        "summary": request.summary,
        "user_summary": request.user_summary,
        "intent": request.intent,
        "tutorial_attempts": request.tutorial_attempts,
        "display_name": request.display_name,
        "role": request.role,
        "faculty": request.faculty,
        "device": request.device,
        "os_name": request.os_name,
        "language": request.language,
        "graph_runs": request.graph_runs,
    }
    return __execute_langchain_workflow(current_state)

def get_zammad_ticket_articles(ticket_id: int) -> list[dict]:
    """Fetch all articles (messages) belonging to a ticket from Zammad."""
    url = f"{ZAMMAD_URL}/api/v1/ticket_articles/by_ticket/{ticket_id}"
    headers = {"Authorization": f"Token token={ZAMMAD_TOKEN}"}

    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()

def _strip_html(text: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&nbsp;", " ")
    text = re.sub(r"\n{2,}", "\n", text).strip()
    return text


def _extract_bot_summary(body: str) -> str | None:
    """Pull out only the free-text summary between the GESPRÄCHSZUSAMMENFASSUNG
    heading and the next heading (or end of article), stripping separators."""
    start = body.find(BOT_SUMMARY_MARKER)
    if start == -1:
        return None
    start += len(BOT_SUMMARY_MARKER)
    end = body.find(BOT_SOLUTIONS_MARKER, start)
    if end == -1:
        end = len(body)
    summary = body[start:end]
    summary = re.sub(r"=+", "", summary).strip()
    return summary or None

def build_ticket_summary_and_conversation(articles: list[dict]) -> str:
    """
    Build the final text to store for any ticket:

      1. If a bot handoff article exists, extract ONLY its free-text
         conversation summary and label it.
      2. Everything AFTER that handoff article (the real human agent
         conversation) is kept as-is, labeled with a clear start marker.

    Works generically:
      - If no bot handoff is found (ticket never used the AI chatbot, or was
        fully resolved by it with no human follow-up), the whole article
        list is treated as the conversation and no summary line is added.
    """
    handoff_index = None
    summary_text = None

    for i, article in enumerate(articles):
        if article.get("sender") != "Agent":
            continue
        body = _strip_html(article.get("body", ""))
        if BOT_HANDOFF_MARKER in body or BOT_SUMMARY_MARKER in body:
            summary_text = _extract_bot_summary(body)
            handoff_index = i
            break

    remaining = articles[handoff_index + 1:] if handoff_index is not None else articles

    conversation_lines = []
    for article in remaining:
        sender = article.get("sender", "")
        if sender not in ("Customer", "Agent"):
            continue  # skip System notifications
        body = _strip_html(article.get("body", ""))
        if body.lstrip("=\n ").startswith(BOT_SOLUTIONS_MARKER):
            continue  # skip standalone "bot-offered solutions" article
        role = "User" if sender == "Customer" else "Agent"
        if body:
            conversation_lines.append(f"{role}: {body}")

    parts = []
    if summary_text:
        parts.append(f"Gesprächszusammenfassung mit KI Chatbot:\n\n{summary_text}")
    if conversation_lines:
        parts.append("Weitere Konversation mit Support-Mitarbeiter:\n\n" + "\n".join(conversation_lines))

    full_text = "\n\n".join(parts)
    return summary_text or "", full_text, conversation_lines


# Tickets carrying any of these tags will not be used to train/improve the AI chatbot:
# - "AI-Solved": the bot already resolved this correctly, nothing new to learn.
# - "No-AI-Training": staff manually flagged this as a special/edge case that
#   should stay human handled and not influence the chatbot's future behavior.
EXCLUDE_FROM_TRAINING_TAGS = {"AI-Solved", "No-AI-Training"}

@app.post("/zammad/ticket-closed")
async def zammad_ticket_closed(payload: dict):
    """Webhook endpoint for Zammad close notifications."""
    ticket = payload.get("ticket", {}) if isinstance(payload.get("ticket"), dict) else {}
    ticket_id = ticket.get("id") or payload.get("id")

    tags = get_ticket_tags(ticket_id) if ticket_id else []
    matched_tags = EXCLUDE_FROM_TRAINING_TAGS.intersection(tags)
    if matched_tags:
        zim_logger.info(f"Ticket {ticket_id} excluded from AI training due to tag: {matched_tags}")
        return {
            "status": "ignored",
            "reason": f"excluded_from_training:{','.join(matched_tags)}",
            "ticket_id": ticket_id,
        }

    metadata = {
        "ticket_number": ticket.get("number") or payload.get("number"),
        "title": ticket.get("title") or payload.get("title"),
        "state": ticket.get("state", {}).get("name") if isinstance(ticket.get("state"), dict) else payload.get("state"),
    }

    articles = get_zammad_ticket_articles(ticket_id) if ticket_id else []
    ticket_summary, _, agent_messages = build_ticket_summary_and_conversation(articles)

    rag_state = {
        "summary": ticket_summary,
        "ticket_id": ticket_id,
        "messages": agent_messages,
    }
    if ticket_id:
        zim_logger.debug(f"Preparing RAG store for closed ticket {ticket_id}")
        zim_logger.info(f"Close webhook received for ticket {ticket_id}")
        store_ticket_state_to_rag(rag_state, ticket_id=ticket_id)

    log_ticket_close_event(ticket_id=ticket_id, source="manual", metadata=metadata)
    return {
        "status": "received",
        "source": "manual",
        "ticket_id": ticket_id,
    }

@app.post("/solution-feedback")
async def solution_feedback(request: ChatRequest):
    """
    Process the user's feedback on the suggested solutions.

    If the solution was helpful, close and tag the ticket as AI solved.
    Otherwise, create a support ticket and return a confirmation.

    :param request: Feedback request
    :return: Backend response
    """
    langchain_messages = _history_to_langchain_messages(request.history)
    langchain_messages.append(HumanMessage(content=request.user_message))

    current_state: ChatbotState = {
        "messages": langchain_messages,
        "user_email": request.user_email,
        "student_id": request.student_id,
        "issue_description": request.issue_description,
        "additional_info": request.additional_info,
        "needs_additional_info": False,
        "priority": request.priority,
        "category": request.category,
        "is_complete": False,
        "solutions": request.solutions,
        "ask_issue_attempts": request.ask_issue_attempts,
        "additional_info_attempts": request.additional_info_attempts,
        "ticket_id": request.ticket_id,
        "summary": request.summary,
        "user_summary": request.user_summary,
        "user_addendum": request.user_addendum,
        "intent": request.intent,
        "tutorial_attempts": request.tutorial_attempts,
        "display_name": request.display_name,
        "role": request.role,
        "faculty": request.faculty,
        "device": request.device,
        "os_name": request.os_name,
        "language": request.language,
        "graph_runs": request.graph_runs,
    }

    current_state["category"] = _resolve_ticket_category(current_state)
    first_name = current_state.get("display_name", "").split()[0] if current_state.get("display_name") else ""

    if request.helpful:
        ticket_service.create_ai_solved_ticket(current_state)
        greeting = f"Super, {first_name}, das freut mich!" if first_name else "Super, das freut mich!"
        return {
            "bot_response": f"{greeting} Bei weiteren Fragen stehe ich jederzeit zur Verfügung. Einen schönen Tag noch!",
            "category": current_state.get("category", "")
        }

    else:
        ticket_service.append_support_ticket_context(current_state, request.ticket_id)
        greeting = f"Danke, {first_name}!" if first_name else "Danke!"
        return {
            "bot_response": f"{greeting} Das Ticket wurde an den Support weitergeleitet.",
            "category": current_state.get("category", "")
        }




@app.post("/webhook/ticket-closed")
async def ticket_closed(payload: dict):
    """
    Called by a Zammad trigger/webhook when a ticket is closed.

    Removes the affected incident from the 'Recent Incidents' collection
    so that closed incidents no longer contribute to problem escalation.

    Expects a payload containing the ticket ID — either as
    {"ticket_id": <id>} or nested as {"ticket": {"id": <id>}}.
    """
    ticket_id = payload.get("ticket_id")
    if ticket_id is None and isinstance(payload.get("ticket"), dict):
        ticket_id = payload["ticket"].get("id")

    if ticket_id is None:
        return {"ok": False, "error": "no ticket id in payload"}

    try:
        recent_incidents.mark_incident_closed(int(ticket_id))
        return {"ok": True, "removed_ticket_id": int(ticket_id)}
    except Exception as e:
        zim_logger.error(f"Ticket close webhook failed for {ticket_id}: {e}")
        return {"ok": False, "error": str(e)}


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
        "student_id": "",
        "issue_description": "",
        "additional_info": [],
        "additional_info_attempts": 0,
        "ask_issue_attempts": 0,
        "priority": 0,
        "category": "",
        "solutions": [],
        "ticket_id": None,
        "summary": "",
        "intent": "",
        "tutorial_attempts": 0,
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
            f"Matrikel: {current_state.get('student_id')} | "
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