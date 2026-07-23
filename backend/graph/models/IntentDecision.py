from pydantic import BaseModel, Field


class IntentDecision(BaseModel):
    """Schema for classifying the user's intent (Issue #161)."""
    intent: str = Field(
        # LLM instruction — kept in German to match product dialogue language
        description='Genau eines von: "tutorial", "problem", "unclear","solved"'
    )
    reason: str = Field(
        default="",
        description="Short justification for the decision (debugging/tracing only)"
    )
