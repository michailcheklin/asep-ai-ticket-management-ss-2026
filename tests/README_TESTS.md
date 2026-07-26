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

**Exception — LLM conversation benchmark test, LLM off-topic handling test and RAG retrieval test:** These tests must be run from the project root, not from the `tests/` folder, because they import backend modules that require the project root to be on the Python path:
   * LLM conversation benchmark test:
     * On Windows `set PYTHONPATH=. && pytest tests/test_llm_conversation_benchmark.py -v -s`
     * On Mac `PYTHONPATH=. pytest tests/test_llm_conversation_benchmark.py -v -s`
   * LLM off-topic request handling test:
     * On Windows `set PYTHONPATH=. && pytest tests/test_llm_off_topic_reactions.py -v -s`
     * On Mac `PYTHONPATH=. pytest tests/test_llm_off_topic_reactions.py -v -s`
   * RAG retrieval test:
     * On Windows `set PYTHONPATH=. && pytest tests/test_rag_retrieve.py -v -s`
     * On Mac `PYTHONPATH=. pytest tests/test_rag_retrieve.py -v -s`

## What is tested

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
  * `test_prompt_includes_summary_context` — the prompt contains all prior user messages, not just the latest one.
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


### LLM chat conversation Benchmark
**What does this test do:**
This script benchmarks multiple GWDG/SAIA LLMs by running them through realistic IT-support conversation scenarios and evaluating their response quality with four DeepEval metrics. Results are saved to `tests/benchmark_conversation_results.json` and logged to LangSmith.

**Why is this test done:**
To identify which LLM performs best as the chatbot's underlying model for the ZIM ticket management use case, to document the strengths and weaknesses of each evaluated model, and to check the conversations against several independent quality dimensions rather than completeness alone.

**How is the test done:**
For each model in `MODEL_CONFIGS`, the chatbot is patched to use that model. Five realistic IT-support conversation scenarios are simulated, each consisting of up to 3 user messages:
* A student whose university WLAN is not showing up in the network list
* A student whose university account is locked
* A student who forgot their password and cannot receive a reset link
* A student who cannot connect to the university VPN from home office
* A university employee who cannot activate their Microsoft Office campus licence

Each scenario produces a `ConversationalTestCase` which is evaluated by the judge model against all four metrics. Each scenario is evaluated inside its own `try/except` block, so a single slow or timed-out evaluation does not discard the already-computed scores of the other scenarios — a failed scenario is recorded as an `ERROR` entry and the benchmark continues.

**Metrics and thresholds:**

| Metric | Type | Threshold | Passing score means | Threshold justification |
| --- | --- | --- | --- | --- |
| Conversation Completeness | `ConversationCompletenessMetric` (built-in) | 0.5 | The conversation reaches a resolution over the whole dialogue. | Multi-turn completeness is partial-credit by nature; 0.5 marks "more complete than not" and matches DeepEval's default, so a model is not failed for a single unresolved turn. |
| Hallucination Detection | `ConversationalGEval` | 0.7 | Factual/technical claims are consistent and plausible; nothing fabricated. | Set a priori as a quality bar, not fitted to observed scores. Groundedness is high-stakes for an IT-support bot — a wrong instruction is worse than none — so the bar is above the 0.5 completeness bar: the bot must stay factual in the clear majority of turns. |
| Knowledge Retention | `ConversationalGEval` | 0.7 | The bot reuses details the user already gave and does not re-ask. | Re-asking known information is a clear, easily-judged failure; 0.7 demands the bot get this right in the clear majority of turns. |
| Answer Relevancy | `ConversationalGEval` | 0.7 | Each reply addresses the user's current request and stays on topic. | On-topic relevancy should hold almost always; 0.7 flags models that drift, stall, or answer evasively. |

All three `ConversationalGEval` metrics use `evaluation_params=[MultiTurnParams.CONTENT]`, `model=SAIA_JUDGE_MODEL`, `async_mode=False`, and are phrased so that a **high** score = good behaviour.

