import json
from pathlib import Path

from pydantic import BaseModel, Field

_CATEGORIES_PATH = (
    Path(__file__).resolve().parents[3]
    / "zammad"
    / "bootstrap"
    / "ticket_categories.json"
)

with _CATEGORIES_PATH.open(encoding="utf-8") as categories_file:
    TICKET_CATEGORIES: list[str] = json.load(categories_file)


class TicketCategoryDecision(BaseModel):
    """Schema for the LLM output of the dedicated ticket category classification step."""
    category: str = Field(
        description=f"Exactly one of: {', '.join(TICKET_CATEGORIES)}"
    )
