import logging
from logging import Logger

class BackendLogger:
    """
    Central class for creating loggers with different names,
    e.g. Langgraph, RAG, ... so that in the logging messages
    the logger's name appears. This class also wraps all the logger configuration
    into one object.
    """
    def __init__(self, logger_name):
        """
        Creates a new logger object with the given name
        and configures the logger to write to the console with a defined format
        :param logger_name: The name for the logger to use: For instance if the name is "RAG"
        then the logs start with (time) [LEVEL]: {logger_name}:
        """
        self.logger: Logger = logging.getLogger(logger_name)
        self.logger.setLevel(logging.DEBUG)

        self._logger_handler = logging.StreamHandler()
        self._logger_handler.setLevel(logging.DEBUG)

        self._logger_formatter = logging.Formatter("%(asctime)s: [%(levelname)s]: %(name)s: %(message)s")
        self._logger_handler.setFormatter(self._logger_formatter)

        self.logger.addHandler(self._logger_handler)

    def debug(self, message:str):
        """
        Writes a debug log message with the internal logger object
        With this method one can log with
        backend_logger_instance.debug(message) instead of
        backend_logger_instance.logger.debug(message)
        :param message: The debug message to be logged
        """
        self.logger.debug(message)

    def info(self, message:str):
        """
        Writes an info log message with the internal logger object
        With this method one can log with
        backend_logger_instance.info(message) instead of
        backend_logger_instance.logger.info(message)
        :param message: The info message to be logged
        """
        self.logger.info(message)

    def warning(self, message:str):
        """
        Writes a warning log message with the internal logger object
        With this method one can log with
        backend_logger_instance.warning(message) instead of
        backend_logger_instance.logger.warning(message)
        :param message: The warning message to be logged
        """
        self.logger.warning(message)

    def error(self, message:str):
        """
        Writes an error log message with the internal logger object
        With this method one can log with
        backend_logger_instance.error(message) instead of
        backend_logger_instance.logger.error(message)
        :param message: The error message to be logged
        """
        self.logger.error(message)

    def critical(self, message:str):
        """
        Writes a critical log message with the internal logger object
        With this method one can log with
        backend_logger_instance.critical(message) instead of
        backend_logger_instance.logger.critical(message)
        :param message: The critical message to be logged
        """
        self.logger.critical(message)

    
    