**Judge model — decision:**
The judge model is **`qwen3.6-35b-a3b`** (configured as `SAIA_JUDGE_MODEL` in `tests/setup.py`). All documented figures were produced under this judge. Several judges were trialled before it, and each rejection is itself part of the selection:
* `gemma-4-31b-it` (31B, the original judge) was too small to reason reliably about the multi-turn `ConversationalGEval` criteria; its verdicts on the same conversation were inconsistent across re-runs, which makes it unsuitable once more than the built-in completeness metric is used.
* `qwen3.5-397b-a17b` was trialled as the strongest available SAIA model, but timed out on essentially every scenario evaluation (~3 min per call, exceeding the client timeout), so the benchmark returned no scores at all. Rejected on latency grounds.
* `qwen3.5-122b-a10b` was trialled next and initially looked viable, but under real SAIA load it too exceeded the timeout on most evaluations. Rejected for the same reason as the 397B model.
* `mistral-medium-3.5-128b` was trialled briefly and completed evaluations, but was set aside in favour of the qwen model to keep the judge in a single family for comparability across all runs.
* `qwen3.6-35b-a3b` (selected) is a mixture-of-experts model with only ~3B active parameters per token, which is why it stays well inside the timeout while still reasoning competently about multi-turn criteria. A full five-scenario evaluation completes in well under ten minutes, which is what finally made complete runs possible at all.

**Judge and metric caveats:**
* The judge only sees the conversation turns (`MultiTurnParams.CONTENT`), not the RAG/FAQ context that grounded the bot's answers, so correctly-grounded facts can be flagged as "unsupported". Hallucination Detection scores should be read as "the judge could not verify these claims from the visible turns alone", not as proof the model invents facts — and used for relative comparison between models, not as an absolute groundedness measure.
* An LLM judge has known biases (self-preference toward its own model family, verbosity/position bias). To keep this controlled, the judge is deliberately taken from a model family that is not itself a chatbot candidate: no evaluated model ever judges itself or a competitor. All figures documented below come from runs under the same judge, so scores are comparable with each other — but they are not absolute quality measures and should not be compared against scores produced under a different judge.

**Evaluated models and findings:**

Six models were benchmarked. Each entry below is backed by exactly one archived run in `tests/logs/`; the log name is given per model. All runs used the judge `qwen3.6-35b-a3b` and the same five scenarios, so the figures are directly comparable.

| Model | Size | Completeness | Hallucination | Knowledge Retention | Answer Relevancy | Overall | Scenarios scored |
| --- | --- | --- | --- | --- | --- | --- | --- |
| gpt-oss-120b | 120B | 0.93 | 0.98 | 0.70 | 0.96 | **0.89** | 5 / 5 |
| glm-4.7 | — | 0.80 | 0.98 | 0.64 | 0.84 | **0.82** | 5 / 5 |
| deepseek-r1-70b | 70B | 0.87 | 0.68 | 0.58 | 0.64 | **0.69** | 5 / 5 |
| llama-3.1-8b | 8B | 0.60 | 0.62 | 0.46 | 0.50 | **0.55** | 5 / 5 |
| gemma-4-31b-it | 31B | 0.33 | 0.42 | 0.48 | 0.42 | **0.41** | 5 / 5 |
| apertus-70b | 70B | 0.00 | 0.20 | 0.03 | 0.17 | **0.10** | 3 / 5 |

Per-scenario scores are given in the order Completeness / Hallucination / Knowledge Retention / Answer Relevancy (thresholds 0.5 / 0.7 / 0.7 / 0.7).

