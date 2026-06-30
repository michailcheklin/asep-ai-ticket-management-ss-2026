import json
import pytest
from openai import InternalServerError

from backend.api.ZIM import chat_endpoint
from backend.graph.models.ChatRequest import ChatRequest

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
@pytest.mark.flaky(reruns=3, reruns_delay=1, only_on=[InternalServerError])
async def test_chat_endpoint_connectivity(testcase):
    """
    This test checks whether the LLM can generate a well-formed response at all,
    i.e., valid JSON.
    :param testcase: The prompt to test along with the context packed in a JSON file
    """


    test_request_as_chat_request = ChatRequest(**testcase)
    print(f"Sending following request to the chatbot: \n{json.dumps(testcase)}")
    response = await chat_endpoint(test_request_as_chat_request)
    print(f"The chatbot responded with the following response: \n{json.dumps(response)}")
    assert isinstance(response, dict), "Response should be a dictionary"
    assert "bot_response" in response, "Response should contain a 'bot_response' key"
