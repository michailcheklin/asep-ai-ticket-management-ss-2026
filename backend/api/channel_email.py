"""Email Webhook Channel für Mailpit/Zammad Integration."""
from fastapi import APIRouter, Request, HTTPException
from langchain_core.messages import HumanMessage

from ..graph.orchestrator import __execute_langchain_workflow
from ..graph.state import ChatbotState
from ..services.BackendLoggingService import BackendLogger

# Initialize the logger specifically for the email channel
email_logger = BackendLogger("EmailChannel")

router = APIRouter()


@router.post("/api/webhook/email")
async def handle_email_webhook(request: Request):
    """
    Receives the webhook from Mailpit, parses the email, and forwards
    it to the LangGraph workflow
    """
    try:
        payload = await request.json()

        sender_email = payload.get("From", {}).get("Address", "")
        display_name = payload.get("From", {}).get("Name", "")
        subject = payload.get("Subject", "")
        text_body = payload.get("Text", "")

        # Ignores all emails coming from support@localhost
        if sender_email.lower() == "support@localhost":
            email_logger.info("Auto-Reply von Zammad (support@localhost) erkannt. Ignoriere E-Mail.")
            return {"status": "ignored", "message": "System email ignored"}

        email_logger.info(f"New email received from: {sender_email} | Subject: {subject}")

        combined_message = f"Subject: {subject}\n\n{text_body}"

        current_state: ChatbotState = {
            "messages": [HumanMessage(content=combined_message)],
            "visited_nodes": [],
            "user_email": sender_email,
            "student_id": "",
            "issue_description": "",
            "additional_info": [],
            "needs_additional_info": False,
            "priority": 0,
            "category": "",
            "is_complete": False,
            "solutions": [],
            "additional_info_attempts": 0,
            "ask_issue_attempts": 0,
            "ticket_id": None,
            "summary": "",
            "user_summary": "",
            "intent": "",
            "tutorial_attempts": 0,
            "display_name": display_name,
            "role": "",
            "faculty": "",
            "device": "",
            "os_name": "",
            "language": "",
            "graph_runs": 0,
            "channel": "email"
        }


        email_logger.debug("Start the LangGraph workflow for the email channel...")
        result_state = __execute_langchain_workflow(current_state)
        email_logger.info("LangGraph workflow for email successfully completed.")

        return {"status": "success", "message": "Email received and processed"}

    except Exception as e:
        email_logger.error(f"Error during email processing: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")