import json
import asyncio
from unittest.mock import patch

import openai
from langchain_core.outputs import ChatResult
from langchain_openai import ChatOpenAI
from pydantic import SecretStr
from deepeval.evaluate import evaluate
from deepeval.metrics import ConversationCompletenessMetric
from deepeval.test_case import ConversationalTestCase, Turn
from backend.api.ZIM import chat_endpoint
from backend.graph.models.ChatRequest import ChatRequest
from backend.graph.models.ExtractedTicketData import ExtractedTicketData
from tests.setup import SAIA_MODEL, SAIA_API_KEY, SAIA_BASE_URL
from langsmith import Client as LangSmithClient
from dotenv import load_dotenv

load_dotenv()

import re

class ThinkStripChatOpenAI(ChatOpenAI):
    """Wrapper für DeepSeek: entfernt <think>...</think> Tags vor dem JSON-Parsing."""
    
    def invoke(self, input, config=None, **kwargs):
        result = super().invoke(input, config=config, **kwargs)
        if hasattr(result, 'content') and isinstance(result.content, str):
            result.content = re.sub(
                r'<think>.*?</think>', '', result.content, flags=re.DOTALL
            ).strip()
        return result



class LlamaPatchForChatOpenAI(ChatOpenAI):
    def _create_chat_result(
        self,
        response: dict | openai.BaseModel,
        generation_info: dict | None = None,
    ) -> ChatResult:
        """
        Applying the fix suggested in https://github.com/langchain-ai/langchain/issues/26777#issuecomment-2639633410
        to handle format issues for Llama
        :param response:
        :param generation_info:
        :return:
        """
        for choice in response.choices:
            message = choice.message
            # Check if the message has a tool_calls attribute.
            if hasattr(message, "tool_calls") and message.tool_calls:
                for tool_call in message.tool_calls:
                    # Check if the tool_call has a function with arguments.
                    if hasattr(tool_call, "function") and hasattr(tool_call.function, "arguments"):
                        if not isinstance(tool_call.function.arguments, str):
                            tool_call.function.arguments = json.dumps(tool_call.function.arguments)

        return super()._create_chat_result(response, generation_info)


SCENARIOS = [
    # Szenario 1: WLAN 
    [
        "Ich bin in der Bibliothek mit einem Windows 10 Laptop, das Uni-WLAN wird nicht in der Netzwerkliste angezeigt",
        "Nein, ein physischer Schalter ist nicht vorhanden. Ich habe schon den Flugzeugmodus aus- und eingeschaltet.",
        "Ja, andere Geräte in der Bibliothek haben WLAN. Nur mein Laptop nicht.",
    ],
    # Szenario 2: Gesperrter Account 
    [
        "Mein Uni-Account ist gesperrt, ich kann mich weder im Portal noch per Mail einloggen",
        "Mein Benutzername ist s-mustermann, ich habe eine alternative Mail: mustermann@gmail.com",
        "Ich habe mein Passwort mehrmals falsch eingegeben, seitdem ist der Account gesperrt.",
    ],
    # Szenario 3: Passwort vergessen
    [
        "Ich habe mein Passwort vergessen und kann mich nicht mehr einloggen",
        "Ich bin Student im 3. Semester, meine Matrikelnummer ist 1234567",
        "Ich habe keinen Zugriff mehr auf meine Uni-Mail, ich kann den Reset-Link nicht empfangen",
    ],
    # Szenario 4: VPN-Verbindung
    [
        "Ich kann mich nicht mit dem Uni-VPN verbinden, ich brauche das für mein Homeoffice",
        "Ich nutze Windows 11 und habe den Cisco AnyConnect Client installiert",
        "Die Fehlermeldung lautet: 'Connection attempt has failed'",
    ],
    # Szenario 5: Software-Lizenz
    [
        "Ich kann meine Campuslizenz für Microsoft Office nicht aktivieren",
        "Ich bin Mitarbeiter der Uni, meine Dienst-Mail ist mustermann@uni-due.de",
        "Die Fehlermeldung sagt 'Kein Abonnement gefunden' obwohl ich berechtigt sein sollte",
    ],
]


MODEL_CONFIGS = {
    "llama-3.1-8b": "meta-llama-3.1-8b-instruct",
    "deepseek-r1-70b":  "deepseek-r1-distill-llama-70b",
    "apertus-70b":      "apertus-70b-instruct-2509",
    "gemma-4-31b":   "gemma-4-31b-it",
}



def run_benchmark_for_model(model_name: str, model_id: str):
    print(f"\n{'='*60}")
    print(f"Teste Modell: {model_name}")
    print(f"{'='*60}\n")

    # Für DeepSeek: ThinkStripChatOpenAI, für alle anderen: normales ChatOpenAI
    llm_class = ThinkStripChatOpenAI if "deepseek" in model_id.lower() \
        else LlamaPatchForChatOpenAI if "llama" in model_id.lower() \
        else ChatOpenAI

    new_llm = llm_class(
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

    with patch("backend.graph.nodes.llm", new_llm), \
         patch("backend.graph.nodes.structured_llm", new_structured_llm):


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