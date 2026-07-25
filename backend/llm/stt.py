import io

from faster_whisper import WhisperModel

from ..config import STT_COMPUTE_TYPE, STT_DEVICE, STT_MODEL_SIZE

model = WhisperModel(STT_MODEL_SIZE, device=STT_DEVICE, compute_type=STT_COMPUTE_TYPE)


def transcribe_audio(audio_bytes: bytes, language: str | None = None) -> str:
    """
    Transcribe recorded audio to text.
    :param audio_bytes: Raw audio file bytes (e.g. WAV from st.audio_input)
    :param language: Optional ISO language hint ("de"/"en") to skip auto-detection
    :return: The transcribed text
    """
    segments, _ = model.transcribe(io.BytesIO(audio_bytes), language=language or None)
    return " ".join(segment.text.strip() for segment in segments).strip()
