from pydantic import BaseModel, Field, model_validator
from typing import Optional, List


class AdditionalInfoDecision(BaseModel):
    """Schema decision, if additional info is needed for effective problem treatment"""
    needs_additional_info: bool = Field(
        default=False,
        description=(
            "False, wenn das Problem mit den vorhandenen Informationen noch nicht "
            "eindeutig bearbeitet werden kann und zuerst weitere Informationen vom "
            "Nutzer benötigt werden. Dies gilt insbesondere dann, wenn mehrere "
            "unterschiedliche Ursachen oder mehrere stark voneinander abweichende "
            "Lösungswege plausibel sind und anhand der bisherigen Angaben nicht "
            "entschieden werden kann, welcher zutrifft. "
            "True nur dann, wenn die vorhandenen Informationen ausreichen, um "
            "eine konkrete und passende Lösung mit hoher Sicherheit vorzuschlagen."
        )
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
