"""Evidence-first action briefs derived from saved complaint records."""
from __future__ import annotations

import json
from collections import Counter
from typing import Mapping

from .llm import generate_json, is_configured


def build_evidence(reports: list[Mapping]) -> dict:
    """Compute all counts and cited IDs in code before any optional model call."""
    items = list(reports)
    categories = Counter(str(r.get("suggested_category") or r.get("category") or "Other") for r in items)
    departments = Counter(str(r.get("department") or "Unassigned") for r in items)
    high = [r for r in items if r.get("priority_label") in ("Critical", "High")]
    unresolved = [r for r in items if r.get("status") != "Resolved"]
    safety = []
    for r in items:
        raw = r.get("analysis") or {}
        if isinstance(raw, str):
            try: raw = json.loads(raw)
            except (ValueError, TypeError): raw = {}
        if isinstance(raw, Mapping) and raw.get("safety_review"):
            safety.append(str(r.get("id", "")))
    dates = [str(r.get("created_at")) for r in unresolved if r.get("created_at")]
    return {"evidence_count": len(items), "high_priority_count": len(high),
        "unresolved_count": len(unresolved), "category_counts": dict(categories),
        "department_counts": dict(departments), "high_priority_ids": [str(r.get("id", "")) for r in high],
        "report_ids": [str(r.get("id", "")) for r in items], "safety_review_ids": safety,
        "oldest_unresolved": min(dates) if dates else None,
        "primary_category": categories.most_common(1)[0][0] if categories else "civic issues",
        "department": departments.most_common(1)[0][0] if departments else "Civic Services"}


def _valid_model_brief(value: object) -> dict:
    if not isinstance(value, dict):
        raise ValueError("Brief model output must be a JSON object")
    summary, action = value.get("summary"), value.get("next_action")
    if not isinstance(summary, str) or not summary.strip() or len(summary.strip()) > 280:
        raise ValueError("Brief summary is missing or too long")
    if not isinstance(action, str) or not action.strip() or len(action.strip()) > 360:
        raise ValueError("Brief action is missing or too long")
    return {"summary": summary.strip(), "next_action": action.strip()}


def generate_action_brief(reports: list[Mapping], title: str = "Civic action brief", *, model_call=None) -> dict:
    evidence = build_evidence(reports)
    summary = (f"{evidence['evidence_count']} reports relate to {evidence['primary_category'].lower()}; "
               f"{evidence['unresolved_count']} remain unresolved.")
    next_action = (f"Review {evidence['high_priority_count']} high-priority report(s), verify conditions on site, "
                  f"and coordinate with {evidence['department']}.")
    engine = "Template generated from saved report records; no LLM call."
    call = model_call
    if call is None and is_configured():
        call = generate_json
    if call is not None:
        # Only derived evidence and short report excerpts go to the configured model.
        evidence_payload = {k: evidence[k] for k in ("evidence_count", "high_priority_count", "unresolved_count", "category_counts", "department_counts", "high_priority_ids", "report_ids", "safety_review_ids")}
        system = ("Write a short operational civic brief using only supplied evidence. Return JSON with summary and next_action. "
                  "Do not invent counts, locations, causes, report IDs, or confirmed facts. Counts and citations are computed outside you.")
        try:
            result = _valid_model_brief(call(system, json.dumps(evidence_payload, ensure_ascii=False)))
            summary, next_action = result["summary"], result["next_action"]
            engine = ("Configured LLM summary over code-computed evidence; counts and citations remain code-derived."
                      if model_call is None else "Injected brief generator (test adapter); counts and citations remain code-derived.")
        except Exception:
            engine = "Template fallback (LLM unavailable or output rejected); evidence computed from saved reports."
    return {"title": title, "summary": summary, "evidence_count": evidence["evidence_count"],
        "high_priority_count": evidence["high_priority_count"], "unresolved_count": evidence["unresolved_count"],
        "risk_uncertainty": ("Report descriptions and proximity are unverified; field review is needed before confirming a shared cause. "
            + (f"Possible safety-review IDs: {', '.join(evidence['safety_review_ids'])}." if evidence["safety_review_ids"] else "No rule-triggered safety terms were found; this does not establish safety.")),
        "next_action": next_action, "department": evidence["department"], "report_ids": evidence["report_ids"],
        "evidence": evidence, "generation": engine}
