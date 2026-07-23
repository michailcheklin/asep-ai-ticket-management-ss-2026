"""
Tests that the LLM fallback chain in backend/llm/llm.py actually falls
through to the next model when the primary SAIA model fails.

Two things are checked:

1. The real chain built in llm.py is wired in the right order (primary ->
   secondary SAIA -> local Ollama) and configured to catch every exception
   (not some narrower subset that would miss real-world failures).
2. LangChain's `.with_fallbacks()` mechanism - the exact mechanism used to
   build that chain - actually falls through for every realistic kind of
   failure a SAIA call can raise:
     * connection error    (SAIA host unreachable                 -> Case 2)
     * timeout              (SAIA slow/unresponsive                 -> Case 2)
     * model retired (404)  ("model not found"                     -> Case 1)
     * model retired (400)  ("model has been deprecated"           -> Case 1)
     * rate limit (429)     (e.g. monthly SAIA quota hit)
     * authentication (401) (bad/expired SAIA_API_KEY)
     * server error (500)   (SAIA-side failure)

The local Ollama model (glm-4.7) is never actually constructed against a
real Ollama server: `langchain_ollama.ChatOllama` is mocked out before
llm.py is (re)loaded, so this test needs neither a running Ollama instance
nor the glm-4.7 image pulled.

(Chat model instances are pydantic models whose bound methods can't be
safely monkeypatched with unittest.mock.patch.object - it fails on
teardown - so failure-mode coverage uses plain RunnableLambda stand-ins
wired the identical way `with_fallbacks` is used in llm.py, while a
separate test asserts the real chain's wiring/config directly.)

Run from the repo root:
    AGENT=ZIM PYTHONPATH=. pytest backend/tests/test_llm_fallback.py -v
"""
import importlib
import os
import unittest
from unittest.mock import MagicMock, patch

import httpx
import openai
from langchain_core.runnables import RunnableLambda

import backend.llm.llm as llm_module

_ORIGINAL_ENV = {}
_chat_ollama_patcher = None

def _never_invoke(_input):
    raise AssertionError("the local Ollama model must never be invoked by this test suite")


# Stand-in for the local Ollama model: a plain Runnable (not a real
# ChatOllama), so no Ollama server/image is needed to build or test the
# chain. Raises if ever actually invoked - none of the tests below should
# call into it for real. llm.py also calls .with_structured_output(schema)
# on it (for structured_llm/category_llm), so that needs stubbing too.
_local_llm_stub = RunnableLambda(_never_invoke)
_local_llm_stub.with_structured_output = lambda schema: RunnableLambda(_never_invoke)
fake_chat_ollama = MagicMock(return_value=_local_llm_stub)


def setUpModule():
    global _chat_ollama_patcher
    # llm.py reads USE_SAIA_API/SAIA_API_KEY at import time, so force a
    # reload in SAIA mode regardless of what earlier-imported test modules
    # left it configured as.
    for key, value in (("AGENT", "ZIM"), ("USE_SAIA_API", "true"), ("SAIA_API_KEY", "dummy-test-key")):
        _ORIGINAL_ENV[key] = os.environ.get(key)
        os.environ[key] = value
    # Patch the source ChatOllama so llm.py's `from langchain_ollama import
    # ChatOllama` picks up the mock on reload.
    _chat_ollama_patcher = patch("langchain_ollama.ChatOllama", fake_chat_ollama)
    _chat_ollama_patcher.start()
    importlib.reload(llm_module)


def tearDownModule():
    _chat_ollama_patcher.stop()
    for key, value in _ORIGINAL_ENV.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    importlib.reload(llm_module)


def _connection_error():
    return openai.APIConnectionError(
        request=httpx.Request("POST", "https://chat-ai.academiccloud.de/v1")
    )


def _timeout_error():
    return openai.APITimeoutError(
        request=httpx.Request("POST", "https://chat-ai.academiccloud.de/v1")
    )


def _status_error(cls, status_code: int, message: str):
    request = httpx.Request("POST", "https://chat-ai.academiccloud.de/v1")
    response = httpx.Response(status_code, request=request)
    return cls(message, response=response, body=None)


