"""Pure helpers for the frontend multiple-choice Q&A widget.

Kept free of Streamlit and HTTP client imports so unit tests can import
this module without the live app runtime.
"""
from __future__ import annotations

import re


def parse_questions_from_message(content: str) -> list[dict]:
    """Extract top-level bullet-point questions from a bot message.

    Supports two formats:
      MCQ:   "* Question? (options: A, B, C)"
      Open:  "* Question?"

    Nested answer bullets (for example lines indented under a question) are
    ignored so they remain visible in the rendered markdown.
    """
    questions: list[dict] = []
    bullet_pattern = re.compile(r"^\s*[\*\-]\s+")

    for line in content.splitlines():
        if not bullet_pattern.match(line):
            continue

        q_text = bullet_pattern.sub("", line).strip()
        options_match = re.search(r"\s*\(options:\s*(.+?)\)\s*$", q_text)
        if options_match:
            options = [o.strip().strip("[]") for o in options_match.group(1).split(",")]
            q_clean = q_text[: options_match.start()].strip()
            questions.append({"text": q_clean, "options": options})
        else:
            questions.append({"text": q_text, "options": None})
    return questions


def contains_nested_bullets(content: str) -> bool:
    """Return True when the message contains indented bullet points."""
    return any(re.match(r"^\s+[\*\-]\s+", line) for line in content.splitlines())


def format_answers_as_message(questions: list[dict], answers: list[str]) -> str:
    """Combine collected Q&A pairs into the backend-expected plain-text format.

    Example output:
        * Which OS are you using?
            * Windows
        * In which room are you?
            * Others: R11
    """
    return "\n".join(
        f"* {q['text']}\n    * {option}: {detail}" if ": " in a and (option := a.split(": ", 1)[0]) and (detail := a.split(": ", 1)[1])
        else f"* {q['text']}\n    * {a}"
        for q, a in zip(questions, answers)
    )


def is_other_option(option: str) -> bool:
    """Return True when the chosen option is an open-ended 'other' variant."""
    return bool(
        re.search(r"\b(other|others|andere[sr]?|sonstige[sr]?)\b", option, re.IGNORECASE)
    )


def can_go_back(current_idx: int) -> bool:
    """True when the user may navigate to a previous question."""
    return current_idx > 0


def navigate_back(current_idx: int, answers: list[str]) -> tuple[int, list[str]]:
    """Move one step back in the questionnaire without dropping stored answers.

    Subsequent answers stay in *answers* so they can be restored if the user
    continues without changing the revisited question. They are truncated only
    when ``apply_question_answer`` detects a changed answer.
    """
    if not can_go_back(current_idx):
        return current_idx, list(answers)
    return current_idx - 1, list(answers)


def apply_question_answer(
    current_idx: int,
    answers: list[str],
    answer: str,
    *,
    is_last: bool,
) -> tuple[int, list[str], bool]:
    """Store *answer* at *current_idx* and advance (or finish) the questionnaire.

    Returns ``(new_idx, new_answers, is_complete)``.

    - If the answer at this index is unchanged, later answers are kept.
    - If it is new or changed, answers after this index are discarded so
      dependent follow-ups are re-answered.
    """
    answers = list(answers)
    if current_idx < len(answers) and answers[current_idx] == answer:
        new_answers = answers
    else:
        new_answers = answers[:current_idx] + [answer]

    if is_last:
        return current_idx, new_answers, True
    return current_idx + 1, new_answers, False


def split_stored_mcq_answer(
    stored: str | None,
    options: list[str],
) -> tuple[str | None, str]:
    """Recover the selected option and optional free-text detail from a stored answer.

    Stored forms:
      - ``"Windows"``
      - ``"Andere: R11"`` (other-option with detail)
    """
    if not stored:
        return None, ""

    if ": " in stored:
        option, detail = stored.split(": ", 1)
        if option in options and is_other_option(option):
            return option, detail

    if stored in options:
        return stored, ""

    for option in options:
        if stored == option or stored.startswith(f"{option}: "):
            detail = stored[len(option) + 2 :] if stored.startswith(f"{option}: ") else ""
            return option, detail
    return None, ""
