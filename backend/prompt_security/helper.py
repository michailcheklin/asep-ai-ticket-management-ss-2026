import concurrent.futures
from .prompt_security_checks import (
    evaluate_prompt_injection,
    evaluate_legality,
    evaluate_off_topic
)

def __check_prompt (prompt:str) -> list[dict]:
    """
    Run all prompt safety checks in parallel.

    The user input is checked for prompt injection, illegal content
    and off-topic requests before being processed by the chatbot.

    :param prompt: User input to validate
    :return: List containing the results of all safety checks
    """
    # Execute all prompt safety checks concurrently.
    with (concurrent.futures.ThreadPoolExecutor() as executor):
        prompt_injection_detection = executor.submit(evaluate_prompt_injection, prompt)
        illegal_topics_detection = executor.submit(evaluate_legality, prompt)
        off_topic_detection = executor.submit(evaluate_off_topic, prompt)

        prompt_injection_detection_result = prompt_injection_detection.result()
        illegal_topics_detection_result = illegal_topics_detection.result()
        off_topic_detection_result = off_topic_detection.result()

    complete_evaluation = [
        prompt_injection_detection_result,
        illegal_topics_detection_result,
        off_topic_detection_result
    ]

    return complete_evaluation