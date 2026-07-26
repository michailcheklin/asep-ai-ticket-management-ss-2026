"""
Tests backend/llm/stt.py's transcribe_audio() without downloading a real
faster-whisper model: WhisperModel is mocked out before the module is
(re)imported, mirroring the ChatOllama-mocking approach in
backend/tests/test_llm_fallback.py.

Run from the repo root:
    PYTHONPATH=. pytest backend/tests/test_stt.py -v
"""
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# faster_whisper.WhisperModel downloads model weights on construction, so it
# must be mocked out *before* backend.llm.stt is ever imported - otherwise
# the module-level `model = WhisperModel(...)` in stt.py would trigger a
# real download the first time this test file is collected. (backend.api.ZIM
# is deliberately not imported here: it transitively loads the full RAG
# stack - real embedding models and DB connections - which is the domain of
# the CI-only/manual live tests, not a fast local unit test.)
patch("faster_whisper.WhisperModel", MagicMock()).start()

import backend.llm.stt as stt_module


class TranscribeAudioTests(unittest.TestCase):
    def test_joins_segments_into_one_stripped_string(self):
        segments = [SimpleNamespace(text=" Hallo "), SimpleNamespace(text="Welt. ")]
        stt_module.model.transcribe = MagicMock(return_value=(segments, None))

        result = stt_module.transcribe_audio(b"fake-wav-bytes", language="de")

        self.assertEqual(result, "Hallo Welt.")

    def test_passes_language_hint_through(self):
        stt_module.model.transcribe = MagicMock(return_value=([], None))

        stt_module.transcribe_audio(b"fake-wav-bytes", language="en")

        self.assertEqual(stt_module.model.transcribe.call_args.kwargs.get("language"), "en")

    def test_empty_language_hint_becomes_none(self):
        stt_module.model.transcribe = MagicMock(return_value=([], None))

        stt_module.transcribe_audio(b"fake-wav-bytes", language="")

        self.assertIsNone(stt_module.model.transcribe.call_args.kwargs.get("language"))


if __name__ == "__main__":
    unittest.main()
