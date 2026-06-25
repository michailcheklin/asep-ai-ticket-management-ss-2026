from datetime import datetime

def log_node_entry(node_name:str, state):
    """
    Whenever a node is entered, a log will be written with the name of the node that was entered,
    along with the state and time at entry. To equip new nodes with logging, call this method
    at the beginning of the node function with the node's name and state.
    :param node_name: The name of the node that was entered
    :param state: The state that the node had when entered
    """
    print(f"{datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]} Entered node {node_name}")
    print(f"Current state: {state}")

