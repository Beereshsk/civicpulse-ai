"""Validated summary enrichment with deterministic, credential-free fallback."""
from __future__ import annotations

import os

from .categorization import CATEGORIES
from .llm import generate_json, is_configured


def local_summary(description: str, limit_words: int = 22) -> str:
    words = str(description or "").strip().split()
    if not words:
        return "No description supplied; operator should request more detail."
    return " ".join(words[:limit_words]) + ("..." if len(words) > limit_words else "")


def validate_enrichment(value: object) -> dict:
    if not isinstance(value, dict):
        raise ValueError("Model output must be an object")
    summary = value.get("summary")
    category = value.get("suggested_category")
    uncertainty = value.get("uncertainty", "Model suggestions require operator review.")
    if not isinstance(summary, str) or not summary.strip() or len(summary.strip()) > 240:
        raise ValueError("Model summary is empty or too long")
    if category not in CATEGORIES:
        raise ValueError("Model category is not in the supported category list")
    if not isinstance(uncertainty, str) or len(uncertainty) > 320:
        raise ValueError("Model uncertainty field is invalid")
    return {"summary": summary.strip(), "suggested_category": category,
            "uncertainty": uncertainty.strip() or "Model suggestions require operator review."}


def summarize_complaint(description: str, supplied_category: str, rule_category: str, *, rule_confidence: float = .48, model_call=None) -> dict:
    text = str(description or "").strip()
    fallback = {"summary": local_summary(text), "suggested_category": rule_category,
                "uncertainty": "Rule-based suggestion; verify the description and location with the reporter.",
                "confidence": .25 if not text else rule_confidence, "engine": "Deterministic local summary"}
    if not text:
        fallback["uncertainty"] = "Description is missing; request more information before routing."
        return fallback
    if model_call is False or (model_call is None and not is_configured()):
        return fallback
    call = model_call if callable(model_call) else generate_json
    system = ("Summarize a civic complaint in plain language. Return JSON with summary, suggested_category, "
              "uncertainty. Do not add facts, locations, causes, or impacts not present in the complaint. "
              f"suggested_category must be exactly one of: {', '.join(CATEGORIES)}.")
    prompt = f"Citizen-selected category: {supplied_category}\nRule suggestion: {rule_category}\nComplaint: {text[:2000]}"
    try:
        valid = validate_enrichment(call(system, prompt))
        if model_call is None:
            engine = f"Configured LLM summary ({os.environ.get('CIVICPULSE_LLM_MODEL', 'configured model')})"
        else:
            engine = "Injected model-call summary (test adapter)"
        return {**valid, "confidence": .8, "engine": engine}
    except Exception:
        # Never persist malformed model output or represent a failed call as successful.
        fallback["uncertainty"] = "Configured model unavailable or malformed; deterministic fallback used. Verify with the reporter."
        fallback["engine"] = "Deterministic fallback (LLM unavailable or output rejected)"
        return fallback
