# Test environment

## Prerequisites for the LLM tests
DeepEval (https://deepeval.com/) is a framework to test LLM outputs. Before the tests can start, you have to do the following steps:

1. Install `deepeval` using `pip install -U deepeval`. 
2. (Optional for our project): Setup Confident AI. Confident AI is a dashboard that hosts the results of all DeepEval tests. For each test there is an exception handling to handle the absence of the ConfidentAI API key to allow to still display the test results in the terminal 
   1. Create an account at Confident AI (https://app.confident-ai.com).
   2. Create a new project
   3. Create a Confident API key under ⚙️ Project Settings (at the bottom left) > API Keys > ➕ Generate New API Key
   4. Choose a name for the ConfidentAI API key
   5. Copy the API key
   6. Write into the .env file `CONFIDENT_API_KEY=<the copied ConfidentAI API key from step 2.5>`
3. Write the SAIA API key into the .env file: `SAIA_API_KEY=<your SAIA API key>`
4. Write `DEEPEVAL_TELEMETRY_OPT_OUT=1` into the .env file to opt out of DeepEval's telemetry if you want to.
5. (Optional) Setup LangSmith for benchmark tracing. LangSmith logs all LLM calls and benchmark results for observability.
   1. Create an account at LangSmith (https://smith.langchain.com). Choose **EU** as data region.
   2. Go to Settings > API Keys > Create API Key
   3. Write into the .env file:
```
      LANGCHAIN_API_KEY=<your LangSmith API key>
      LANGCHAIN_TRACING_V2=true
      LANGCHAIN_PROJECT=ai-ticket-benchmark
      LANGCHAIN_ENDPOINT=https://eu.api.smith.langchain.com
```

## How the folder structure is made to accomodate the testing
Each script that contains test cases ("test script") is in the folder `<project root>/tests`. This helps separating test code from application code. Each test script is named like this: `test_(what_is_tested_here).py` to describe what is tested. 

To ensure that the test scripts can find all the application code, each folder (frontend, backend, tests) has an empty `__init__.py` file. This tells Python to treat the folders as packages (also cf. https://docs.python.org/3/tutorial/modules.html#packages).  **Do not delete this file**. Otherwise, the test scripts cannot find the code from the backend or frontend anymore. 

If you are during regular development import code from other scripts, you need to use the full module path. For example if you need to import in the backend something from `backend/nodes.py` into `backend/main.py`:
* ❌ Incorrect: `from nodes import ...`
* ✅ Correct: `from backend.nodes import ...`



## How each test script is structured
1. Each test has at the beginning imports of all methods that need to be imported for the tests.
2. After that, the input that is tested, is defined ("testcases"). 
3. The actual testing happens in any method, where the name starts with `test` which are automatically treated by Pytest as a test case (cf. https://docs.pytest.org/en/stable/explanation/goodpractices.html#conventions-for-python-test-discovery). 
4. Each test method ends with an assertion to define what condition must be met to consider a test to be passed.
5. Additionally, global states such as counters are saved in Pytest fixtures (cf. https://docs.pytest.org/en/stable/explanation/fixtures.html#what-fixtures-are). 
6. If needed, helper methods such as to perform calculations, can be defined like a normal method, but a helper method's name should not start with `test` so that Pytest does not falsely recognize the function as test case.

### How to test from the command line without the CI/CD pipeline:
1. Open a terminal in the project root
2. Do `cd tests`
3. Do now this: 
   * On Windows `pytest .\<name of test file> -s -v`
   * On Mac/Linux `pytest ./<name of test file> -s -v`
4. The `-s -v` flag causes the normal application to print on the terminal 

## What is tested

### Prompt security check
**What does this test do:** 
In this script, some inputs are sent to the function that checks the prompt for illegal topics, prompt injection and off-topic text. 

**Why is this test done:** 
To check if the prompt security algorithm is not too lax and not too strict.

**How is the test done:** 
For each prompt it is defined whether it is expected that the prompt is OK or not. The test checks if the prompt check correctly blocks or allows inputs and then calculates the accuracy, precision, recall and F1 score.

**When is the test passed:** 
Accuracy, Precision, Recall and F1 score must be above 75%. If any of the metrics falls below that limit, the test is failed. 

**Additional notes:** 
(Currently this feature is disabled due to causing bugs with the chatbot's generation, cf. https://gitlab.git.nrw/ude-sse/asep-sose26/team1-zim/ai-ticket-management/-/merge_requests/19#what-has-changed, the test stays for potential future implementations). 

### Chatbot connectivity
**What does this test do:**
Here it is checked if the chatbot is responsive or not. 

**Why is this test done:**
This test checks first if the chatbot responds before other chatbot tests will be done, because it would be impossible to evaluate the chatbot's responses, if the chatbot cannot reply at all.

**How is the test done:**
In this script, one input is sent to the chatbot, which is expected to return a valid JSON response within 20 minutes. 

**When is the test passed:**
The test is passed if the chatbot responds successfully with a JSON response within the timeout.

**Additional notes:**
If this test fails, the chatbot evaluation tests will not be run

### Chatbot conversation quality
**What does this test do:**
Here it is checked if the chatbot can properly react on the user. The following metrics are checked (also cf. https://deepeval.com/guides/guides-multi-turn-evaluation-metrics):
* Conversation Completeness - Whether the chatbot does address all concerns of the user
* Turn Relevancy - Whether the chatbot can provide relevant answers according to the context
* Knowledge Retention - Whether the chatbot does not forget infos during the conversation.

**Why is this test done:**
This test is done to identify potential quality problems in the way the chatbot generates the responses to the user.

**How is the test done:**
In this script, a conversation between the user and the chatbot is simulated and then evaluated. 

**When is the test passed:**
The test is passed if all the three metrics return a score of over 50% (DeepEval default value).

**Additional notes:**
One test case uses around 30 SAIA prompts within 5-6 minutes, out of which around three quarters are for the metrics.

### LLM Model Benchmark
**What does this test do:**
This script benchmarks multiple GWDG/SAIA LLMs by running them through realistic IT-support conversation scenarios and evaluating their response quality using DeepEval's `ConversationCompletenessMetric`. Results are saved to `tests/benchmark_results.json` and logged to LangSmith.

**Why is this test done:**
To identify which LLM performs best as the chatbot's underlying model for the ZIM ticket management use case, and to document the strengths and weaknesses of each evaluated model.

**How is the test done:**
For each model in `MODEL_CONFIGS`, the chatbot is patched to use that model. Two realistic conversation scenarios are simulated:
* A student whose university WLAN is not showing up in the network list
* A student whose university account is locked

Each scenario produces a `ConversationalTestCase` which is then evaluated by the judge model (Apertus-70B) using the `ConversationCompletenessMetric`. Results are collected and written to `benchmark_results.json`. All LLM calls are automatically traced in LangSmith via the LangChain integration.

**When is the test passed:**
The test always passes (it is a benchmarking script, not a pass/fail test). Results are stored for manual analysis.

**Evaluated models and findings:**

**deepseek-r1-distill-llama-70b** (70B):
- Score: could not be fully evaluated due to rate limits
- Strength: Available via SAIA, strong reasoning capabilities.
- Weakness: Writes long reasoning chains in `<think>` tags before answering, which DeepEval cannot parse reliably. Frequently hits API rate limits.

**apertus-70b-instruct-2509** (70B):
- Score: 0.83 (WLAN scenario), 0.67 (Account scenario)
- Strength: Answers directly without excessive follow-up questions. Best overall results.
- Weakness: Occasionally fails when used as both chatbot and judge simultaneously due to server load (RetryError).

**gemma-4-31b-it** (31B):
- Score: 0.00 (both scenarios)
- Strength: Compatible with the system, no technical errors.
- Weakness: Asks multiple follow-up questions before providing a solution. Conversation ends as incomplete by the metric.

**meta-llama-3.1-8b-instruct** (8B – small model):
- Score: could not be fully evaluated due to rate limits
- Strength: Smallest and fastest model tested, low server demand.
- Weakness: Returns incorrect JSON structure for some scenarios (`needs_additional_info` field missing), causing errors.



**Additional notes:**
* All models are accessed via the GWDG/SAIA API (`https://chat-ai.academiccloud.de/v1/`) which is OpenAI-compatible.
* A known RAG bug causes all models to query "How to connect to the VPN using Forcepoint?" regardless of the actual issue. This affects the quality of solutions provided by all models.
* The judge model (Apertus-70B) evaluates responses — running Apertus as both chatbot and judge simultaneously can cause `RetryError` due to server load.
* Rate limits (`429`) occur after many API calls in one session. 