FAILURE_MODES = {
    "connection_error": _connection_error,
    "timeout": _timeout_error,
    "model_retired_404": lambda: _status_error(openai.NotFoundError, 404, "model not found"),
    "model_retired_400": lambda: _status_error(openai.BadRequestError, 400, "model has been deprecated"),
    "rate_limit_429": lambda: _status_error(openai.RateLimitError, 429, "quota exceeded"),
    "auth_error_401": lambda: _status_error(openai.AuthenticationError, 401, "invalid api key"),
    "server_error_500": lambda: _status_error(openai.InternalServerError, 500, "internal server error"),
}


class RealChainWiringTests(unittest.TestCase):
    """USE_SAIA_API=true must build primary -> secondary -> local, catching all exceptions."""

    def test_chain_order_is_primary_then_secondary_then_local(self):
        self.assertIsNot(llm_module.llm, llm_module._primary_llm)
        self.assertIs(llm_module.llm.runnable, llm_module._primary_llm)
        self.assertEqual(
            list(llm_module.llm.fallbacks),
            [llm_module._secondary_llm, llm_module.local_llm],
        )
        # local_llm must be the mocked-out ChatOllama stand-in, not a real client.
        self.assertIs(llm_module.local_llm, _local_llm_stub)

    def test_models_are_the_expected_ones(self):
        self.assertEqual(llm_module._primary_llm.model_name, "openai-gpt-oss-120b")
        self.assertEqual(llm_module._secondary_llm.model_name, "glm-4.7")
        # llm.py must request "glm-4.7" from Ollama - checked via the mocked
        # constructor's call args, without needing a real Ollama/the image.
        fake_chat_ollama.assert_called_once()
        self.assertEqual(fake_chat_ollama.call_args.kwargs.get("model"), "glm-4.7")

    def test_fallback_catches_every_exception_type(self):
        # A narrowed exceptions_to_handle would silently stop catching some
        # of the real SAIA failure modes exercised below.
        self.assertEqual(llm_module.llm.exceptions_to_handle, (Exception,))


class FallbackMechanismFailureModeTests(unittest.TestCase):
    """Confirms with_fallbacks() - the mechanism llm.py's chain relies on -
    falls through to the next model for every realistic failure kind."""

    def test_falls_back_to_secondary_for_every_primary_failure_mode(self):
        for name, make_error in FAILURE_MODES.items():
            with self.subTest(failure_mode=name):
                def primary(_input, _make_error=make_error):
                    raise _make_error()

                calls = []

                def secondary(_input):
                    calls.append("secondary")
                    return "secondary-response"

                def local(_input):
                    calls.append("local")
                    return "local-response"

                chain = RunnableLambda(primary).with_fallbacks([
                    RunnableLambda(secondary),
                    RunnableLambda(local),
                ])

                result = chain.invoke("hi")

                self.assertEqual(result, "secondary-response")
                self.assertEqual(calls, ["secondary"])

    def test_falls_back_all_the_way_to_local_when_both_saia_tiers_fail(self):
        def primary(_input):
            raise _connection_error()

        def secondary(_input):
            raise _timeout_error()

        def local(_input):
            return "local-response"

        chain = RunnableLambda(primary).with_fallbacks([
            RunnableLambda(secondary),
            RunnableLambda(local),
        ])

        self.assertEqual(chain.invoke("hi"), "local-response")

    def test_no_fallback_needed_when_primary_succeeds(self):
        def primary(_input):
            return "primary-response"

        def secondary(_input):
            raise AssertionError("secondary should not be called")

        chain = RunnableLambda(primary).with_fallbacks([RunnableLambda(secondary)])

        self.assertEqual(chain.invoke("hi"), "primary-response")

    def test_all_tiers_failing_raises(self):
        def always_fails(_input):
            raise _connection_error()

        chain = RunnableLambda(always_fails).with_fallbacks([
            RunnableLambda(always_fails),
            RunnableLambda(always_fails),
        ])

        with self.assertRaises(openai.APIConnectionError):
            chain.invoke("hi")


if __name__ == "__main__":
    unittest.main()
