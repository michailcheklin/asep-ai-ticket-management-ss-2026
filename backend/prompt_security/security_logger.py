from datetime import datetime

LOG_FILE = "./backend/blocked_prompts.log"


def log_blocked_prompt(prompt: str, reason: str, risk_score: float | None = None) -> None:
    """
    Diese Methode schreibt einen Log-Eintrag, wenn ein Prompt aus dem Chatbot blockiert wurde.
    In den Logs wird neben dem blockierten Prompt und dem Grund, warum der Prompt blockiert wurde, auch vermerkt,
    von wem (E-Mail + Matr.-Nr.) und wann (Zeit) der Prompt geschickt wurde, vermerkt.
    :param prompt: Der Prompt, der geprüft wurde
    :param reason: Der Grund, warum ein Prompt blockiert wurde
    :param risk_score: Die vom Modell bestimmte Wahrscheinlichkeit, dass der Blockiergrund erfüllt wurde
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(LOG_FILE, "a", encoding="utf-8") as file:
        file.write(f"[{timestamp}]\n")
        file.write(f"Reason: {reason}\n")
        file.write(f"Risk Score: {risk_score}\n")
        file.write(f"Prompt: {prompt}\n")
        file.write("-" * 50 + "\n")