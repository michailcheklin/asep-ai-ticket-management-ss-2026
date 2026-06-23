import os

from deepeval.models import GPTModel
from dotenv import load_dotenv

load_dotenv()
SAIA_API_KEY = os.environ.get("SAIA_API_KEY", "")

# The configuration so that the SAIA API from GWDG is used
SAIA_MODEL = GPTModel(
    model="deepseek-r1-distill-llama-70b",
    temperature=0,
    api_key=SAIA_API_KEY,
    base_url="https://chat-ai.academiccloud.de/v1/"
)
