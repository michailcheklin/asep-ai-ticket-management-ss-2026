from typing import Dict, List

from pydantic import BaseModel


class FaqSubmission(BaseModel):
    """
    Request payload for submitting a new FAQ entry via POST /faq.

    Mirrors the FAQ JSON schema consumed by rag_store_faq.flatten_faq_entry
    (context, problem, solution). 'force' is a control flag, not part of the
    stored entry: when true the redundancy check is skipped ("Dennoch anlegen").
    """
    id: str = ""
    context: str = ""
    problem: str = ""
    # list of {"faq_content": str, "extracted_urls": [...]}
    solution: List[Dict] = []
    force: bool = False
    # When true the entry has already been previewed/approved by the user and is
    # stored as-is (skips redundancy check, polish and title generation).
    confirmed: bool = False
