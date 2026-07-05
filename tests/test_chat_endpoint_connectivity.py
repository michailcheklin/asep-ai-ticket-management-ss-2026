import json
import pytest
from openai import InternalServerError, RateLimitError

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
@pytest.mark.flaky(reruns=3, reruns_delay=30, only_on=[InternalServerError])
async def test_chat_endpoint_connectivity(testcase):
    """
    This test checks whether the LLM can generate a well-formed response at all,
    i.e., valid JSON.
    :param testcase: The prompt to test along with the context packed in a JSON file
    """

    try:
        test_request_as_chat_request = ChatRequest(**testcase)
        print(f"Sending following request to the chatbot: \n{json.dumps(testcase)}")
        response = await chat_endpoint(test_request_as_chat_request)
        print(f"The chatbot responded with the following response: \n{json.dumps(response)}")
        assert isinstance(response, dict), "Response should be a dictionary"
        assert "bot_response" in response, "Response should contain a 'bot_response' key"
    except RateLimitError:
        # If rate limit was hit, test passes, but gives a message about that.
        # Rate limit error means that the server could be reached,
        # however the request was rejected due to the rate limit
        # This is different to the HTTP 500 error, which means that the server could not
        # be reached at all
        print("The API server could be reached but the rate limit was hit.")
        assert True

