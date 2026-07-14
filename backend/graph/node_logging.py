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
    langgraph_logger.logger.debug(f"Entered {node_name}")
    langgraph_logger.logger.debug(f"Current state:\n{state}")