**gpt-oss-120b** (120B — current production chatbot model). Evidence: `tests/logs/gpt-oss-120b_2026-07-25_10-39.log`, runtime 8:28 min.
- Scenario 1 (WLAN not in network list): 1.00 / 1.00 / 1.00 / 1.00
- Scenario 2 (university account locked): 0.67 / 1.00 / 0.90 / 1.00
- Scenario 3 (forgot password, no reset link): 1.00 / 1.00 / 0.10 / 0.80
- Scenario 4 (cannot connect to VPN): 1.00 / 1.00 / 1.00 / 1.00
- Scenario 5 (Office campus licence): 1.00 / 0.90 / 0.50 / 1.00
- Strength: the best model in the field on every metric. Perfect scores in three of five scenarios, and the only model with no factual complaints from the judge (Hallucination 0.98 average). Answers are structured, cite the correct ZIM URLs and hotline details, and stay on topic throughout.
- Weakness: Knowledge Retention is its only metric below threshold (0.70, exactly at the bar). It is caused by two scenarios — in the password scenario (0.10) the bot re-asks for the username the user had already given and restarts the dialogue, and in the Office scenario (0.50) it partially repeats its own earlier questions.
- Conclusion: confirmed as the production model. No candidate came close enough to justify a switch.

**glm-4.7** — Evidence: `tests/logs/glm-4.7_2026-07-25_10-00.log`, runtime 6:46 min.
- Scenario 1 (WLAN): 1.00 / 1.00 / 1.00 / 1.00
- Scenario 2 (account locked): 1.00 / 1.00 / 1.00 / 1.00
- Scenario 3 (forgot password): 1.00 / 0.90 / 0.80 / 0.90
- Scenario 4 (VPN): 0.00 / 1.00 / 0.20 / 0.30
- Scenario 5 (Office licence): 1.00 / 1.00 / 0.20 / 1.00
- Strength: the fastest of the large models (6:46 min for a full five-scenario run) and factually the joint-best (Hallucination 0.98). Four of five scenarios pass on Completeness with 1.00, two of them perfectly on all four metrics.
- Weakness: one scenario collapses completely. In the VPN scenario the bot loses the thread and restarts with a generic greeting, which drags Completeness to 0.00 and Answer Relevancy to 0.30. Knowledge Retention is the weakest metric overall (0.64), driven by the same restart pattern in scenarios 4 and 5.
- Note on reproducibility: two identical glm-4.7 runs 17 minutes apart produced materially different per-scenario scores despite `temperature=0.2`. Single-run figures for this model should be treated as indicative rather than exact.
- Conclusion: the strongest alternative to gpt-oss-120b and the recommended fallback, on the condition that the conversation-restart problem is addressed in the graph (see cross-model findings).

**deepseek-r1-70b** (70B) — Evidence: `tests/logs/deepseek-r1-70b_2026-07-25_12-51.log`, runtime 9:08 min.
- Scenario 1 (WLAN): 1.00 / 1.00 / 1.00 / 1.00
- Scenario 2 (account locked): 1.00 / 0.50 / 0.80 / 1.00
- Scenario 3 (forgot password): 0.33 / 0.10 / 0.10 / 0.00
- Scenario 4 (VPN): 1.00 / 1.00 / 1.00 / 1.00
- Scenario 5 (Office licence): 1.00 / 0.80 / 0.00 / 0.20
- Strength: two scenarios (WLAN, VPN) are perfect on all four metrics, and Completeness stays high overall (0.87). Its reasoning-model nature shows in well-argued step-by-step instructions when it stays on track.
- Weakness: strongly inconsistent. The password scenario fails on every metric at once (0.33 / 0.10 / 0.10 / 0.00) — the bot answers a question the user did not ask and never returns to the actual problem. The Office scenario loses all user context (Knowledge Retention 0.00). The `<think>` reasoning tags also require the `ThinkStripChatOpenAI` wrapper; without it the raw reasoning leaks into user-facing answers.
- Conclusion: not recommended. The variance between a perfect scenario and a total failure is too high for a support bot, and the reasoning tags add an extra failure mode.

