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

If you are during regular development import code from other scripts, you need to use the full module path. For example if you need to import in the backend something from `backend/graph/nodes.py` into `backend/main.py`:
* ❌ Incorrect: `from nodes import ...`
* ✅ Correct: `from backend.graph.nodes import ...`



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

**Exception — LLM benchmark test and RAG retrieval test:** These tests must be run from the project root, not from the `tests/` folder, because they import backend modules that require the project root to be on the Python path:
   * LLM benchmark test:
     * On Windows `set PYTHONPATH=. && pytest tests/test_llm_benchmark.py -v -s`
     * On Mac `PYTHONPATH=. pytest tests/test_llm_benchmark.py -v -s`
   * RAG retrieval test:
     * On Windows `set PYTHONPATH=. && pytest tests/test_rag_retrieve.py -v -s`
     * On Mac `PYTHONPATH=. pytest tests/test_rag_retrieve.py -v -s`

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

### Graph node unit tests
**What do these tests do:**
These scripts unit-test individual LangGraph nodes from `backend/graph/nodes.py` in isolation, with all LLM, RAG-retrieval and Zammad calls mocked:
* `test_intent_classification.py` — `classify_intent`
* `test_ticket_category.py` — `classify_ticket`, `classify_ticket_category`, `extract_information`, `finish_ticket`, `_resolve_ticket_category`
* `test_ticket_category_live.py` — `classify_ticket_category` against the real LLM (live counterpart to `test_ticket_category.py`)
* `test_ask_for_additional_info.py` — `ask_for_additional_info`
* `test_give_solutions.py` — `give_solutions`
* `test_question_back_navigation.py` — frontend MCQ back navigation (`frontend.ui.qa_navigation`)

**Why is this test done:**
To catch regressions in a single node's decision logic (fallback behavior, prompt construction, state updates) without needing a running chatbot, a real LLM, or a real Zammad instance — these tests run fast and deterministically in CI on every push.

**How is the test done:**
Each test follows the Arrange-Act-Assert pattern: the relevant LLM object, `retrieve_relevant_entries`, and/or `ticket_service.<method>` are mocked via `unittest.mock.patch` on their `backend.graph.nodes` module-level reference (e.g. `@patch("backend.graph.nodes.category_llm")`, `@patch("backend.graph.nodes.llm")`, `@patch("backend.graph.nodes.retrieve_relevant_entries")`), mock return values are set up to a decision object built by a small factory helper (e.g. `category_decision(...)`, `intent_decision(...)`, `additional_info_decision(...)`), the node function is called directly with a hand-built state dict, and the returned state-update dict (and, where relevant, the mocked call arguments) are asserted against the expected outcome. `test_ticket_category.py` and `test_intent_classification.py` also assert on prompt content (`mock_llm.invoke.call_args[0][0][0].content`) to guard against silently broken prompt templates.

Note: `ask_for_additional_info` builds its structured-output LLM inline (`llm.with_structured_output(AdditionalInfoDecision)`) rather than using a module-level singleton like `category_llm`/`intent_llm`/`structured_llm`. Its tests therefore patch `backend.graph.nodes.llm` and configure `mock_llm.with_structured_output.return_value.invoke.return_value` instead of patching a dedicated LLM object directly.

**What each individual test checks (expected output):**
* `test_intent_classification.py`
  * `test_returns_valid_intent_from_llm` — a mocked `"tutorial"` LLM decision results in `result["intent"] == "tutorial"`.
  * `test_falls_back_to_unclear_on_unknown_intent` — a mocked out-of-schema intent (`"anleitung"`) falls back to `result["intent"] == "unclear"`.
  * `test_prompt_includes_previous_intent_and_conversation` — the prompt sent to the LLM contains both the previous intent (`"tutorial"`) and the latest user message.
  * `test_email_is_extracted_when_missing` — an email found in the user message is written to `result["user_email"]`.
  * `test_existing_email_is_not_overwritten` — if `user_email` is already set, the key is absent from the returned state update (i.e. not overwritten).
  * `test_expected_intents_are_defined` — `INTENTS == ["tutorial", "problem", "unclear", "solved"]`.
