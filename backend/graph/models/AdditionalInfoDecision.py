from pydantic import BaseModel, Field
from typing import Optional


class AdditionalInfoDecision(BaseModel):
    """Schema decision, if additional info is needed for effective problem treatment"""
    needs_additional_info: bool = Field(
        description="True, wenn die Zusatzinfos ausreichen, um das Problem zu bearbeiten. False, wenn wichtige Details fehlen (z.B. bei 'WLAN kaputt' fehlt das Gebäude)."
    )
    follow_up_question: Optional[str] = Field(
        description="Wenn needs_additional_info False ist: Eine kurze, höfliche Frage an den User, um die fehlenden Details herauszufinden. Wenn needs_additional_info True ist, lasse dieses Feld leer (null)."
    )