**llama-3.1-8b** (8B — smallest model, candidate lightweight fallback) — Evidence: `tests/logs/llama-3.1-8b_2026-07-25_09-19.log`, runtime 8:16 min.
- Scenario 1 (WLAN): 1.00 / 1.00 / 1.00 / 1.00
- Scenario 2 (account locked): 1.00 / 0.80 / 1.00 / 1.00
- Scenario 3 (forgot password): 0.00 / 0.20 / 0.10 / 0.00
- Scenario 4 (VPN): 1.00 / 0.90 / 0.20 / 0.50
- Scenario 5 (Office licence): 0.00 / 0.20 / 0.00 / 0.00
- Strength: it handles the two simplest scenarios genuinely well — WLAN is perfect on all four metrics and the account-lockout scenario is close behind. For its size (8B, the smallest and cheapest model tested) that is a respectable result, and it shows the RAG context does most of the work in straightforward cases.
- Weakness: it breaks down as soon as the scenario needs more than one coherent step. Two of five scenarios score 0.00 on Completeness — the bot never reaches a resolution, dumps retrieved content wholesale, and falls back to generic "please contact ZIM support" replies. Structured-output reliability is also a risk: in an earlier run it violated the `IntentDecision` schema (returned a `GESAMTCHATVERLAUF` field instead of `intent`), aborting the conversation build.
- Conclusion: unsuitable as the production model. Defensible only as an emergency fallback where availability matters more than answer quality, and only with additional schema-validation guards on the `classify_intent` / `classify_ticket` nodes.

**gemma-4-31b-it** (31B — the former judge model, tested here as a chatbot candidate) — Evidence: `tests/logs/gemma-4-31b_2026-07-25_11-07.log`, runtime 9:56 min.
- Scenario 1 (WLAN): 1.00 / 0.90 / 1.00 / 1.00
- Scenario 2 (account locked): 0.00 / 0.00 / 0.00 / 0.00
- Scenario 3 (forgot password): 0.67 / 1.00 / 1.00 / 0.90
- Scenario 4 (VPN): 0.00 / 0.00 / 0.20 / 0.10
- Scenario 5 (Office licence): 0.00 / 0.20 / 0.20 / 0.10
- Strength: when it works it works well — the WLAN and password scenarios are among the better results in the whole benchmark, with correct grounding in the given context and Hallucination at 0.90 / 1.00.
- Weakness (disqualifying): in three of five scenarios the model leaks its own system prompt into the user-facing answer instead of answering the user. All four metrics collapse to near-zero in those scenarios because there is no usable reply at all. This is not a judging artefact — the leaked instructions are visible verbatim in the log.
- Conclusion: rejected as a chatbot candidate. A model that exposes its system prompt to end users is not deployable regardless of its quality in the remaining scenarios. Note that this is also the model that was replaced as the *judge*, for a different reason (too inconsistent for multi-turn GEval judging).

**apertus-70b** (70B) — Evidence: `tests/logs/apertus-70b_2026-07-25_11-21.log`, runtime 19:31 min, only 3 of 5 scenarios scored.
- Scenario 2 (account locked): 0.00 / 0.20 / 0.00 / 0.10
- Scenario 3 (forgot password): 0.00 / 0.20 / 0.10 / 0.20
- Scenario 5 (Office licence): 0.00 / 0.20 / 0.00 / 0.20
- Scenarios 1 and 4 (WLAN, VPN): not evaluated — the model itself failed to produce a response during the conversation build, so no test case could be constructed.
- Weakness: the worst result of the benchmark by a wide margin, and the only model that never once reached a resolution (Completeness 0.00 in every scored scenario). It is also by far the slowest — 19:31 min for three scenarios, more than twice the time gpt-oss-120b needed for five. Four separate runs were attempted and none completed all five scenarios.
- Conclusion: rejected. Neither the answer quality nor the latency is acceptable, and it is the only candidate whose failures originate in the model itself rather than in the judge step.

**Cross-model findings:**
* **Knowledge Retention is the weakest metric for every single model**, from 8B to 120B (best: gpt-oss-120b at 0.70, exactly at threshold). The failure is always the same pattern: the bot re-asks for information the user already gave, or restarts the dialogue with a generic greeting mid-conversation. Because the pattern is identical across six models of very different sizes and families, the cause is more likely the intent / additional-info loop in the LangGraph flow than the models themselves. 
**Improving the graph should therefore yield more than switching the model**

