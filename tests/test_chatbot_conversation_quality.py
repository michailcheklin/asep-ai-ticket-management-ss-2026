from deepeval.evaluate import evaluate
from deepeval.metrics import ConversationCompletenessMetric, TurnRelevancyMetric, KnowledgeRetentionMetric
from deepeval.simulator import ConversationSimulator
from deepeval.simulator.controller import end, proceed

from backend.api.ZIM import chat_endpoint
from backend.graph.models.ChatRequest import ChatRequest
from tests.setup import SAIA_MODEL
from deepeval.dataset import EvaluationDataset, ConversationalGolden
from deepeval.test_case import Turn

# Special "response" object that denotes that the chatbot was not called yet in the test
EMPTY_LAST_RESPONSE_FROM_CHATBOT = {
            "bot_response": "",
            "user_email": "",
            "matrikelnummer": "",
            "issue_description": "",
            "additional_info": [],
            "needs_additional_info": False,
            "priority": 0,
            "is_complete": False,
            "solutions": [],
            "additional_info_attempts": 0,
            "ask_issue_attempts": 0,
        }


# Our test case
dataset = EvaluationDataset(goldens=[
    ConversationalGolden(
        scenario="Nicht-technischer Kunde, der Probleme mit dem WLAN in der Universitätsbibliothek schildert",
        expected_outcome="Kunde erhält Lösungsvorschläge zur Behebung des geschilderten WLAN-Problems",
        user_description="Nicht-technischer Kunde, der dazu tendiert, vage Informationen zu geben, es sei denn er wird"
                         " explizit nach Details gefragt",
        turns=[
            # The initial message from the frontend that is shown
            Turn(role="assistant", content="Hallo! Ich bin ZIM Helper. Erzähl mir bitte von deinem Anliegen."),

            # The first thing that the user types into the chat
            Turn(role="user", content="Mein WLAN geht nicht")

            # After that the chatbot test decides what the user enters into the chat
            # and then how the simulated user on the subsequent chatbot output reacts
        ]
    ),
])


# Our test metrics:
# Did the bot address the user's conversation completely?
conversation_completeness_metric = ConversationCompletenessMetric(
    model=SAIA_MODEL,
)

# Did the bot lose the topic's relevance over the conversation?
turn_relevancy_metric = TurnRelevancyMetric(
    model=SAIA_MODEL,
)

# Did the bot lose the already found knowledge over the conversation?
knowledge_retention_metric = KnowledgeRetentionMetric(
    model=SAIA_MODEL,
)

next_requests_store: dict[str, dict] = {}
last_responses_store:dict[str, dict] = {}

# Wrapping the chatbot call into a callback for DeepEval
async def model_callback(input: str, turns: list, thread_id: str) -> Turn:
    """
    This function wraps the call of the chatbot into a DeepEval model callback which is then tested.
    This runs until a solution is found or until a maximum number of messages.
    Most important is that the chatbot correctly extracts the info because when a solution is
    presented, the user can still press No and cause a ticket to be created.
    :param input: The current user input
    :param turns: The DeepEval last Turns that have been sent
    :param thread_id: The DeepEval testcase thread ID to differentiate different test cases
    :return: A DeepEval Turn object for evaluation
    """
    if not thread_id in last_responses_store:
        last_responses_store[thread_id] = EMPTY_LAST_RESPONSE_FROM_CHATBOT

    # Prepare the request to send
    next_request_to_send = next_requests_store.get(thread_id, {
        "user_message": "",
        "history": [],
        "user_email": "a@example.com",
        "matrikelnummer": "1234567",
        "issue_description": "",
        "additional_info": [],
        "priority": 0,
        "helpful": False,
        "solutions": [],
        "bot_message": "",
        "additional_info_attempts": 0,
        "ask_issue_attempts": 0,
    })
    next_request_to_send["user_message"] = input
    next_request_to_send_as_chatrequest = ChatRequest(**next_request_to_send)

    # Get response
    response = await chat_endpoint(next_request_to_send_as_chatrequest)
    last_responses_store[thread_id] = response

    # Update the test session state with the latest response
    new_next_request_to_send = {
        "user_message": "",
        "history": [],
        "user_email": next_request_to_send["user_email"],
        "matrikelnummer": next_request_to_send["matrikelnummer"],
        "issue_description": response["issue_description"],
        "additional_info": response["additional_info"],
        "priority": response["priority"],
        "helpful": False,
        "solutions": response["solutions"],
        "bot_message": "",
        "additional_info_attempts": response["additional_info_attempts"],
        "ask_issue_attempts": response["ask_issue_attempts"],
    }
    next_requests_store[thread_id] = new_next_request_to_send

    # Convert response to DeepEval Turn
    return Turn(role="assistant", content=response["bot_response"])


async def stopping_controller(thread_id:str = None, **kwargs):
    """
    This causes the test case to be stopped, if solutions are shown to the user
    along with the Yes/No buttons on "Did this help?" if a solution was found.
    :param thread_id: The DeepEval testcase thread ID
    :param kwargs: Any other arguments DeepEval automatically passes
    :return:
    """
    if thread_id not in last_responses_store:
        return proceed()

    if last_responses_store[thread_id].get("is_complete", False)\
            or len(last_responses_store[thread_id].get("solutions", [])) > 0:
        return end()

    return proceed()

# Create simulator and run the test
simulator = ConversationSimulator(
    model_callback=model_callback,
    simulator_model=SAIA_MODEL,
    language="German",
    stopping_controller=stopping_controller,
    async_mode=True,
    max_concurrent=1

)
test_cases = simulator.simulate(
    conversational_goldens=dataset.goldens,
    max_user_simulations=6,
)

# Evaluate the test cases
evaluate(
    test_cases=test_cases,
    metrics=[
        conversation_completeness_metric,
        turn_relevancy_metric,
        knowledge_retention_metric,
    ],
)