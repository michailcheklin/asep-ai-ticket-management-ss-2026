import os
from pathlib import Path

from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from ..graph.models.ExtractedTicketData import ExtractedTicketData
from ..graph.models.TicketCategoryDecision import TicketCategoryDecision

USE_SAIA = os.getenv("USE_SAIA_API", "false").lower() == "true"
# temperature 0.2 for less hallucination
# Toggles between the SAIA API models and local Ollama.
# Defaults to 'false' to avoid useing up the monthly SAIA limit (3000 requests)
# during standard code development and pipeline testing
ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
local_llm = ChatOllama(model="glm-4.7", temperature=0.2, base_url=ollama_url)

if USE_SAIA:
    raw_key = os.getenv("SAIA_API_KEY", "")
    # LangChain requires API keys to be wrapped in a Pydantic 'SecretStr' type
    # This prevents the key from being exposed in plain text within logs
    # if the application crashes or the 'llm' object is accidentally printed to the terminal
    secure_saia_api_key = SecretStr(raw_key) if raw_key else None

    def _saia_model(model_name: str) -> ChatOpenAI:
        return ChatOpenAI(
            model=model_name,
            api_key=secure_saia_api_key,
            base_url="https://chat-ai.academiccloud.de/v1",
            temperature=0.2,
            timeout=120,
            max_retries=1,
        )

    # Fallback chain: primary SAIA model -> secondary SAIA model (in case the
    # primary is retired/unsupported) -> local Ollama model (in case SAIA is
    # unreachable entirely). Both failure modes surface as an exception from
    # .invoke(), so a single fallback chain covers both cases.
    _primary_llm = _saia_model("openai-gpt-oss-120b")
    _secondary_llm = _saia_model("glm-4.7")
    llm = _primary_llm.with_fallbacks([_secondary_llm, local_llm])

    def with_structured_fallback(schema):
        """Structured-output runnable with the same SAIA -> SAIA -> local fallback chain.

        RunnableWithFallbacks (the result of .with_fallbacks()) has no
        .with_structured_output(), so structured output must be applied to
        each model before chaining fallbacks.
        """
        return _primary_llm.with_structured_output(schema).with_fallbacks([
            _secondary_llm.with_structured_output(schema),
            local_llm.with_structured_output(schema),
        ])
else:
    llm = local_llm

    def with_structured_fallback(schema):
        return local_llm.with_structured_output(schema)

structured_llm = with_structured_fallback(ExtractedTicketData)
category_llm = with_structured_fallback(TicketCategoryDecision)

AGENT = os.getenv("AGENT", "")
if not AGENT:
    raise Exception("AGENT not set. Aborting...")

_agent_path = Path(__file__).parent / "AGENTS" / f"{AGENT}.md"
if not _agent_path.exists():
    raise FileNotFoundError(f"Agent-Datei nicht gefunden: {_agent_path}")

AGENT_PROMPT = _agent_path.read_text(encoding="utf-8").strip()
