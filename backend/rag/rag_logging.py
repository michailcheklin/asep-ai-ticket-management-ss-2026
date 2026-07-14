import logging

rag_logger = logging.getLogger("RAG")
rag_logger.setLevel(logging.DEBUG)

rag_logger_handler = logging.StreamHandler()
rag_logger_handler.setLevel(logging.DEBUG)

rag_logger_formatter = logging.Formatter("%(asctime)s: [%(name)s] [%(levelname)s]: %(message)s")
rag_logger_handler.setFormatter(rag_logger_formatter)

rag_logger.addHandler(rag_logger_handler)