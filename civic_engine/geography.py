"""Greedy radius clustering over records that have valid coordinates."""
from __future__ import annotations

import math
from .models import Complaint


def _distance(a: Complaint, b: Complaint) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a.lat, a.lon, b.lat, b.lon))
    hav = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 6371000 * 2 * math.atan2(math.sqrt(hav), math.sqrt(max(0.0, 1-hav)))


def cluster_reports(reports: list[dict], radius_m: int = 500, minimum: int = 3) -> list[dict]:
    complaints = [Complaint.from_record(r) for r in reports]
    located = [(raw, model) for raw, model in zip(reports, complaints) if model.lat is not None and model.lon is not None]
    assigned, clusters = set(), []
    for seed_raw, seed in located:
        if seed.id in assigned:
            continue
        members = [(raw, item) for raw, item in located if item.id not in assigned and _distance(seed, item) <= radius_m]
        if len(members) < minimum:
            continue
        assigned.update(item.id for _, item in members)
        unresolved = [(raw, item) for raw, item in members if item.status != "Resolved"]
        categories = {}
        for raw, item in members:
            name = item.category or "Other"
            categories[name] = categories.get(name, 0) + 1
        dates = [item.created_at for _, item in unresolved if item.created_at]
        clusters.append({"id": f"H{len(clusters)+1:02d}", "count": len(members),
            "lat": sum(item.lat for _, item in members)/len(members),
            "lon": sum(item.lon for _, item in members)/len(members),
            "categories": sorted(categories.items(), key=lambda pair: pair[1], reverse=True),
            "high_priority": sum(item.priority_label in ("Critical", "High") for _, item in members),
            "unresolved": len(unresolved), "oldest_unresolved": min(dates) if dates else None,
            "report_ids": [item.id for _, item in members],
            "signal_note": "Proximity signal only; not evidence of a shared cause."})
    return sorted(clusters, key=lambda item: (item["high_priority"], item["count"]), reverse=True)
