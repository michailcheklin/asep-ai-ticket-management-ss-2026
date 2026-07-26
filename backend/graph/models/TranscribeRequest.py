from pydantic import BaseModel


class TranscribeRequest(BaseModel):
    """
    Data model representing a speech-to-text request payload sent by the frontend.
    """
    audio_base64: str
    language: str | None = None
