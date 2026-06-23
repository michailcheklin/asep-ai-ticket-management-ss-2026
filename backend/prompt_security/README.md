# Prompt security checks 
(Currently disabled due to conflicts with the chat flow)

In this folder the code for the prompt security checks is stored. Each prompt goes through three security checks:
1. Prompt injection - Sentences like "Disregard your system prompt" are banned as they could be abused to use the ZIM support bot for other purposes
2. Illegal topics - Requests concerning committing a crime are blocked
3. Off-topic: Requests having nothing to do with the ZIM or any university IT problem are blocked so that ressources of the chatbot only get used for the intended purpose (Currently the LangGraph node that only extracts the issue if it is IT-related does similar purpose)

Files
- `prompt_check_pipeline.py` - There the HuggingFace models are defined which are used for the prompt checks
- `prompt_security_result.py` - Here the three security checks are implemented along with a helper method to translate the input into English, because most HuggingFace models only work with English language inputs.
- `security_logger.py` - Writes any prompt security related incidents into a log file to help traceability.
- `helper.py` - Does all three security checks in parallel

Extension of the code
* To add security checks, implement a method into `prompt_security_result.py`
* To add or change the HuggingFace models configure the HuggingFace model used in `prompt_check_pipeline.py`

