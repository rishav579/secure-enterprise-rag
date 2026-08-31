"""Generation evaluation metrics: Citation Precision, Provenance, and Refusal Accuracy."""

import re
from typing import List, Set


def citation_precision(cited_ids: List[str], server_supplied_ids: Set[str]) -> float:
    """Fraction of citations made by model that exist in the server-supplied context."""
    if not cited_ids:
        return 1.0  # No citations claimed

    valid_count = sum(1 for cid in cited_ids if cid in server_supplied_ids)
    return valid_count / len(cited_ids)


def citation_provenance_intact(cited_ids: List[str], server_supplied_ids: Set[str]) -> bool:
    """Boolean assertion: True if and only if 100% of cited IDs come from server context."""
    if not cited_ids:
        return True
    return all(cid in server_supplied_ids for cid in cited_ids)


def refusal_accuracy(is_refusal: bool, expected_refusal: bool) -> bool:
    """True if model decision correctly matches ground truth refusal expectation."""
    return is_refusal == expected_refusal


def answer_contains_prohibited_terms(answer: str, prohibited_terms: List[str]) -> bool:
    """Returns True if any prohibited term is detected in answer."""
    answer_lower = answer.lower()
    return any(term.lower() in answer_lower for term in prohibited_terms)


def answer_contains_expected_facts(answer: str, expected_fact_phrases: List[str]) -> float:
    """Fraction of expected factual phrases present in the answer."""
    if not expected_fact_phrases:
        return 1.0

    answer_lower = answer.lower()
    hits = sum(1 for phrase in expected_fact_phrases if phrase.lower() in answer_lower)
    return hits / len(expected_fact_phrases)
