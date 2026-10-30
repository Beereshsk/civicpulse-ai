"""Rule-based category suggestion with explicit confidence and matched terms."""
from __future__ import annotations

from .models import Complaint

CATEGORIES = (
    "Roads and potholes", "Waterlogging and drainage", "Waste management",
    "Streetlights and electricity", "Water supply", "Public safety", "Other",
)
RULES = (
    ("Waterlogging and drainage", ("flood", "waterlogging", "drain", "sewer", "standing water", "overflow")),
    ("Waste management", ("garbage", "waste", "trash", "rubbish", "dump", "bin")),
    ("Streetlights and electricity", ("streetlight", "street light", "electricity", "power line", "dark", "outage")),
    ("Water supply", ("water supply", "no water", "tap water", "pipe burst", "leak")),
    ("Public safety", ("unsafe", "exposed wire", "sparking", "open manhole", "accident", "hazard", "fire")),
    ("Roads and potholes", ("pothole", "road", "pavement", "sidewalk", "crater", "traffic")),
)


def categorize_complaint(description: str, supplied_category: str = "Other") -> dict:
    text = str(description or "").strip().lower()
    found = [(category, tuple(term for term in terms if term in text)) for category, terms in RULES]
    category, terms = max(found, key=lambda item: len(item[1]))
    if terms:
        return {"suggested_category": category, "confidence": min(.92, .62 + .1 * len(terms)),
                "matched_terms": list(terms), "method": "keyword rules"}
    fallback = supplied_category if supplied_category in CATEGORIES else "Other"
    return {"suggested_category": fallback, "confidence": .48 if text else .25,
            "matched_terms": [], "method": "citizen-selected fallback"}


def categorize_model(complaint: Complaint) -> dict:
    return categorize_complaint(complaint.description, complaint.category)
