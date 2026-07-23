import os
from pathlib import Path

from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from ..graph.models.ExtractedTicketData import ExtractedTicketData
from ..graph.models.TicketCategoryDecision import TicketCategoryDecision

USE_SAIA = os.getenv("USE_SAIA_API", "false").lower() == "true"
# temperature 0.2 for less hallucination
# Toggles between the SAIA API model (70B) and local Ollama (3B).
# Defaults to 'false' to avoid useing up the monthly SAIA limit (3000 requests)
# during standard code development and pipeline testing
if USE_SAIA:
    raw_key = os.getenv("SAIA_API_KEY", "")
    # LangChain requires API keys to be wrapped in a Pydantic 'SecretStr' type
    # This prevents the key from being exposed in plain text within logs
    # if the application crashes or the 'llm' object is accidentally printed to the terminal
    secure_saia_api_key = SecretStr(raw_key) if raw_key else None
    llm = ChatOpenAI(
        model="openai-gpt-oss-120b",
        api_key=secure_saia_api_key,
        base_url="https://chat-ai.academiccloud.de/v1",
        temperature=0.2,
        timeout=120,
        max_retries=1,
    )
else:
    ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    llm = ChatOllama(
        model="qwen3:8b",
        temperature=0.2,
        base_url=ollama_url
    )

structured_llm = llm.with_structured_output(ExtractedTicketData)
category_llm = llm.with_structured_output(TicketCategoryDecision)

AGENT = os.getenv("AGENT", "")
if not AGENT:
    raise Exception("AGENT not set. Aborting...")

_agent_path = Path(__file__).parent / "AGENTS" / f"{AGENT}.md"
if not _agent_path.exists():
    raise FileNotFoundError(f"Agent-Datei nicht gefunden: {_agent_path}")

AGENT_PROMPT = _agent_path.read_text(encoding="utf-8").strip()