**Improving the graph:**
The benchmark results also validate the current graph design: even the smallest model (8B) achieves perfect scores in the simpler scenarios, which shows that the graph's RAG grounding and prompt structure carry most of the answer quality, and three of the four metrics score high across the strong models. The one remaining weakness — Knowledge Retention — appears to be a localized issue rather than an architectural flaw: code inspection of `backend/graph/nodes.py` (`ask_for_additional_info`) found conditions that are consistent with the observed failure pattern and suggest four candidate improvements. These are working hypotheses, not confirmed root causes — other contributing factors (prompt wording, graph routing) cannot be ruled out from the benchmark data alone:
  * Pass the conversation history to the follow-up-question LLM call: the node currently builds its prompt only from `issue_description` and `additional_info` — `state["messages"]` is never included, so the model cannot know what has already been asked and answered. This is the most important fix.
  * Include `student_id` and `user_email` in the BENUTZER-KONTEXT block: both exist in `ChatbotState` but are omitted by `_build_metadata_context`, which is exactly the information the judge flagged as "forgotten" in the logs.
  * Track already-asked follow-up questions in the state (e.g. an `asked_questions` list) and explicitly forbid repeating them in the prompt.
  * Prevent the ticket-intro block from being sent twice: the logs show the "Ich habe gerade ein Support-Ticket erstellt…" message repeated verbatim, i.e. the node fires twice — a state flag such as `ticket_intro_sent` would prevent this.

Whether these changes actually raise the Knowledge Retention scores — and whether they are the primary cause at all — must be validated by a before/after benchmark run before further conclusions are drawn.

* **Run reliability is the limiting factor, not model quality.** The benchmark was started roughly 50 times in total; 19 runs were archived as logs, and only 6 of those produced usable results — plus 2 complete runs documented before this rework, i.e. about 8 usable runs overall. The remaining runs were lost to judge timeouts, `InternalServerError` (500) and rate limits (429) on the SAIA side. That these are server-side and not code-side is shown by the deepseek run at 12:51, which completed all five scenarios with the identical script minutes after an aborted run. Runs in the early morning are markedly more reliable.
* **Results are not deterministic even at `temperature=0.2`.** Two identical glm-4.7 runs 17 minutes apart produced materially different per-scenario scores. Rankings should therefore be read as coarse tiers (gpt-oss and glm clearly ahead; deepseek and llama behind; gemma and apertus rejected), not as exact figures.
* **Model selection:** gpt-oss-120b is confirmed as the production chatbot model, with **glm-4.7 as fallback**. This matches the fallback chain already implemented in `backend/llm/llm.py` (SAIA `openai-gpt-oss-120b` → SAIA `glm-4.7` → local Ollama model): the benchmark confirms glm-4.7 as the right choice for the secondary slot — it is the only other model that completed all five scenarios with a comparable hallucination score, and it is the fastest of the large models.

**When is the test passed:**
The test always passes (it is a benchmarking script, not a pass/fail test). The thresholds above only mark each scenario/metric as PASS or FAIL in the report; results are stored for manual analysis.

