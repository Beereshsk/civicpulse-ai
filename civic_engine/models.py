"""Typed view over the existing SQLite report dictionaries/rows."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class Complaint:
    id: str
    description: str
    category: str = "Other"
    address: str = ""
    lat: float | None = None
    lon: float | None = None
    status: str = "Submitted"
    department: str = ""
    priority_score: int = 0
    priority_label: str = "Low"
    created_at: str = ""
    analysis: Mapping[str, Any] | None = None

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "Complaint":
        """Adapt the established report row/dict without changing its schema."""
        def coordinate(name: str) -> float | None:
            value = record.get(name)
            if value is None or value == "":
                return None
            try:
                result = float(value)
                limit = 90 if name == "lat" else 180
                return result if -limit <= result <= limit else None
            except (TypeError, ValueError):
                return None

        description = str(record.get("description") or "").strip()
        return cls(
            id=str(record.get("id") or ""), description=description,
            category=str(record.get("suggested_category") or record.get("category") or "Other"),
            address=str(record.get("address") or ""), lat=coordinate("lat"), lon=coordinate("lon"),
            status=str(record.get("status") or "Submitted"), department=str(record.get("department") or ""),
            priority_score=int(record.get("priority_score") or 0), priority_label=str(record.get("priority_label") or "Low"),
            created_at=str(record.get("created_at") or ""), analysis=record.get("analysis") if isinstance(record.get("analysis"), Mapping) else None,
        )
