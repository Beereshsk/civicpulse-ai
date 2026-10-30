"""Backward-compatible imports for the modular ``civic_engine`` package."""
from civic_engine.briefs import generate_action_brief
from civic_engine.categorization import CATEGORIES, categorize_complaint
from civic_engine.departments import DEPARTMENTS
from civic_engine.duplicates import detect_duplicates
from civic_engine.geography import cluster_reports
from civic_engine.pipeline import process_complaint
from civic_engine.priority import WEIGHTS, score_priority
from civic_engine.summarization import local_summary

STATUSES = ["Submitted", "Under Review", "Assigned", "In Progress", "Resolved"]


def validate_status_update(status: str) -> str:
    if status not in STATUSES:
        raise ValueError("Choose a valid workflow status.")
    return status


def categorize(text: str, supplied: str = "Other"):
    result = categorize_complaint(text, supplied)
    return result["suggested_category"], result["confidence"]


def score_report(text: str, created_at: str):
    return score_priority(text, created_at)


def analyze(text: str, supplied_category: str, created_at: str):
    return process_complaint({"description": text, "category": supplied_category}, created_at=created_at)


def duplicate_candidates(report: dict, others: list[dict], threshold: int = 38):
    return detect_duplicates(report, others, threshold=threshold)


def action_brief(reports: list[dict], title: str = "Civic action brief"):
    return generate_action_brief(reports, title)
