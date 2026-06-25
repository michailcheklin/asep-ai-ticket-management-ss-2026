# Test environment

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