**Additional notes:**
* The LLM Model Benchmark is only available once a merge request exists for the feature branch. It is optional (does not contribute to pipeline pass/fail) and must be started manually. To start it in CI: Gitlab → Build > Pipelines → find the most recent pipeline tagged "Merge Request" → click the "Play" button.
* All models are accessed via the GWDG/SAIA API (`https://chat-ai.academiccloud.de/v1/`), which is OpenAI-compatible. The `demand` field in the API response indicates current server load (0 = free, higher = busy).
* DeepSeek's `<think>...</think>` reasoning tags are stripped automatically by the `ThinkStripChatOpenAI` wrapper class before responses are parsed.
* Some models require up to 3 conversation turns before offering a solution. Scenarios therefore consist of 3 messages so that conservative models have enough turns to complete the conversation.
* Rate limits (`429`) can occur after many API calls in one session. Wait for the rate limit to reset before re-running the benchmark.
* The benchmark must be run from the **project root** (not from the `tests/` folder): `PYTHONPATH=. pytest tests/test_llm_conversation_benchmark.py -v -s`
* If the test hangs for a long time, it is most likely due to server overload on SAIA's side, or the one-time HuggingFace download of the RAG embedder model on first run.
* To add more models, add entries to the `MODEL_CONFIGS` dictionary in `test_llm_conversation_benchmark.py` in the format `"model_name_shown_on_console": "saia_internal_model_name"`, e.g. `"llama-3.1-8b": "meta-llama-3.1-8b-instruct",`.

* Benchmark one model at a time. Running several models in one invocation multiplies the exposure to SAIA timeouts, and a failure late in the run costs all preceding models their log.
* Console output is archived per run with `tee`, so every documented score can be traced back to its raw run:
  `PYTHONPATH=. pytest tests/test_llm_conversation_benchmark.py -v -s 2>&1 | tee tests/logs/<model>_$(date +%Y-%m-%d_%H-%M).log`
  **Update the log filename whenever you change `MODEL_CONFIGS`** — two archived runs were misnamed because the filename still carried the previous model's name while `MODEL_CONFIGS` had already been changed.
* `tests/logs/` holds exactly one reference run per evaluated model — the run the figures above are taken from. Incomplete or superseded runs are kept outside the repository and are not part of the documentation.

* Benchmark availability depends heavily on GWDG/SAIA server load. During afternoon/evening hours the judge model frequently returns `InternalServerError` or times out, so only a subset of scenarios gets scored per run (the per-scenario `try/except` records these as ERROR entries and lets the rest complete). Runs in the early morning are markedly more reliable. Results should therefore be accumulated across several runs rather than expected from a single one.

### LLM off-topic reaction test
**What does this test do:**
This script runs multiple GWDG/SAIA LLMs by running them through off-topic requests using DeepEval's `ConversationalGEval` metric with a description of that the bot should politely reject an off-topic request . Results are saved to `tests/off_topic_reactions_results.json` and logged to LangSmith.

**Why is this test done:**
To identify which LLM complies the best to its agent.md file when rejecting off-topic requests

**How is the test done:**
For each model in `MODEL_CONFIGS`, the chatbot is patched to use that model. 3 off-topic messages are sent in separate chats to simulate how the user sends an off-topic message as the first message.

Each scenario produces a `ConversationalTestCase` which is then evaluated by the judge model (qwen3.6-35b-a3b, imported from tests/setup.py) using the `ConversationalGEval`. Results are collected and written to `off_topic_reactions_results.json`. All LLM calls are automatically traced in LangSmith via the LangChain integration.

**When is the test passed:**
The test always passes (it is a benchmarking script, not a pass/fail test). Results are stored for manual analysis.


## How to add more LLM tests
To add another LLM test that simulates a set of sequences of user messages, do the following steps:
1. Add a new Python file in the `tests` folder
2. Define the 2D array of strings called `SCENARIOS` to define the scenarios:
   1. Each separate chat is a sub array in the 2D array
   2. In each subarray each string represents a chat message the user types no matter what the bot responds to
3. Define the models that are tested in a dict called `MODEL_CONFIGS`:
   1. Each key (as string) is the name of the model displayed in the result file 
   2. The value (as string) of each key is the full name of the model acc. to the SAIA API