* `test_ticket_category.py`
  * `test_returns_valid_category_from_llm` — a mocked `"Incident"` decision results in `classify_ticket_category(...) == "Incident"`.
  * `test_falls_back_when_llm_returns_unknown_category` — a mocked out-of-schema category (`"Netzwerk"`) falls back to `"Service Request"`.
  * `test_prompt_includes_full_conversation_context` — the prompt contains all prior user messages, not just the latest one.
  * `test_moodle_login_classified_as_incident` / `test_wlan_classified_as_incident` — representative Moodle-login and WLAN cases both classify as `"Incident"`.
  * `test_extract_information_does_not_set_category` — `extract_information` returns the extracted `issue_description` but never sets a `"category"` key.
  * `test_extract_prompt_does_not_include_category_rules` — the extraction prompt contains neither `"4. Kategorie"` nor `"ITSM-Ticket-Typ"`.
  * `test_classify_ticket_node_sets_category` — the `classify_ticket` node sets `state_update["category"]` from the (mocked) classifier and calls it exactly once.
  * `test_resolve_ticket_category_reuses_existing_value` — if `state["category"]` is already set, `_resolve_ticket_category` returns it unchanged without calling the classifier.
  * `test_finish_ticket_reuses_category_without_reclassifying` — `finish_ticket` reuses an existing `category` (no reclassification call) and passes it through unchanged into the Zammad ticket payload.
  * `test_expected_categories_are_defined` — `TICKET_CATEGORIES == ["Incident", "Service Request", "Change", "Problem", "Complaint"]`.
  * `test_regression_fixtures_load_from_old_tickets` — `rag/old_tickets.json` loads exactly 56 valid cases.
  * `test_holdout_fixtures_load` — `rag/category_holdout_tests.json` loads at least 5 valid cases.
* `test_ticket_category_live.py` (only runs with `RUN_LLM_CATEGORY_TESTS=1`)
  * `test_live_wlan_is_incident` / `test_live_moodle_login_is_incident` / `test_live_login_without_keywords_is_incident` — the real LLM classifies each representative case as `"Incident"`.
  * `test_regression_cases_from_old_tickets` — real-LLM accuracy across all regression cases is at least `CATEGORY_REGRESSION_MIN_ACCURACY` (default 90%).
  * `test_holdout_cases_generalization` — real-LLM accuracy across all unseen holdout cases is at least `CATEGORY_HOLDOUT_MIN_ACCURACY` (default 80%).
* `test_ask_for_additional_info.py`
  * `test_skips_follow_up_when_rag_has_no_matches` — no FAQ/ticket matches → returns `{"needs_additional_info": True}` and the LLM is never invoked.
  * `test_marks_complete_when_two_additional_infos_already_collected` — 2 or more `additional_info` entries already collected → returns `{"needs_additional_info": True}` regardless of the LLM decision, and Zammad is not contacted.
  * `test_marks_complete_after_max_attempts` — `additional_info_attempts >= 3` → returns `{"needs_additional_info": True}`, Zammad is not contacted.
  * `test_marks_complete_when_llm_decides_no_more_info_needed` — the LLM decision has `needs_additional_info=True` → returns `{"needs_additional_info": True}`, Zammad is not contacted.
  * `test_asks_follow_up_question_and_appends_to_ticket` — the LLM decision has `needs_additional_info=False` with a follow-up question → returns `needs_additional_info: False`, increments `additional_info_attempts`, includes the question in the returned `AIMessage`, and appends exactly one internal note to the Zammad ticket with the correct `ticket_id`/`sender`/`internal` values.
* `test_give_solutions.py`
  * `test_returns_early_message_when_issue_description_empty` — empty `issue_description` → returns the fixed "Keine ausreichende Anfrage..." message with `solutions: []`, and RAG is never queried.
  * `test_returns_error_message_when_rag_raises` — RAG retrieval raises an exception → returns the fixed "Fehler bei der Suche..." message with `solutions: []`.
  * `test_builds_solutions_from_two_faq_matches` — 2 FAQ matches → `solutions` contains exactly those two `{"title": "FAQ: <id>", ...}` entries.
  * `test_fills_up_with_ticket_matches_when_fewer_than_two_faq_matches` — 1 FAQ match + a ticket match → `solutions` is filled up to 2 with a `{"title": "Ähnliches Ticket (<category>)", ...}` entry.
  * `test_appends_summary_to_ticket_with_correct_payload` — the LLM-generated summary is appended to the Zammad ticket with the correct `ticket_id`/`sender`/`internal` values.
  * `test_continues_when_ticket_append_fails` — the Zammad append call raises an exception → the function does not propagate it and still returns the `messages`/`solutions` state update.

