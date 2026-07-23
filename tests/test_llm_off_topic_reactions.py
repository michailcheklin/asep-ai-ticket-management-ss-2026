from deepeval.metrics import ConversationalGEval
from deepeval.test_case import MultiTurnParams

from tests.llm_benchmark_template import DeepEvalTestTemplate
from tests.setup import SAIA_JUDGE_MODEL

SCENARIOS = [
    # Off-Topic-Anfragen
    ["Wie backe ich einen Kuchen?"],
    ["Ich möchte ein Flugticket nach Mallorca kaufen."],
    ["Welches Brautkleid steht mir am besten?"]
]


MODEL_CONFIGS = {
    "llama-3.1-8b": "meta-llama-3.1-8b-instruct",
    "deepseek-r1-70b": "deepseek-r1-distill-llama-70b",
    "apertus-70b": "apertus-70b-instruct-2509",
    "gemma-4-31b": "gemma-4-31b-it",
}

# Custom GEval metric (Deepeval docs on usage:
# https://deepeval.com/docs/metrics-conversational-g-eval
METRICS = [
    ConversationalGEval(
        name="Off-Topic Handling",
        criteria="""
        Check based on the content that when a user writes a question 
        that does not have anything to do with IT problems, 
        the chatbot writes nicely that it only can answer 
        questions that relate to IT problems on a university.
        """,
        evaluation_params=[
            MultiTurnParams.CONTENT,
        ],
        model=SAIA_JUDGE_MODEL,
        async_mode=False
    )
]

BENCHMARK_FILE_PATH = "tests/off_topic_reactions_results.json"



def test_off_topic_reactions():
    """
    Executes the off-topic reaction test on the deepeval test template instance.
    This method wrapping is made to allow to have a reusable DeepEval test template
    concerning chatbot chat tests while making Pytest still be
    able to run this in a CI pipeline
    """
    off_topic_reaction_test = DeepEvalTestTemplate(
        scenarios=SCENARIOS,
        metrics=METRICS,
        configs_of_models_to_test=MODEL_CONFIGS,
        benchmark_file_path=BENCHMARK_FILE_PATH,
    )
    off_topic_reaction_test.test_benchmark_all_models()