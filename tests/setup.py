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

SAIA_MODEL = make_model("gemma-4-31b-it")

SIMULATOR_MODEL = make_model("teuken-7b-instruct-research")