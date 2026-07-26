from deepeval.metrics import ConversationCompletenessMetric, ConversationalGEval
from deepeval.test_case import MultiTurnParams

from tests.llm_benchmark_template import DeepEvalTestTemplate
from tests.setup import SAIA_JUDGE_MODEL


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
    "llama-3.1-8b":    "meta-llama-3.1-8b-instruct",
    "deepseek-r1-70b": "deepseek-v4-flash",
    "apertus-70b":     "apertus-70b-instruct-2509",
    "gemma-4-31b":     "gemma-4-31b-it",
    "gpt-oss-120b":    "openai-gpt-oss-120b",              
    "glm-4.7":         "glm-4.7",  
}
METRICS = [
    ConversationCompletenessMetric(
        model=SAIA_JUDGE_MODEL, async_mode=False, threshold=0.5,
    ),
    ConversationalGEval(
        name="Hallucination Detection",
        criteria=(
            "Assess whether every factual claim, instruction step, URL, or "
            "detail the assistant provides is grounded in the conversation and "
            "plausible for university IT support. Award a HIGH score when the "
            "assistant stays factual and does not invent steps, links, contact "
            "details, or capabilities. Award a LOW score when it fabricates or "
            "states unsupported information."
        ),
        evaluation_params=[MultiTurnParams.CONTENT],
        model=SAIA_JUDGE_MODEL, async_mode=False, threshold=0.7,
    ),
    ConversationalGEval(
        name="Knowledge Retention",
        criteria=(
            "Assess whether the assistant remembers information the user has "
            "already provided earlier in the conversation. Award a HIGH score "
            "when it reuses known details and does not ask again for them. "
            "Award a LOW score when it re-asks for information the user already "
            "gave (e.g. device, OS, email, error message)."
        ),
        evaluation_params=[MultiTurnParams.CONTENT],
        model=SAIA_JUDGE_MODEL, async_mode=False, threshold=0.7,
    ),
    ConversationalGEval(
        name="Answer Relevancy",
        criteria=(
            "Assess whether each assistant turn directly addresses the user's "
            "current request or question. Award a HIGH score when every answer "
            "is on-point and useful for the user's IT problem. Award a LOW "
            "score when answers are vague, off-topic, or ignore what the user asked."
        ),
        evaluation_params=[MultiTurnParams.CONTENT],
        model=SAIA_JUDGE_MODEL, async_mode=False, threshold=0.7,
    ),
]


BENCHMARK_FILE_PATH = "tests/benchmark_conversation_results.json"


def test_conversation_benchmark():
    conversation_benchmark = DeepEvalTestTemplate(
        scenarios=SCENARIOS,
        metrics=METRICS,
        configs_of_models_to_test=MODEL_CONFIGS,
        benchmark_file_path=BENCHMARK_FILE_PATH,
    )
    conversation_benchmark.test_benchmark_all_models()