import torch
import os
from transformers import pipeline, Pipeline, MarianTokenizer, MarianMTModel

huggingface_model_folder = os.getenv("HF_HOME", "/models")

ILLEGAL_TOPICS:list[str] = ["terrorism", "violence", "crime"]
ILLEGAL_TOPIC_DETECTION_THRESHOLD:float = 0.5

# Quelle: https://www.uni-due.de/zim/hilfecenter/faqs.php
# Versuchen, eine kleinstmögliche Liste von Labels zu definieren,
# da je mehr Labels geprüft werden, desto länger dauert die Prüfung,
# ob die Nachricht themenfremd ist
ON_TOPIC_TOPICS:list[str] = ["computer problem", "network", "email", "moodle", "media technology", "system management"]
ON_TOPIC_DETECTION_THRESHOLD:float = 0.5

# Wenn der Text als nicht Prompt Injection gesehen wird, aber die
# Confidence unter dieser Schwelle liegt, soll der Text trotzdem abgelehnt werden
PROMPT_INJECTION_THRESHOLD:float = 0.7

# Auswahl der Device (GPU falls vorhanden, sonst CPU) für die Generierung der Übersetzung
device:str = "cuda" if torch.cuda.is_available() else "cpu"

def initialize_models() -> tuple:
    """
    Diese Methode setzt die für die Prompt-Überprüfung notwendigen Hugging-Face-LLM auf
    :return: In dieser Reihenfolge als Tupel: Der Themenklassifizierer, der Tokenizer des Übersetzers,
    der Übersetzer und der Prompt-Injection-Detektor
    """
    print("Hugging Face-LLMs für die Prüfung des Prompts herunterladen und initialisieren...")

    # Themenklassifizierer
    topic_classifier:Pipeline = pipeline("zero-shot-classification", model="MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli")

    # Übersetzer (Deutsch -> Englisch)
    model_id:str = "Helsinki-NLP/opus-mt-de-en"
    translator_tokenizer:MarianTokenizer = MarianTokenizer.from_pretrained(model_id)
    translator:MarianMTModel = MarianMTModel.from_pretrained(model_id).to(device).eval()

    # Prompt Injection-Erkenner
    prompt_injection_detector:Pipeline = pipeline("text-classification", model="deepset/deberta-v3-base-injection")

    print("Hugging Face-LLMs für die Prüfung des Prompts erfolgreich initialisiert")
    return topic_classifier, translator_tokenizer, translator, prompt_injection_detector

if __name__ == "__main__":
    initialize_models()