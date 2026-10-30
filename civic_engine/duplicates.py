"""Explainable lexical and optional geographic duplicate candidate matching."""
from __future__ import annotations

import math
import re
from difflib import SequenceMatcher
from typing import Mapping

from .models import Complaint

TOKEN_RE = re.compile(r"[a-z0-9]+")
STOP_WORDS = {"the", "and", "near", "beside", "on", "at", "to", "is", "a", "an", "of", "for", "in", "this", "that", "it", "with", "are", "was"}


def _tokens(text: str) -> set[str]:
    return {token for token in TOKEN_RE.findall(text.lower()) if len(token) > 2 and token not in STOP_WORDS}


def _distance_m(a: Complaint, b: Complaint) -> float | None:
    if a.lat is None or a.lon is None or b.lat is None or b.lon is None:
        return None
    lat1, lon1, lat2, lon2 = map(math.radians, (a.lat, a.lon, b.lat, b.lon))
    hav = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 6371000 * 2 * math.atan2(math.sqrt(hav), math.sqrt(max(0.0, 1-hav)))


def detect_duplicates(report: Mapping, existing_reports: list[Mapping], *, threshold: int = 38, limit: int = 5) -> list[dict]:
    """Return candidates based on text plus optional category and distance signals.

    Similarity is a heuristic score, not a probability or an automatic merge.
    At least one text signal is required; missing coordinates simply remove the
    geographic component. Empty descriptions produce no candidates.
    """
    target = Complaint.from_record(report)
    text = target.description.lower()
    if not text or not _tokens(text):
        return []
    target_tokens = _tokens(text)
    results = []
    for record in existing_reports:
        candidate = Complaint.from_record(record)
        if not candidate.id or candidate.id == target.id or not candidate.description:
            continue
        candidate_tokens = _tokens(candidate.description.lower())
        lexical = SequenceMatcher(None, text, candidate.description.lower()).ratio() * 100
        overlap = 100 * len(target_tokens & candidate_tokens) / max(1, len(target_tokens | candidate_tokens))
        same_category = target.category == candidate.category and target.category != "Other"
        category_points = 12 if same_category else 0
        distance = _distance_m(target, candidate)
        geo_points = max(0, 18 * (1 - distance / 800)) if distance is not None else 0
        score = round(min(100, .48 * lexical + .42 * overlap + category_points + geo_points))
        if score < threshold or not (lexical >= 55 or overlap >= 25):
            continue
        reasons = [f"{round(overlap)}% meaningful token overlap"]
        if same_category:
            reasons.append("same suggested category")
        if distance is not None:
            reasons.append(f"{round(distance)} m apart")
        results.append({"candidate_id": candidate.id, "score": score,
                        "explanation": ", ".join(reasons) + "; similarity signal, not a duplicate verdict"})
    return sorted(results, key=lambda result: (-result["score"], result["candidate_id"]))[:max(0, limit)]
