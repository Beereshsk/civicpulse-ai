"""Composition layer used by report creation and seeded demo records."""
from __future__ import annotations

from typing import Mapping

from .categorization import categorize_complaint
from .departments import recommend_department
from .duplicates import detect_duplicates
from .models import Complaint
from .priority import SAFETY_TERMS, asserted_terms, score_priority
from .summarization import summarize_complaint


def process_complaint(record: Mapping, existing_reports: list[Mapping] | None = None, *,
                      created_at: str | None = None, model_call=None, use_llm: bool | None = None) -> dict:
    """Analyze a complaint; priority and duplicate scores always remain code-derived."""
    complaint = Complaint.from_record(record)
    text = complaint.description
    supplied_category = str(record.get("category") or "Other")
    category = categorize_complaint(text, supplied_category)
    enrichment_call = False if use_llm is False else model_call
    enrichment = summarize_complaint(text, supplied_category, category["suggested_category"],
        rule_confidence=category["confidence"], model_call=enrichment_call)
    suggested = enrichment["suggested_category"]
    priority = score_priority(text, created_at or complaint.created_at)
    department = recommend_department(suggested)
    compare_record = {**dict(record), "description": text, "category": supplied_category,
        "suggested_category": suggested, "lat": complaint.lat, "lon": complaint.lon}
    duplicate_matches = detect_duplicates(compare_record, existing_reports or [])
    confidence = enrichment.get("confidence", category["confidence"])
    summary_engine = enrichment["engine"]
    category_method = "configured LLM suggestion" if summary_engine.startswith("Configured LLM") else category["method"]
    engine = (f"{summary_engine}; deterministic application priority, duplicate, and department rules"
              if "LLM" in summary_engine else "Deterministic local rules (no LLM call)")
    urgency = ("Human review recommended now" if priority["safety_review"] else
               "Review soon" if priority["score"] >= 65 else "Routine review")
    return {**priority, "suggested_category": suggested, "confidence": confidence,
        "category_method": category_method, "category_matched_terms": category["matched_terms"],
        "confidence_note": "Uncalibrated signal; use the uncertainty text and original report for review.",
        "summary": enrichment["summary"], "severity": "High" if priority["components"]["severity"] >= 70 else
            "Moderate" if priority["components"]["severity"] >= 45 else "Low",
        "potential_impact": "Potentially affects multiple people" if priority["components"]["impact"] >= 55 else
            "Extent of impact is unclear from the report", "urgency": urgency,
        "department": department["department"], "department_reason": department["reason"],
        "uncertainty": enrichment["uncertainty"], "evidence_terms": asserted_terms(text.lower(), SAFETY_TERMS),
        "duplicates": duplicate_matches, "engine": engine, "summary_engine": summary_engine}
