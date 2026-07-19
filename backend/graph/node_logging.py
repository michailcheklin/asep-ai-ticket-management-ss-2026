from ..services.BackendLoggingService import BackendLogger

langgraph_logger = BackendLogger("Langgraph")


def log_node_entry(node_name:str, state):
    """
    Whenever a node is entered, a log will be written with the name of the node that was entered,
    along with the state and time at entry. To equip new nodes with logging, call this method
    at the beginning of the node function with the node's name and state.
    :param node_name: The name of the node that was entered
    :param state: The state that the node had when entered
    """
    langgraph_logger.debug(f"Entered {node_name}")
    langgraph_logger.debug(f"Current state:\n{state}")

    metadata_keys = ("display_name", "role", "faculty", "device", "os_name")
    metadata = {k: state.get(k, "") for k in metadata_keys if state.get(k)}
    if metadata:
        langgraph_logger.debug(f"User metadata: {metadata}")


def truncate_long_strings_in_dicts_for_logging(obj, max_length=200):
    """
    For logging:
    Truncates recursively in a dict all strings to 200 characters and
    indicates the truncation with "..."
    :param obj: The dictionary to truncate
    :param max_length: The maximum length of a string before being truncated
    :return:
    """
    if isinstance(obj, str):
        return obj[:max_length] + "..." if len(obj) > max_length else obj
    elif isinstance(obj, dict):
        return {k: truncate_long_strings_in_dicts_for_logging(v, max_length) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [truncate_long_strings_in_dicts_for_logging(item, max_length) for item in obj]
    else:
        return obj

def visit(node_name: str) -> dict:
    """
    Return fragment for graph nodes: registers the node in the
    visited_nodes path. Usage: return {**visit("give_tutorial_node"), ...}
    """
    return {"visited_nodes": [node_name]}