**When is the test passed:**
All assertions in every test case must pass. `test_ticket_category_live.py`'s classes are skipped unless `RUN_LLM_CATEGORY_TESTS=1` is set — without it, the job still counts as passed, just with those cases reported as skipped.

**Additional notes:**
* The four mocked graph-node files (`test_intent_classification.py`, `test_ticket_category.py`, `test_ask_for_additional_info.py`, `test_give_solutions.py`) plus the frontend Q&A back-navigation suite (`test_question_back_navigation.py`) run together in one CI job (`run_test_graph_nodes`, stage `before_deepeval`) via a single `pytest` invocation on every push — the node tests share the same mocking approach and never touch a real LLM; the back-navigation tests are pure helpers with no Streamlit runtime.
* `test_ticket_category_live.py` is **not** part of that job — it needs `RUN_LLM_CATEGORY_TESTS=1` to actually execute anything (without it, every test class is skipped), and it burns real SAIA quota (56 regression + 5+ holdout + 3 spot-check calls). It instead has its own CI job, `run_test_ticket_category_live` (stage `deepeval`), gated the same way as `run_deepeval_tests`: manual and `allow_failure: true` on merge-request pipelines, so it only runs when someone explicitly triggers it (e.g. after changing the classification prompt/logic), not on every push.
* `test_ticket_category.py`'s `TicketCategoryConstantsTests` and `test_ticket_category_live.py`'s regression/holdout suites load fixtures from `backend/rag/old_tickets.json` and `backend/rag/category_holdout_tests.json` via the shared helper module `category_test_support.py`. Regression/holdout accuracy thresholds are configurable via `CATEGORY_REGRESSION_MIN_ACCURACY` (default 0.90), `CATEGORY_HOLDOUT_MIN_ACCURACY` (default 0.80), and an optional `CATEGORY_REGRESSION_LIMIT` cap.
* To run the live LLM suite locally: `RUN_LLM_CATEGORY_TESTS=1 pytest tests/test_ticket_category_live.py -v -s` (uses real SAIA/Ollama quota — don't run casually, see the SAIA request cap in the main `CLAUDE.md`).

### RAG retrieval
**What does this test do:**
This script checks whether `retrieve_relevant_entries()` (`backend/rag/retrieve_info.py`) still finds the correct FAQ and past-ticket matches for four fixed IT-support queries — VPN, WLAN/eduroam, Windows license, and one irrelevant control query ("booking a holiday") — evaluated against the same similarity thresholds used in production.

**Why is this test done:**
To catch regressions in the RAG retrieval module — e.g. shifted thresholds, a swapped embedding/reranker model, a broken query-encoding step — that would silently degrade solution quality, and to flag when the FAQ/ticket knowledge base has drifted away from covering these core topics.

**How is the test done:**
All four queries are retrieved once via a shared `pytest` fixture and reused across the individual test functions. For the three queries with known-good matches (VPN, WLAN, Windows license), each test asserts that a FAQ match is returned, that it reaches the tier-1 similarity threshold (`FAQ_TIER_1_THRESHOLD`), and that at least one ticket match is returned (ticket matches are already filtered by `TICKET_SIMILARITY_THRESHOLD` inside `retrieve_relevant_entries()`). For the irrelevant control query, the test asserts the opposite: no FAQ match reaches the tier-1 threshold and no ticket match is returned at all.

**When is the test passed:**
The test is passed if, for the three relevant queries, a FAQ match reaches `FAQ_TIER_1_THRESHOLD` and at least one ticket match is returned, and if, for the irrelevant query, no FAQ match reaches that threshold and no ticket match is returned.

**Additional notes:**
The thresholds are imported directly from `backend/rag/retrieve_info.py` instead of being duplicated in the test, so the test always evaluates against the actual production values rather than a possibly stale copy. This test must be run from the project root with `PYTHONPATH=.` set (see exception above), since it imports `backend.rag.retrieve_info` via its full module path.

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
For each model in `MODEL_CONFIGS`, the chatbot is patched to use that model. Five realistic IT-support conversation scenarios are simulated, each consisting of up to 3 user messages:
* A student whose university WLAN is not showing up in the network list
* A student whose university account is locked
* A student who forgot their password and cannot receive a reset link
* A student who cannot connect to the university VPN from home office
* A university employee who cannot activate their Microsoft Office campus licence

Each scenario produces a `ConversationalTestCase` which is then evaluated by the judge model (Gemma-4-31B) using the `ConversationCompletenessMetric`. Results are collected and written to `benchmark_results.json`. All LLM calls are automatically traced in LangSmith via the LangChain integration.

**When is the test passed:**
The test always passes (it is a benchmarking script, not a pass/fail test). Results are stored for manual analysis.

**Evaluated models and findings:**

**deepseek-r1-distill-llama-70b** (70B):
- Score (5-scenario run): 1.00 (VPN scenario), 0.67 (Office scenario); scenarios 1–3 could not be evaluated due to API server errors (InternalServerError)
- Strength: Strong reasoning capabilities and detailed step-by-step solutions. Produces the most structured, helpful responses for technical IT problems.
- Weakness: Writes long reasoning chains inside `<think>...</think>` tags before the actual answer, which required a custom wrapper class (`ThinkStripChatOpenAI`) to strip these tags before JSON parsing. Frequently hits API rate limits and server errors under load.

**apertus-70b-instruct-2509** (70B):
- Score (preliminary 2-scenario run): 0.83 (WLAN scenario), 0.67 (Account scenario)
- Score (5-scenario run): could not be evaluated — HTTP 500 error during evaluation phase
- Strength: Answers directly and concisely without excessive follow-up questions. Best overall completeness scores in completed evaluations.
- Weakness: Unstable under high server load — when used as chatbot model while the judge model runs simultaneously, it produced `RetryError` and HTTP 500 responses. Cannot serve as both chatbot and judge at the same time.

**gemma-4-31b-it** (31B):
- Score (preliminary 2-scenario run): 0.00 (WLAN scenario), 0.33 (Account scenario)
- Score (5-scenario run): could not be evaluated — API rate limit exceeded (429)
- Strength: Stable and compatible with the system; no technical parsing errors or JSON format issues.
- Weakness: Tends to ask multiple follow-up questions before offering any solution, causing conversations to end before a solution is reached. Low completeness scores as a result.

**meta-llama-3.1-8b-instruct** (8B – small model):
- Score (5-scenario run): could not be evaluated — API rate limit exceeded (429)
- Strength: Smallest and fastest model tested; lowest server demand of all evaluated models. Suitable as a lightweight fallback.
- Weakness: Returns unexpected JSON structures for some extraction steps (`needs_additional_info` field sometimes missing or misformatted), which caused parsing errors. Model quality is noticeably lower than the 70B models.

**Additional notes:**
* The LLM Model Benchmark is only available if for the feature branch a merge request already exists. Additionally, the benchmark is optional (i.e. it does not contribute to the pass/fail of the entire pipeline) and has to be activated manually. For more info about manual and optional CI tests, refer to https://docs.gitlab.com/ci/jobs/job_control/#create-a-job-that-must-be-run-manually in the Gitlab documentation.
This change was done to give the option to do these tests only when our application's LLM generation was changed substantially and there only once, which conserves API credits. To start the test in the CI, do these steps:
  1. Go to Gitlab
  2. Click Build > Pipelines
  3. Find the most recent pipeline that is tagged with "Merge Request" and the corresponding merge request number
  4. Click on the "Play" button

* All models are accessed via the GWDG/SAIA API (`https://chat-ai.academiccloud.de/v1/`) which is OpenAI-compatible. The `demand` field in the API response indicates current server load (0 = free, higher = busy).
* The judge model is **Gemma-4-31B** (`gemma-4-31b-it`). It was chosen to avoid server overload — using the same model as both chatbot and judge simultaneously caused `RetryError` for Apertus.
* DeepSeek's `<think>...</think>` reasoning tags are stripped automatically by the `ThinkStripChatOpenAI` wrapper class before responses are parsed.
* Some models (especially Gemma and Llama) require up to 3 conversation turns before offering a solution. Scenarios therefore consist of 3 messages so that conservative models have enough turns to complete the conversation.
* Rate limits (`429`) occur after many API calls in one session. Wait for the rate limit to reset before re-running the benchmark.
* The benchmark must be run from the **project root** (not from the `tests/` folder): `PYTHONPATH=. pytest tests/test_llm_benchmark.py -v -s`
* * In the CI/CD pipeline, view the console output to view the results after the test has finished.
* If the test hangs for a long time, it is most likely due to server overload on SAIA's side
* To add more models, add entries into the `MODEL_CONFIGS` dictionary in `test_llm_benchmark.py` in the following format: `"model_name_that_appears_on_console:":"saia_internal_model_name"`, e. g. `"llama-3.1-8b": "meta-llama-3.1-8b-instruct",`.