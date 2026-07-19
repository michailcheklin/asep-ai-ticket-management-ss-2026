import torch

from .security_logger import log_blocked_prompt
from datetime import datetime
from backend.prompt_security.prompt_check_model_setup import (
    ZIM_KEYWORDS,
    DANGEROUS_PATTERNS,
    ON_TOPIC_TOPICS,
    ON_TOPIC_DETECTION_THRESHOLD,
    ILLEGAL_TOPICS,
    ILLEGAL_TOPIC_DETECTION_THRESHOLD,
    translator,
    translator_tokenizer,
    prompt_injection_detector,
    topic_classifier,
    device
)


def evaluate_prompt_injection(text: str) -> dict:
    """
    Evaluate a prompt for prompt injection and return an explainable decision.
    """
    text = __translate_from_german_into_english(text)
    output = prompt_injection_detector(text)[0]

    label = output.get("label", "")
    score = float(output.get("score", 0.0))

   
    print("Injection Output:", output)



    text_lower = text.lower()
    has_attack_pattern = any(pattern in text_lower for pattern in DANGEROUS_PATTERNS)

    blocked = has_attack_pattern    
    

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    result = {
        "checked_for": "prompt injection",
        "allowed": not blocked,
        "reason": "Prompt Injection" if blocked else None,
        "model_label": label,
        "risk_score": round(score, 3),
        "checked_text": text,
        "timestamp": timestamp,
    }

    if not result["allowed"]:
        log_blocked_prompt(
            prompt=text,
            reason=result["reason"],
            risk_score=result["risk_score"]
        )

    return result


def evaluate_legality(text:str) -> dict:
    """
    Check the prompt for illegal topics.
    :param text: The text to check (in English after translation)
    :return: Result dict; ``allowed`` is False if illegal topics were detected
    """
    text = __translate_from_german_into_english(text)

    output = topic_classifier(text, ILLEGAL_TOPICS, multi_label=True)
    topics_and_scores = list(zip(output["labels"], output["scores"]))
    topics_and_scores = sorted(topics_and_scores, key=lambda x: x[1], reverse=True)
    most_relevant_topic, most_relevant_score = topics_and_scores[0]
    # Keyword matching is currently a temporary safeguard to reduce false
    # positives on legitimate ZIM requests. This should later be replaced by
    # a more robust assessment, because keywords alone cannot reliably
    # distinguish normal support requests from mixed/dangerous ones.



    is_zim_ticket = any(keyword in text.lower() for keyword in ZIM_KEYWORDS)

    blocked = (
        not is_zim_ticket
        and len([x for x in output["scores"] if x > ILLEGAL_TOPIC_DETECTION_THRESHOLD]) > 0
    )


    result = {
        "checked_for":"legality of prompt",
        "allowed": not blocked,
        "reason": "Illegal topics" if blocked else None,
        "model_label": most_relevant_topic,
        "risk_score": round(most_relevant_score, 3),
        "checked_text": text,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    if not result["allowed"]:
        log_blocked_prompt(
            prompt=text,
            reason=result["reason"],
            risk_score=result["risk_score"]
        )

    return result


def evaluate_off_topic(text:str) -> dict:
    """
    Check whether a prompt is unrelated to ZIM topics.
    :param text: The text to check (in English after translation)
    :return: Result dict; ``allowed`` is False if the prompt is off-topic
    """

    text = __translate_from_german_into_english(text)

    output = topic_classifier(text, ON_TOPIC_TOPICS, multi_label=True)
    topics_and_scores = list(zip(output["labels"], output["scores"]))
    topics_and_scores = sorted(topics_and_scores, key=lambda x: x[1], reverse=True)
    most_relevant_topic, most_relevant_score = topics_and_scores[0]

    blocked = len([x for x in output["scores"] if x > ON_TOPIC_DETECTION_THRESHOLD]) == 0

    result = {
        "checked_for": "off-topic",
        "allowed": not blocked,
        "reason": "Off-Topic" if blocked else None,
        "model_label": "Off-Topic" if blocked else None,
        # For off-topic decisions: the lower the highest topic score,
        # the more off-topic the text is considered.
        "risk_score": round(1-most_relevant_score, 3),
        "checked_text": text,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    if not result["allowed"]:
        log_blocked_prompt(
            prompt=text,
            reason=result["reason"],
            risk_score=result["risk_score"]
        )
    return result




def __translate_from_german_into_english(text: str) -> str:
    """
    Translate text from German to English because the classifier was trained
    on English text.
    :param text: German input text
    :return: English translation
    """
    # Source: https://discuss.huggingface.co/t/issue-with-summarization-and-translation-pipeline/173919/4#p-252057-translation-example-marian-12
    inputs = translator_tokenizer(text, return_tensors="pt", truncation=True).to(device)

    with torch.no_grad():
        out = translator.generate(**inputs)

    translation = translator_tokenizer.decode(out[0], skip_special_tokens=True)
    print(f"English translation: '{translation}'")
    return translation
