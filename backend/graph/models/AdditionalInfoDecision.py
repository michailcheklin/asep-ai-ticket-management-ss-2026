from pydantic import BaseModel, Field, model_validator
from typing import Optional, List


class AdditionalInfoDecision(BaseModel):
    """Schema decision, if additional info is needed for effective problem treatment"""
    needs_additional_info: bool = Field(
        default=False,
        description="True, wenn die Zusatzinfos ausreichen, um das Problem zu bearbeiten. False, wenn wichtige Details fehlen (z.B. bei 'WLAN kaputt' fehlt das Gebäude)."
    )
    follow_up_question: Optional[str] = Field(
        default=None,
        description="Wenn needs_additional_info False ist: Eine kurze, höfliche Frage an den User, um die fehlenden Details herauszufinden. Wenn needs_additional_info True ist, lasse dieses Feld leer (null)."
    )
    follow_up_questions: Optional[List[str]] = Field(
        default=None,
        description="Fallback: Manche Modelle geben mehrere Fragen als Liste zurück. Der erste Eintrag wird als follow_up_question verwendet."
    )

    @model_validator(mode='after')
    def merge_questions(self):
        if not self.follow_up_question and self.follow_up_questions:
            self.follow_up_question = self.follow_up_questions[0]
        return self