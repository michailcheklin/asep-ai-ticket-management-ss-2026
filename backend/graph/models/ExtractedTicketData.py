from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class ExtractedTicketData(BaseModel):
    """
    Schema defining the structured ticket data to be extracted from user messages
    """
    language: Optional[Literal["de", "en"]] = Field(
        None,
        description="Die Sprache der aktuellsten Nutzernachricht: 'de' oder 'en'. "
                    "Nur setzen, wenn die Sprache eindeutig erkennbar ist (mehrere Woerter Fliesstext). "
                    "Bei einzelnen Zahlen, Matrikelnummern, Emojis oder unklarem Text: null lassen."
    )
    student_id: Optional[str] = Field(None,
                                          description="Die 7-stellige Matrikelnummer des Studenten, falls genannt.")
    problem: Optional[str] = Field(None,
                                   description="Das vom Nutzer explizit beschriebene IT-Problem oder die Supportanfrage. "
                                                "Nur setzen, wenn tatsächlich ein konkretes Problem genannt wird. "
                                                "Bei Begrüßungen, einzelnen Buchstaben, Testnachrichten, Smalltalk, "
                                                "Dankesnachrichten oder unverständlichem Text muss der Wert null sein. "
                                                "Niemals ein Problem erfinden oder aus Vermutungen ableiten."
                                   )
    additional_info: Optional[List[str]] = Field(default_factory=list,
                                                 description="Eine Liste von spezifischen Zusatzinformationen, die für den IT-Support an einer Universität relevant sind (z.B. Gebäude, Raumnummer, Fehlermeldung, Gerätetyp, OS). Keine Füllwörter."
                                                 )
    priority: Optional[int] = Field(
        None,
        description=(
            "Priority of the ticket. Use 1 for urgent or important issues, "
            "for example locked account, no login possible, exam or deadline affected, "
            "complete outage. Use 0 for normal or non-urgent issues."
        )
    )
    summary: Optional[str] = Field(None,
                                              description="Eine kurze Zusammenfassung des Problems basierend auf dem gesamten Chatverlauf. Diese Zusammenfassung sollte den Kontext und die wichtigsten Punkte des Problems in bis zu 3 Sätze erfassen.")
    user_summary: Optional[str] = Field(
        None,
        description="Inhaltlich identisch zu 'summary', aber geschrieben in der im "
                    "BENUTZER-KONTEXT angegebenen Antwortsprache statt zwingend auf Deutsch. "
                    "Wird dem Nutzer selbst angezeigt (Ticket-Bestaetigung), nicht dem Support-Team."
    )