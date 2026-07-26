"""Email Webhook Channel für Mailpit/Zammad Integration."""
from fastapi import APIRouter, Request, HTTPException
from langchain_core.messages import HumanMessage

# Importe analog zu ZIM.py
from ..graph.orchestrator import __execute_langchain_workflow
from ..graph.state import ChatbotState
from ..services.BackendLoggingService import BackendLogger

# Logger initialisieren, spezifisch für den Email-Channel
email_logger = BackendLogger("EmailChannel")

# APIRouter instanziieren
router = APIRouter()


@router.post("/api/webhook/email")
async def handle_email_webhook(request: Request):
    """
    Empfängt den Webhook von Mailpit, parst die E-Mail und leitet
    sie an den LangGraph-Workflow weiter.
    """
    try:
        # Mailpit sendet die Daten als JSON
        payload = await request.json()

        # 1. Daten aus dem Mailpit-Payload extrahieren
        # Mailpit verschachtelt die Absender-Infos unter 'From' -> 'Address' und 'Name'
        sender_email = payload.get("From", {}).get("Address", "")
        display_name = payload.get("From", {}).get("Name", "")
        subject = payload.get("Subject", "")
        text_body = payload.get("Text", "")  # Der reine Text der E-Mail (ohne HTML)

        # ---------------------------------------------------------
        # NEUER FILTER: System-Mails (Auto-Replies) ignorieren
        # ---------------------------------------------------------
        if sender_email.lower() == "support@localhost":
            email_logger.info("Auto-Reply von Zammad (support@localhost) erkannt. Ignoriere E-Mail.")
            return {"status": "ignored", "message": "System email ignored"}
        # ---------------------------------------------------------

        email_logger.info(f"Neue E-Mail empfangen von: {sender_email} | Betreff: {subject}")

        # 2. Den Input für den LLM-Graphen formatieren
        # Wir kombinieren Betreff und Body, damit das LLM den vollen Kontext hat
        combined_message = f"Betreff: {subject}\n\n{text_body}"

        # 3. Den ChatbotState aufbauen
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

        # 4. Den LangGraph-Workflow anstoßen
        email_logger.debug("Starte LangGraph Workflow für E-Mail-Kanal...")
        result_state = __execute_langchain_workflow(current_state)
        email_logger.info("LangGraph Workflow für E-Mail erfolgreich abgeschlossen.")

        # 5. HTTP 200 OK an Mailpit zurückgeben
        return {"status": "success", "message": "Email received and processed"}

    except Exception as e:
        email_logger.error(f"Fehler bei der E-Mail-Verarbeitung: {e}")
        # Wenn wir keinen 2xx Statuscode zurückgeben, versucht Mailpit
        # (je nach Config) die E-Mail eventuell später erneut zuzustellen.
        raise HTTPException(status_code=500, detail="Internal Server Error")