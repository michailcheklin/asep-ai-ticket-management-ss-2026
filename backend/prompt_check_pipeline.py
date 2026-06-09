import torch
import os
from transformers import pipeline, MarianTokenizer, MarianMTModel

huggingface_model_folder = os.getenv("HF_HOME", "/models")

ILLEGAL_TOPICS:list[str] = ["terrorism", "crime", "copyright infringement"]
ILLEGAL_TOPIC_DETECTION_THRESHOLD:float = 0.5

# Quelle: https://www.uni-due.de/zim/hilfecenter/faqs.php
# Versuchen, eine kleinstmögliche Liste von Labels zu definieren,
# da je mehr Labels geprüft werden, desto länger dauert die Prüfung,
# ob die Nachricht themenfremd ist
ON_TOPIC_TOPICS:list[str] = ["computer problem", "network", "email", "moodle", "media technology", "system management"]
ON_TOPIC_DETECTION_THRESHOLD:float = 0.5

# Wenn der 
# Text als nicht Prompt Injection gesehen wird, aber die
# Confidence unter dieser Schwelle liegt, soll der Text trotzdem abgelehnt werden
PROMPT_INJECTION_BLOCK_THRESHOLD:float = 0.7

# Auswahl der Device (GPU falls vorhanden, sonst CPU) für die Generierung der Übersetzung
device:str = "cuda" if torch.cuda.is_available() else "cpu"

# Themenklassifizierer
topic_classifier = pipeline("zero-shot-classification", model="MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli")

# Übersetzer (Deutsch -> Englisch)
translator_model_id = "Helsinki-NLP/opus-mt-de-en"
translator_tokenizer = MarianTokenizer.from_pretrained(translator_model_id)
translator = MarianMTModel.from_pretrained(translator_model_id).to(device).eval()

# Prompt Injection-Erkenner
prompt_injection_detector = pipeline("text-classification", model="deepset/deberta-v3-base-injection")