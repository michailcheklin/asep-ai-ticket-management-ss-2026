import logging

langgraph_logger = logging.getLogger("Langgraph")
langgraph_logger.setLevel(logging.DEBUG)

langgraph_logger_handler = logging.StreamHandler()
langgraph_logger_handler.setLevel(logging.DEBUG)

langgraph_logger_formatter = logging.Formatter("%(asctime)s: [%(name)s] [%(levelname)s]: %(message)s")
langgraph_logger_handler.setFormatter(langgraph_logger_formatter)

langgraph_logger.addHandler(langgraph_logger_handler)


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

