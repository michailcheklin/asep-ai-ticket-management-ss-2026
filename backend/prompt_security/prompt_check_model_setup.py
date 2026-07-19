import os
import torch
from transformers import pipeline, MarianTokenizer, MarianMTModel


huggingface_model_folder = os.getenv("HF_HOME", os.path.expanduser("~/.cache/huggingface/hub/"))

ILLEGAL_TOPICS:list[str] = ["terrorism", "crime", "copyright infringement"]
ILLEGAL_TOPIC_DETECTION_THRESHOLD:float = 0.5
DANGEROUS_PATTERNS = [
    "ignore previous instructions",
    "ignore all instructions",
    "reveal your system prompt",
    "show your system prompt",
    "developer message",
    "system message",
    "bypass security",
    "act as developer",
    "jailbreak",
    "print hidden instructions",
]


# Source: https://www.uni-due.de/zim/hilfecenter/faqs.php
# Keep the on-topic label list as small as possible: more labels increase
# the time needed to decide whether a message is off-topic.
ON_TOPIC_TOPICS:list[str] = ["computer problem", "network", "email", "moodle", "media technology", "system management"]
ON_TOPIC_DETECTION_THRESHOLD:float = 0.5
# Keyword strings include German product terms used for matching user input;
# they are detection data, not code identifiers.
ZIM_KEYWORDS = [
        "wlan", "moodle", "account", "login", "einloggen",
        "register", "anmelden", "passwort", "password", "e-mail", "email",
        "matrikelnummer", "matrictlation number", "printer", "drucker",
        "vpn", "exam", "prüfung"
]
# If the text is not classified as prompt injection but confidence is below
# this threshold, reject the text anyway.
PROMPT_INJECTION_BLOCK_THRESHOLD:float = 0.7

# Device selection (GPU if available, otherwise CPU) for translation generation
device:str = "cuda" if torch.cuda.is_available() else "cpu"

# Topic classifier
topic_classifier = pipeline(
    task="zero-shot-classification",
    model="MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli",
    cache_dir=huggingface_model_folder,
)

# Translator (German -> English)
translator_model_id = "Helsinki-NLP/opus-mt-de-en"
translator_tokenizer = MarianTokenizer.from_pretrained(
    translator_model_id,
    cache_dir=huggingface_model_folder,
)
translator = MarianMTModel.from_pretrained(
    translator_model_id,
    cache_dir=huggingface_model_folder,
).to(device).eval()

# Prompt-injection detector
prompt_injection_detector = pipeline(
    task="text-classification",
    model="deepset/deberta-v3-base-injection",
    cache_dir=huggingface_model_folder,
)
