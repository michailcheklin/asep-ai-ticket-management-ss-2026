from datetime import datetime


LOG_FILE = "blocked_prompts.log"


def log_blocked_prompt(prompt: str, reason: str, risk_score: float | None = None) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(LOG_FILE, "a", encoding="utf-8") as file:
        file.write(f"[{timestamp}]\n")
        file.write(f"Reason: {reason}\n")
        file.write(f"Risk Score: {risk_score}\n")
        file.write(f"Prompt: {prompt}\n")
        file.write("-" * 50 + "\n")