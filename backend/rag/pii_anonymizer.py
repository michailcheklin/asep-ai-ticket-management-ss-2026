"""
PII anonymization for ticket RAG storage.

Loads Piiranha (structured PII) + flair-DE (German person names) ONCE at
module import time — mirroring the eager-load pattern used for the RAG
embedders/re-ranker (see retrieve_info.py's startup block). Import this
module (directly or transitively via rag_store_tickets.py) during backend
startup so the models are warm before the first ticket-closed webhook
arrives.

Piiranha for structured PII (emails, phone numbers, IBANs, etc.) + flair-DE
for person names (avoids Piiranha's subword fragmentation issue on German
names), followed by a regex safety net for structured identifiers models
tend to miss (matriculation numbers, IPs, MACs, IBANs, etc.).

Public API:
    anonymize_ticket_text(text)
        -> (anonymized_text, label_counts)

    anonymize_ticket_fields(full_conversation, messages, ticket_id=None)
        -> (anonymized_full_conversation, anonymized_messages)
"""

from __future__ import annotations

import logging
import re

import torch
from flair.data import Sentence
from flair.models import SequenceTagger
from transformers import AutoModelForTokenClassification, AutoTokenizer

# ----------------------------------------------------------------------
# Logging — kept quiet/compact on purpose (see _log_anonymization_summary)
# ----------------------------------------------------------------------
anon_logger = logging.getLogger("pii_anonymizer")
if not anon_logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(message)s"))
    anon_logger.addHandler(_handler)
anon_logger.setLevel(logging.INFO)
anon_logger.propagate = False

# ----------------------------------------------------------------------
# Tunable parameters
# ----------------------------------------------------------------------
SCORE_THRESHOLD = 0.5
MIN_WORD_LABEL_AGREEMENT = 0.5
MAX_MERGE_GAP = 1
MASK_FORMAT = "[{label}]"

ENTITIES_TO_MASK = {
    "FIRSTNAME", "LASTNAME", "MIDDLENAME", "USERNAME", "PASSWORD",
    "EMAIL", "PHONENUMBER", "PHONEIMEI", "IP", "IPV4", "IPV6", "MAC",
    "STREETADDRESS", "ZIPCODE", "CREDITCARDNUMBER", "CREDITCARDCVV",
    "IBAN", "BIC", "ACCOUNTNUMBER", "DOB", "DATE", "SSN",
}
NAME_LABELS = {"FIRSTNAME", "LASTNAME", "MIDDLENAME"}
STRUCTURED_ENTITIES_TO_MASK = ENTITIES_TO_MASK - NAME_LABELS

PIIRANHA_MODEL_NAME = "iiiorg/piiranha-v1-detect-personal-information"
FLAIR_MODEL_NAME = "flair/ner-german-large"

PIIRANHA_LABEL_MAP = {
    "GIVENNAME": "FIRSTNAME",
    "SURNAME": "LASTNAME",
    "TELEPHONENUM": "PHONENUMBER",
    "STREET": "STREETADDRESS",
    "SOCIALNUM": "SSN",
    "IDCARDNUM": "SSN",
    "DATEOFBIRTH": "DOB",
}

MATRICULATION_REQUIRE_CONTEXT = False
MATRICULATION_CONTEXT_WINDOW = 30
PHONE_MIN_DIGITS = 6
PHONE_MAX_DIGITS = 13

EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
PHONE_RE = re.compile(r"(?<![\w.])(?:\+49[\s./-]?|0)(?:\d[\s./-]?){5,12}\d(?![\w])")
MATRICULATION_BARE_RE = re.compile(r"(?<!\d)[1-9]\d{6}(?!\d)")
MATRICULATION_CONTEXT_KEYWORDS = re.compile(
    r"(matrikelnummer|matr\.?-?nr\.?|matriculation number|student id|student number)",
    re.IGNORECASE,
)
IPV4_RE = re.compile(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)")
MAC_RE = re.compile(r"(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}")
IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}[ ]?(?:[A-Z0-9]{4}[ ]?){2,7}[A-Z0-9]{1,4}\b")
CREDITCARD_RE = re.compile(r"\b(?:\d[ -]*?){13,16}\b")
DOB_RE = re.compile(r"\b\d{1,2}[./]\d{1,2}[./]\d{2,4}\b")

REGEX_PATTERNS = {
    "EMAIL": EMAIL_RE,
    "IPV4": IPV4_RE,
    "MAC": MAC_RE,
    "IBAN": IBAN_RE,
    "CREDITCARDNUMBER": CREDITCARD_RE,
    "DATE": DOB_RE,
}

WORD_RE = re.compile(r"\S+")