4. Define an array of DeepEval conversational metrics with the name `METRICS` to be used for evaluation:
   1. Each item is either a `ConversationalGEval` with a custom conversation metric or any of the predefined conversational metric such as `ConversationCompleteness` (for a full list, cf. https://deepeval.com/guides/guides-multi-turn-evaluation-metrics)
   2. For any custom conversational metric you need to provide for the instantiation of a `ConversationalGEval` these arguments:
      1. `name`: The name of the metric as a string - Appears in the result JSON file and in console outputs
      2. `criteria`: A natural language definition of the criteria that DeepEval shall evaluate the conversation against
      3. `evaluation_params`: The parameters the DeepEval evaluation shall take into account. For chat-only tests, `MultiTurnParams.CONTENT` suffices so that only the chat messages are checked
      4. `model=SAIA_JUDGE_MODEL`: Sets the judge model to a SAIA API model defined in `tests/setup.py`. Do not leave that empty, else DeepEval will try to use the API of `openai.com` and not the SAIA API
      5. `async_mode=False` - Ensures the metric evaluates the chat messages sequentially
5. Provide in the `BENCHMARK_FILE_PATH` the filepath of the test result's JSON file which serves as a test artifact
6. In a method where the name starts with `test_` (so Pytest sees the code as a test), write this code:
    ```
    def test_your_name():
        your_name_test = DeepEvalTestTemplate(
            scenarios=SCENARIOS,
            metrics=METRICS,
            configs_of_models_to_test=MODEL_CONFIGS,
            benchmark_file_path=BENCHMARK_FILE_PATH,
        )
        your_name_test.test_benchmark_all_models()
    ```
   The code does these things:
    1. Defines a DeepEval test template object with the message sequences to test, the metrics, the models to evaluate and the file path of the result JSON file
   2. Executes the test
7. In `gitlab-ci.yml` add this code to integrate the new test as an optional and manual merge request pipeline in the CI/CD:
   ```
   run_deepeval_custom_tests:
      stage: deepeval
      # Merge request pipeline
      rules:
        - if: $CI_PIPELINE_SOURCE == "merge_request_event"
          # Making this manual to give the option to run this only once in an MR
          # or not at all in MRs that do not affect the LLM generation
          # rather than on every push from the point onwards an MR was created
          # To give the option, this job shall not block pipelines.
          when: manual
          allow_failure: true
      tags:
        - dind
        - ude-sse
      artifacts:
        paths:
          - tests/deepeval_custom_tests_result_file_name.json
      # Caching the Python dependencies per branch, or otherwise
      # adding dependencies in one branch that cause a conflict
      # would cause conflicts in all other branches
      cache:
        - key: ${CI_COMMIT_REF_SLUG}
          paths:
            - $PIP_CACHE_DIR
            - $VENV_DIR/lib/python*/site-packages/
          policy: pull
        - key: hf-models
          paths:
            - .cache/huggingface/
          policy: pull
      script:
        - python --version
        - pip install --upgrade pip
        - python -m venv $VENV_DIR
        - source $VENV_DIR/bin/activate
        - if [ -f tests/requirements.txt ]; then pip install -r tests/requirements.txt; fi
        - echo "LANGSMITH_TRACING_V2=true" >> .env
        - echo "LANGSMITH_API_KEY=$LANGSMITH_API_KEY" >> .env
        - echo "LANGSMITH_ENDPOINT=https://eu.api.smith.langchain.com" >> .env
        - echo "LANGCHAIN_PROJECT=ai-ticket-benchmark" >> .env
        - echo "SAIA_API_KEY=$SAIA_API_KEY" >> .env
        - echo "USE_SAIA_API=true" >> .env
        - echo "AGENT=ZIM" >> .env
        - echo "ZAMMAD_SERVER_ADDRESS=$ZAMMAD_SERVER_ADDRESS" >> .env
        - PYTHONPATH=. pytest tests/test_deepeval_custom_tests.py -v -s
   ```
    Important notes for the CI file:
   1. Use a descriptive name as the header of the job (here the name would be `run_deepeval_custom_tests`)
   2. Make sure the correct artifact path is selected, where the result JSON is located (here it would be `tests/deepeval_custom_tests_result_file_name.json`)
   3. In the last line after the installation of the requirements and the definition of environments, make sure to write the correct name of the test script (here it would be `pytest tests/test_deepeval_custom_tests.py`.