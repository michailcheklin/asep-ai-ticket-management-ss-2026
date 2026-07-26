from langgraph.graph import END
from .state import ChatbotState



def route_based_on_state(state: ChatbotState):
    """
    Determine the next workflow node based on the missing
    required information.
    """
    if state.get("channel") == "email" and state.get("issue_description") and state.get("user_email"):
        return "email_retrieve_solutions_node"
    if not state.get("user_email"):
        print("[ERROR route_based_on_state] user_email is missing from the state — "
              "a conversation must not start without a login session.")
        
    if not state.get("issue_description"):
        print(f"[DEBUG]: Attempts for ask_for_issue node: {state.get('ask_issue_attempts')}")
        if state.get("ask_issue_attempts", 0) >= 3:
            return "finish_ai_created_ticket_node"
        else:
            return "ask_issue_node"

    return "classify_intent_node"

def route_after_intent(state: ChatbotState):
    """
    Determine the next workflow node based on the intent of the user.
    """

    intent = state.get("intent")

    if intent == "solved" and state.get("tutorial_attempts", 0) > 0:
        return "classify_ticket_node"

    if intent == "tutorial" and state.get("tutorial_attempts", 0) > 0:
        if state.get("tutorial_attempts", 0) <= 3:
            return "give_tutorial_node"
        else:
            return "classify_ticket_node"

    if intent == "tutorial" or intent == "problem":
        return "ask_for_additional_info"

    return "ask_intent_node"

def route_after_evaluator(state: ChatbotState):
    """
    Determine whether enough information has been collected.

    If all required information is available, search for suitable
    solutions. Otherwise, end the current workflow so the user can
    provide additional information.
    """
    if not state.get("needs_additional_info"):
        intent = state.get("intent")

        if intent == "tutorial":
            if state.get("tutorial_attempts", 0) <= 3:
                return "give_tutorial_node"
            else:
                return "classify_ticket_node"
        else:
            return "classify_ticket_node"
    else:
        return END

def route_after_solutions(state: ChatbotState):
    """
    Determine the next step after searching for solutions.

    If solutions were found, wait for user feedback unless the
    conversation is already complete. If no solutions were found,
    create a ticket immediately.

    :param state: Current chatbot state
    :return: Next workflow node
    """
    if state.get("solutions"):
        if state.get("is_complete"):
            return "finish_ai_created_ticket_node"
        else:
            return END
    else:
        return "finish_ai_created_ticket_node"

def route_after_classification(state: ChatbotState):
    """
    Routes the user to a full tutorial or a quick solution and ticket creation
    """
    if state.get("intent") == "solved":
        return "finish_tutorial_node"
    return "escalate_incidents_node"

