from pydantic import BaseModel, Field


class IntentDecision(BaseModel):
    """Schema fuer die Intent-Klassifikation des Nutzeranliegens (Issue #161)."""
    intent: str = Field(
        description='Genau eines von: "tutorial", "problem", "unclear","solved"'
    )
    reason: str = Field(
        default="",
        description="Kurze Begruendung der Entscheidung (nur fuer Debugging/Tracing)"
    )