# ----------------------------------------------------------------------
# Model loading — runs ONCE at import time
# ----------------------------------------------------------------------
anon_logger.info("[Anonymizer] Loading Piiranha PII model...")
_piiranha_tokenizer = AutoTokenizer.from_pretrained(PIIRANHA_MODEL_NAME, use_fast=True)
_piiranha_model = AutoModelForTokenClassification.from_pretrained(PIIRANHA_MODEL_NAME).eval()
_piiranha_id2label = _piiranha_model.config.id2label

anon_logger.info("[Anonymizer] Loading flair German NER model (names)...")
_flair_tagger = SequenceTagger.load(FLAIR_MODEL_NAME)

anon_logger.info("[Anonymizer] Ready (variant D: piiranha + flair-DE + regex).\n")


# ----------------------------------------------------------------------
# Shared span-detection utilities
# ----------------------------------------------------------------------
def _clean_label(raw_label: str) -> str:
    return raw_label[2:].upper() if raw_label.startswith(("B-", "I-")) else raw_label.upper()


def _normalize_piiranha_label(raw_label: str) -> str:
    label = _clean_label(raw_label)
    return PIIRANHA_LABEL_MAP.get(label, label)


def _predict_all_tokens(text, tokenizer, model, id2label, label_normalizer):
    encoding = tokenizer(text, return_offsets_mapping=True, return_tensors="pt", truncation=True)
    offset_mapping = encoding.pop("offset_mapping")[0].tolist()
    with torch.no_grad():
        logits = model(**encoding).logits[0]
    probs = torch.softmax(logits, dim=-1)
    scores, pred_ids = probs.max(dim=-1)
    tokens = []
    for (start, end), pred_id, score in zip(offset_mapping, pred_ids.tolist(), scores.tolist()):
        if start == end:
            continue
        tokens.append((start, end, label_normalizer(id2label[pred_id]), score))
    return tokens


def _aggregate_to_words(text, subword_tokens, min_word_agreement=MIN_WORD_LABEL_AGREEMENT):
    words = [(m.start(), m.end()) for m in WORD_RE.finditer(text)]
    result = []
    for w_start, w_end in words:
        overlapping = [t for t in subword_tokens if t[0] < w_end and t[1] > w_start]
        if not overlapping:
            continue
        label_scores = {}
        for _, _, label, score in overlapping:
            label_scores.setdefault(label, []).append(score)
        best_label, best_scores = max(label_scores.items(), key=lambda kv: len(kv[1]))
        agreement = len(best_scores) / len(overlapping)
        if best_label == "O" or agreement < min_word_agreement:
            continue
        result.append((w_start, w_end, best_label, sum(best_scores) / len(best_scores)))
    return result


def _group_words_into_spans(word_tokens, max_merge_gap=MAX_MERGE_GAP):
    spans, current = [], None
    for start, end, label, score in word_tokens:
        if current and current["label"] == label and start <= current["end"] + max_merge_gap:
            current["end"] = end
            current["scores"].append(score)
        else:
            if current:
                spans.append(current)
            current = {"start": start, "end": end, "label": label, "scores": [score]}
    if current:
        spans.append(current)
    return [
        {"start": s["start"], "end": s["end"], "label": s["label"], "score": sum(s["scores"]) / len(s["scores"])}
        for s in spans
    ]


def find_spans_model(
    text,
    tokenizer,
    model,
    id2label,
    label_normalizer,
    entities_to_mask,
    score_threshold=SCORE_THRESHOLD,
    min_word_agreement=MIN_WORD_LABEL_AGREEMENT,
):
    if not text or not text.strip():
        return []
    subword_tokens = _predict_all_tokens(text, tokenizer, model, id2label, label_normalizer)
    word_tokens = _aggregate_to_words(text, subword_tokens, min_word_agreement)
    spans = _group_words_into_spans(word_tokens)
    return [s for s in spans if s["score"] >= score_threshold and s["label"] in entities_to_mask]


def apply_spans(text, spans, mask_format=MASK_FORMAT):
    ordered = sorted(spans, key=lambda s: (s["start"], -(s["end"] - s["start"])))
    filtered, last_end = [], -1
    for s in ordered:
        if s["start"] >= last_end:
            filtered.append(s)
            last_end = s["end"]
    anonymized = text
    for s in sorted(filtered, key=lambda s: s["start"], reverse=True):
        anonymized = anonymized[: s["start"]] + mask_format.format(label=s["label"]) + anonymized[s["end"] :]
    return anonymized, filtered


def find_spans_piiranha(text, entities_to_mask=ENTITIES_TO_MASK):
    return find_spans_model(
        text, _piiranha_tokenizer, _piiranha_model, _piiranha_id2label, _normalize_piiranha_label, entities_to_mask
    )


def find_spans_flair_names(text, name_label="PERSON"):
    if not text or not text.strip():
        return []
    sentence = Sentence(text)
    _flair_tagger.predict(sentence)
    return [
        {"start": e.start_position, "end": e.end_position, "label": name_label, "score": e.score}
        for e in sentence.get_spans("ner")
        if e.tag == "PER"
    ]


