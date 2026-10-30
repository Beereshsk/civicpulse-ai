"""Deterministic prototype priority scoring; weights are policy assumptions."""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone

WEIGHTS = {"safety": .40, "severity": .25, "impact": .20, "age": .15}
SAFETY_TERMS = ("exposed wire", "sparking", "open manhole", "fire", "gas leak", "collapsed", "injury", "accident", "live wire", "swerving into traffic", "swerving into oncoming traffic", "near miss")
SEVERITY_TERMS = SAFETY_TERMS + ("deep", "large", "blocked", "overflow", "flood", "no water", "outage", "school", "hospital")
IMPACT_TERMS = ("school", "hospital", "bus", "crossing", "market", "many", "residents", "intersection", "main road")
NEGATION_PREFIX = re.compile(r"\b(?:no|not|never|without|none)\s+(?:(?:a|an|the|any|reported|known|confirmed|evidence|indication|signs?|of)\s+){0,4}$")


def term_is_asserted(text: str, term: str) -> bool:
    """Ignore a keyword occurrence explicitly negated immediately before it."""
    for match in re.finditer(re.escape(term), text):
        prefix = text[max(0, match.start() - 56):match.start()]
        if not NEGATION_PREFIX.search(prefix):
            return True
    return False


def asserted_terms(text: str, terms: tuple[str, ...]) -> list[str]:
    return [term for term in terms if term_is_asserted(text, term)]


def _age_days(created_at: str | None, now: datetime | None) -> float:
    if not created_at:
        return 0.0
    try:
        created = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        return max(0.0, (current - created).total_seconds() / 86400)
    except (ValueError, TypeError, OverflowError):
        return 0.0


def score_priority(description: str, created_at: str | None = None, *, now: datetime | None = None) -> dict:
    """Score factors 0-100, apply 40/25/20/15 weights in Python, then label.

    Missing text does not imply safety: absent hazard terms receive only the
    neutral-low safety baseline and are never marked as verified safe.
    """
    text = str(description or "").strip().lower()
    safety_signals = asserted_terms(text, SAFETY_TERMS)
    severity_signals = asserted_terms(text, SEVERITY_TERMS)
    impact_signals = asserted_terms(text, IMPACT_TERMS)
    safety = 90 if safety_signals else (35 if term_is_asserted(text, "unsafe") else 8)
    severity = min(100, 28 + 18 * len(severity_signals))
    impact = min(100, 25 + 15 * len(impact_signals))
    days = _age_days(created_at, now)
    age = round(min(100, days / 14 * 100))
    components = {"safety": safety, "severity": severity, "impact": impact, "age": age}
    contributions = {name: round(value * WEIGHTS[name], 1) for name, value in components.items()}
    # Conventional half-up integer display; avoid Python's ties-to-even at 64.5.
    score = max(0, min(100, math.floor(sum(contributions.values()) + .5)))
    label = "Critical" if score >= 85 else "High" if score >= 65 else "Medium" if score >= 35 else "Low"
    needs_human_review = bool(safety_signals)
    explanation = (f"{label} priority ({score}/100): safety {safety} x 40%, severity {severity} x 25%, "
                   f"public impact {impact} x 20%, and complaint age {age} x 15%.")
    if needs_human_review:
        explanation += " A possible immediate safety hazard is flagged for human review."
    return {"score": score, "label": label, "components": components, "contributions": contributions,
            "weights": dict(WEIGHTS), "factors": [k for k, v in components.items() if v >= 60],
            "factor_signals": {"safety": safety_signals, "severity": severity_signals, "impact": impact_signals},
            "explanation": explanation, "safety_review": needs_human_review, "age_days": round(days, 1)}
