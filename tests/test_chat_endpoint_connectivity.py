import json
import pytest

from backend.api.ZIM import chat_endpoint
from backend.graph.models import ChatRequest

# Nur 3 Tests, um die Prompts beim Key zu sparen
testcases = [
    # Beginn einer Konversation
    {
        "user_message": "Mein WLAN geht nicht",
        "history": [

        ],  # Format: [{"role": "user", "content": "Hallo"}, {"role": "bot", "content": "Hi"}]
        "user_email":"a@example.com",
        "matrikelnummer": "123456789",
        "issue_description": "",
        "additional_info": [],
        "priority": 0
    },
]


@pytest.mark.asyncio
@pytest.mark.parametrize("testcase", testcases)
async def test_chat_endpoint_connectivity(testcase):
    """
    Dieser Test testet, ob das LLM überhaupt eine wohlgeformte Antwort generieren kann,
    d. h. eine gültige JSON. Dies ist Platzhalter, bis ein besseres Verständnis über DeepEval
    für die echte LLM-Analyse gewonnen werden konnte
    :param testcase: Der zu testende Prompt mit dem Kontext als JSON
    """
    test_request_as_chat_request = ChatRequest(**testcase)
    print(f"Sending following request to the chatbot: \n{json.dumps(testcase)}")
    response = await chat_endpoint(test_request_as_chat_request)
    print(f"The chatbot responded with the following response: \n{json.dumps(response)}")
    assert isinstance(response, dict), "Response should be a dictionary"
    assert "bot_response" in response, "Response should contain a 'bot_response' key"
