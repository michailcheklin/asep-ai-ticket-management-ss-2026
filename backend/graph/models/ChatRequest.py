from typing import Dict, List

from pydantic import BaseModel


class ChatRequest(BaseModel):
    """
    Data model representing the request payload sent by the frontend.
    """
    user_message: str
    history: List[Dict[str, str]]
    user_email: str = ""
    student_id: str = ""
    issue_description: str = ""
    additional_info: List[str] = []
    priority: int = 0
    category: str = ""
    helpful: bool = False
    solutions: List[Dict] = []
    bot_message: str = ""
    additional_info_attempts: int = 0
    ask_issue_attempts: int = 0
    ticket_id: int | None = None
    summary: str = ""
    user_addendum: str = ""
    intent: str = ""
    tutorial_attempts: int = 0
    graph_runs: int = 0
    display_name: str = ""
    role: str = ""
    faculty: str = ""
    device: str = ""
    os_name: str = ""
    language: str = ""