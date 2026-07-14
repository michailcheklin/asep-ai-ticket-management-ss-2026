import logging
from logging import Logger

class BackendLogger:
    """
    Central class for creating loggers with different names,
    e.g. Langgraph, RAG, ... so that in the logging messages
    the logger's name appears
    """
    def __init__(self, logger_name):
        self.logger: Logger = logging.getLogger(logger_name)
        self.logger.setLevel(logging.DEBUG)

        self._logger_handler = logging.StreamHandler()
        self._logger_handler.setLevel(logging.DEBUG)

        self._logger_formatter = logging.Formatter("%(asctime)s: [%(levelname)s]: %(name)s: %(message)s")
        self._logger_handler.setFormatter(self._logger_formatter)

        self.logger.addHandler(self._logger_handler)



    
    