# ----------------------------------------------------------------------
# Regex safety net
# ----------------------------------------------------------------------
def _matriculation_matches(text):
    matches = []
    for m in MATRICULATION_BARE_RE.finditer(text):
        if MATRICULATION_REQUIRE_CONTEXT:
            window_start = max(0, m.start() - MATRICULATION_CONTEXT_WINDOW)
            if not MATRICULATION_CONTEXT_KEYWORDS.search(text[window_start : m.start()]):
                continue
        matches.append(m)
    return matches


def _phone_matches(text):
    matches = []
    for m in PHONE_RE.finditer(text):
        digit_count = sum(c.isdigit() for c in m.group())
        if PHONE_MIN_DIGITS <= digit_count <= PHONE_MAX_DIGITS:
            matches.append(m)
    return matches


def anonymize_with_regex(text, mask_format="[{label}]"):
    if not text or not text.strip():
        return text, []
    spans = []
    for label, pattern in REGEX_PATTERNS.items():
        for m in pattern.finditer(text):
            spans.append((m.start(), m.end(), label))
    for m in _matriculation_matches(text):
        spans.append((m.start(), m.end(), "MATRICULATIONNUMBER"))
    for m in _phone_matches(text):
        spans.append((m.start(), m.end(), "PHONENUMBER"))

    spans.sort(key=lambda s: (s[0], -(s[1] - s[0])))
    filtered, last_end = [], -1
    for start, end, label in spans:
        if start >= last_end:
            filtered.append((start, end, label))
            last_end = end

    anonymized, found = text, []
    for start, end, label in sorted(filtered, key=lambda s: s[0], reverse=True):
        found.append({"text": text[start:end], "label": label})
        anonymized = anonymized[:start] + mask_format.format(label=label) + anonymized[end:]
    return anonymized, list(reversed(found))


# ----------------------------------------------------------------------
# Anonymize (piiranha structured PII + flair-DE names + regex)
# ----------------------------------------------------------------------
def _anonymize_text_variant_d(text: str) -> tuple[str, dict[str, int]]:
    if not text or not text.strip():
        return text or "", {}

    structured_spans = find_spans_piiranha(text, STRUCTURED_ENTITIES_TO_MASK)
    name_spans = find_spans_flair_names(text)
    intermediate, applied_spans = apply_spans(text, structured_spans + name_spans)
    final_text, regex_found = anonymize_with_regex(intermediate)

    label_counts: dict[str, int] = {}
    for span in applied_spans:
        label_counts[span["label"]] = label_counts.get(span["label"], 0) + 1
    for found in regex_found:
        label_counts[found["label"]] = label_counts.get(found["label"], 0) + 1

    return final_text, label_counts


def _format_label_counts(label_counts: dict[str, int]) -> str:
    if not label_counts:
        return "none"
    parts = [label if count == 1 else f"{label} x{count}" for label, count in sorted(label_counts.items())]
    return ", ".join(parts)


def _log_anonymization_summary(
    ticket_id: str | None,
    fc_counts: dict[str, int],
    msg_counts: dict[str, int],
) -> None:
    """One compact, greppable line per ticket — safe to skip while scanning logs."""
    fc_total = sum(fc_counts.values())
    msg_total = sum(msg_counts.values())
    anon_logger.info(
        "[Anonymizer] %s | full_conversation: %d masked (%s) | messages: %d masked (%s)",
        ticket_id or "unknown",
        fc_total,
        _format_label_counts(fc_counts),
        msg_total,
        _format_label_counts(msg_counts),
    )


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------
def anonymize_ticket_text(text: str) -> tuple[str, dict[str, int]]:
    """Anonymize a single piece of text. Returns (anonymized_text, label_counts)."""
    return _anonymize_text_variant_d(text)


def anonymize_ticket_fields(
    full_conversation: str,
    messages: str,
    ticket_id: str | None = None,
) -> tuple[str, str]:
    """
    Anonymize the two fields written to the ticket RAG store.

    Field names intentionally match rag_store_tickets.py:
      - full_conversation: the text that gets embedded/tokenized
      - messages: the metadata field

    Returns (anonymized_full_conversation, anonymized_messages).
    """
    try:
        anon_full_conversation, fc_counts = _anonymize_text_variant_d(full_conversation or "")
        anon_messages, msg_counts = _anonymize_text_variant_d(messages or "")
        _log_anonymization_summary(ticket_id, fc_counts, msg_counts)
        return anon_full_conversation, anon_messages
    except Exception:
        print("PII FAILURE: The ticket could not be anonymized and was thus not stored in the database.")
        # Depending on organisational preferences, this path can be changed to take different measures:
        # e.g. re-open ticket and add a specific tag in case of failure for the staff to handle.
        # Based on how important it is to store a certain ticket and how much effort staff should put
        # in case of failure here.
        raise