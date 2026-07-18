from deepeval.metrics import ConversationCompletenessMetric

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
    "llama-3.1-8b": "meta-llama-3.1-8b-instruct",
    "deepseek-r1-70b":  "deepseek-r1-distill-llama-70b",
    "apertus-70b":      "apertus-70b-instruct-2509",
    "gemma-4-31b":   "gemma-4-31b-it",
}

METRICS = [ConversationCompletenessMetric(model=SAIA_JUDGE_MODEL, async_mode=False)]

BENCHMARK_FILE_PATH = "tests/benchmark_conversation_results.json"



def test_conversation_benchmark():
    """
    Executes the conversation benchmark on the deepeval test template instance
    This method wrapping is made to allow to have a reusable DeepEval test template
    concerning chatbot chat tests while making Pytest still be
    able to run this in a CI pipeline
    """
    conversation_benchmark = DeepEvalTestTemplate(
        scenarios=SCENARIOS,
        metrics=METRICS,
        configs_of_models_to_test=MODEL_CONFIGS,
        benchmark_file_path=BENCHMARK_FILE_PATH,
    )
    conversation_benchmark.test_benchmark_all_models()