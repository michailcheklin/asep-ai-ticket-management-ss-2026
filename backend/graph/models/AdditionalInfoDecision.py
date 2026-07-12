from pydantic import BaseModel, Field, model_validator
from typing import Optional, List


class AdditionalInfoDecision(BaseModel):
    """Schema decision, if additional info is needed for effective problem treatment"""
    needs_additional_info: bool = Field(
        default=False,
        description=(
            "True, wenn vor einer Lösung noch zusätzliche Informationen vom Nutzer "
            "benötigt werden. Dies ist insbesondere der Fall, wenn mehrere "
            "unterschiedliche Einträge aus der Wissensdatenbank plausibel sind und "
            "deren Lösungen voneinander abweichen. Die Rückfrage soll genau die "
            "Information ermitteln, die zwischen diesen Einträgen unterscheidet. "
            "False nur dann, wenn mit den vorhandenen Informationen eine passende "
            "Lösung ausgewählt werden kann."
        )
    )
    follow_up_question: Optional[str] = Field(
        description=(
            "Wenn needs_additional_info True ist: Eine oder mehrere kurze, höfliche Fragen an den User, "
            "formatiert als Bullet-Liste. Multiple-Choice-Fragen müssen als Zeilen wie "
            " '* [Frage]? (options: [A], [B], [C])' "
            "geliefert werden. Offene Fragen haben keine `options:`-Klammer. Wenn needs_additional_info False ist, "
            "lasse dieses Feld leer (null)."
        )
    )
