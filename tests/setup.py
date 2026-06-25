import os
from deepeval.models import GPTModel
from dotenv import load_dotenv



load_dotenv()
SAIA_API_KEY = os.environ.get("SAIA_API_KEY", "")
SAIA_BASE_URL = "https://chat-ai.academiccloud.de/v1/"

def make_model(model_id: str) -> GPTModel:
    return GPTModel(
        model=model_id,
        temperature=0,
        api_key=SAIA_API_KEY,
        base_url=SAIA_BASE_URL
    )

MODELS_TO_EVALUATE = {
    "deepseek-r1-70b":  make_model("deepseek-r1-distill-llama-70b"),
    "apertus-70b":      make_model("apertus-70b-instruct-2509"),
    "qwen3.6-35b":      make_model("qwen3.6-35b-a3b"),
    "teuken-7b":        make_model("teuken-7b-instruct-research"),
}

# Judge-Modell für DeepEval (bewertet die Antworten)
# Wir nutzen DeepSeek als Judge, da es schon bekannt und stabil ist
# 1.Änderungenn nach Fehlermeldung: DeepSeek-R1 schreibt zuerst langen Denkprozess in <think>-Tags — DeepEval erwartet strukturierte JSON-Antworten und kann das nicht sauber parsen
# Apertus antwortet direkt ohne solche Tokens und ist das zuverlässigere Judge-Modell
SAIA_MODEL = make_model("apertus-70b-instruct-2509")

# Simulator-Modell für DeepEval (spielt den Nutzer im Gespräch nach)
# Teuken-7b ist ein kleines 7B-Modell und dadurch deutlich schneller als Apertus-70b,
# was die Simulationszeit stark reduziert. Die Qualität der Bewertung bleibt trotzdem
# gut, da für die Metriken weiterhin Apertus als Judge-Modell (SAIA_MODEL) verwendet wird.
SIMULATOR_MODEL = make_model("teuken-7b-instruct-research")