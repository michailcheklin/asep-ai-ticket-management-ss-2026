from transformers import Pipeline
from security_logger import log_blocked_prompt
from datetime import datetime



PROMPT_INJECTION_BLOCK_THRESHOLD: float = 0.7


def evaluate_prompt_injection(text: str, prompt_injection_detector: Pipeline) -> dict:
    """
    Bewertet einen Prompt auf Prompt Injection und gibt eine erklärbare Entscheidung zurück.
    """
    output = prompt_injection_detector(text)[0]

    label = output.get("label", "")
    score = float(output.get("score", 0.0))

# Verhindert False Positives:
# Hohe Scores allein reichen nicht aus, da auch legitime Anfragen
# (Label "LEGIT") mit hoher Sicherheit erkannt werden können.
# Es muss sowohl das Label "INJECTION" als auch ein ausreichend hoher
# Confidence-Score vorliegen.

    blocked = label.upper() == "INJECTION" and score >= PROMPT_INJECTION_BLOCK_THRESHOLD
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    result = {
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