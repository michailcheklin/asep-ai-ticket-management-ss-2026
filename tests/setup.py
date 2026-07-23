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


SAIA_MODEL = make_model("gemma-4-31b-it")

