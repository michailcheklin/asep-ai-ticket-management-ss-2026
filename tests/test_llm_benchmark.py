import json
import asyncio
from unittest.mock import patch
from langchain_openai import ChatOpenAI
from pydantic import SecretStr
from deepeval.evaluate import evaluate
from deepeval.metrics import ConversationCompletenessMetric
from deepeval.test_case import ConversationalTestCase, Turn
from backend.main import chat_endpoint, ChatRequest
from backend.nodes import ExtractedTicketData
from tests.setup import SAIA_MODEL, SAIA_API_KEY, SAIA_BASE_URL
from langsmith import Client as LangSmithClient
from dotenv import load_dotenv

load_dotenv()

# Feste Gesprächsszenarien – deterministisch, kein Simulator nötig
SCENARIOS = [
    [
        "Ich bin in der Bibliothek mit einem Windows 10 Laptop, das Uni-WLAN wird nicht in der Netzwerkliste angezeigt",
    ],
    [
        "Mein Uni-Account ist gesperrt, ich kann mich weder im Portal noch per Mail einloggen",
    ],
]


MODEL_CONFIGS = {
    "deepseek-r1-70b":  "deepseek-r1-distill-llama-70b",
    #"apertus-70b":      "apertus-70b-instruct-2509",
    "gemma-4-31b":   "gemma-4-31b-it",  
    "llama-3.1-8b": "meta-llama-3.1-8b-instruct",
}



def run_benchmark_for_model(model_name: str, model_id: str):
    print(f"\n{'='*60}")
    print(f"Teste Modell: {model_name}")
    print(f"{'='*60}\n")

    new_llm = ChatOpenAI(
        model=model_id,
        api_key=SecretStr(SAIA_API_KEY),
        base_url=SAIA_BASE_URL.rstrip("/"),
        temperature=0.2
    )
    new_structured_llm = new_llm.with_structured_output(ExtractedTicketData, method="json_mode")

    async def build_test_case(messages):
        turns = []
        next_req = {
            "user_message": "", "history": [],
            "user_email": "a@example.com", "matrikelnummer": "1234567",
            "issue_description": "", "additional_info": [],
            "priority": 0, "helpful": False, "solutions": [],
            "bot_message": "", "additional_info_attempts": 0, "ask_issue_attempts": 0,
        }
        for msg in messages:
            turns.append(Turn(role="user", content=msg))
            next_req["user_message"] = msg
            response = await chat_endpoint(ChatRequest(**next_req))
            turns.append(Turn(role="assistant", content=response["bot_response"]))
            next_req.update({
                "issue_description": response.get("issue_description", ""),
                "additional_info": response.get("additional_info", []),
                "priority": response.get("priority", 0),
                "solutions": response.get("solutions", []),
                "additional_info_attempts": response.get("additional_info_attempts", 0),
                "ask_issue_attempts": response.get("ask_issue_attempts", 0),
            })
            if response.get("is_complete") or response.get("solutions"):
                break
        return ConversationalTestCase(turns=turns)

    with patch("backend.nodes.llm", new_llm), \
         patch("backend.nodes.structured_llm", new_structured_llm):


        async def run_all():
            return await asyncio.gather(*[build_test_case(msgs) for msgs in SCENARIOS])

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            test_cases = loop.run_until_complete(run_all())
        finally:
            loop.close()
            asyncio.set_event_loop(None)
        

        all_scenario_results = []
        for tc in test_cases:
            r = evaluate(
                test_cases=[tc],
                metrics=[ConversationCompletenessMetric(model=SAIA_MODEL, async_mode=False)],
            )
            all_scenario_results.append(r)

        return all_scenario_results


def test_benchmark_all_models():
    all_results = {}

    for model_name, model_id in MODEL_CONFIGS.items():
        try:
            results = run_benchmark_for_model(model_name, model_id)
            all_results[model_name] = str(results)
        except Exception as e:
            print(f"\n⚠ {model_name} konnte nicht evaluiert werden: {e}")
            all_results[model_name] = f"ERROR: {str(e)}"

    with open("tests/benchmark_results.json", "w") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)

    print("\n" + "="*60)
    print("BENCHMARK ABGESCHLOSSEN")
    print("Ergebnisse gespeichert in tests/benchmark_results.json")
    print("="*60)


    # LangSmith: Ergebnisse loggen
    try:
        ls_client = LangSmithClient()
        for model_name, result_data in all_results.items():
            ls_client.create_run(
                name=f"benchmark-{model_name}",
                run_type="chain",
                inputs={"model": model_name, "scenarios": len(SCENARIOS)},
                outputs={"result": str(result_data)},
                project_name="ai-ticket-benchmark",
            )
        print("\n✅ Ergebnisse in LangSmith geloggt.")
    except Exception as e:
        print(f"\n⚠ LangSmith-Logging fehlgeschlagen: {e}")