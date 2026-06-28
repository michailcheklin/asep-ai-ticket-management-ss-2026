from pydantic import BaseModel, Field

TICKET_CATEGORIES = [
    "Zugang/Login",
    "Technisches Problem",
    "Allgemeine Anfrage",
    "Beschwerde",
    "Rechnung",
]


class TicketCategoryDecision(BaseModel):
    """Schema for the LLM output of the dedicated ticket category classification step."""
    category: str = Field(
        description=f"Exactly one of: {', '.join(TICKET_CATEGORIES)}"
    )
