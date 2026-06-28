from pydantic import BaseModel, Field, model_validator
from typing import Optional, List


class AdditionalInfoDecision(BaseModel):
    """Schema decision, if additional info is needed for effective problem treatment"""
    needs_additional_info: bool = Field(
        default=False,
        description="True, wenn die Zusatzinfos ausreichen, um das Problem zu bearbeiten. False, wenn wichtige Details fehlen (z.B. bei 'WLAN kaputt' fehlt das Gebäude)."
    )
    follow_up_question: Optional[str] = Field(
        description=(
            "Wenn needs_additional_info False ist: Eine oder mehrere kurze, höfliche Fragen an den User, "
            "formatiert als Bullet-Liste. Multiple-Choice-Fragen müssen als Zeilen wie "
            " '* [Frage]? (options: [A], [B], [C])' "
            "geliefert werden. Offene Fragen haben keine `options:`-Klammer. Wenn needs_additional_info True ist, "
            "lasse dieses Feld leer (null)."
        )
    )
