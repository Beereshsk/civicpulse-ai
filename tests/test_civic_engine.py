import json
import math
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from civic_engine.briefs import build_evidence, generate_action_brief
from civic_engine.categorization import categorize_complaint
from civic_engine.duplicates import detect_duplicates
from civic_engine.geography import cluster_reports
from civic_engine.llm import is_configured
from civic_engine.pipeline import process_complaint
from civic_engine.priority import WEIGHTS, score_priority
from civic_engine.summarization import summarize_complaint


class CategorySummaryTests(unittest.TestCase):
    def test_category_uses_keywords_and_falls_back_to_selected_category(self):
        match = categorize_complaint("Deep pothole beside the school crossing", "Other")
        self.assertEqual(match["suggested_category"], "Roads and potholes")
        self.assertEqual(match["method"], "keyword rules")
        fallback = categorize_complaint("", "Water supply")
        self.assertEqual(fallback["suggested_category"], "Water supply")
        self.assertEqual(fallback["confidence"], .25)

    def test_summary_rejects_malformed_and_timed_out_model_output(self):
        malformed = summarize_complaint("Drain overflow on Cedar Lane", "Other", "Waterlogging and drainage",
            model_call=lambda *_: {"summary": "", "suggested_category": "made up"})
        self.assertEqual(malformed["engine"], "Deterministic fallback (LLM unavailable or output rejected)")
        self.assertIn("Drain overflow", malformed["summary"])
        timed_out = summarize_complaint("Pothole on North Street", "Other", "Roads and potholes",
            model_call=lambda *_: (_ for _ in ()).throw(TimeoutError()))
        self.assertIn("fallback", timed_out["engine"])

    def test_empty_summary_and_missing_llm_credentials_use_local_fallback(self):
        result = summarize_complaint("", "Other", "Other")
        self.assertIn("No description", result["summary"])
        self.assertFalse(is_configured({}))


class PriorityTests(unittest.TestCase):
    def test_weights_and_expected_score_are_calculated_in_application_code(self):
        fixed_now = datetime(2026, 1, 15, tzinfo=timezone.utc)
        result = score_priority("Open manhole near school crossing", "2026-01-01T00:00:00+00:00", now=fixed_now)
        expected = math.floor(sum(result["contributions"].values()) + .5)
        self.assertEqual(result["score"], expected)
        self.assertEqual(result["score"], 78)
        self.assertEqual(result["label"], "High")
        self.assertTrue(result["safety_review"])
        self.assertAlmostEqual(sum(WEIGHTS.values()), 1.0)
        self.assertEqual(result["contributions"]["safety"], 36.0)

    def test_half_up_rounding_respects_high_priority_threshold(self):
        result = score_priority("Exposed wire sparking; injury reported at crossing", "2026-01-15T00:00:00+00:00",
            now=datetime(2026, 1, 15, tzinfo=timezone.utc))
        self.assertEqual(sum(result["contributions"].values()), 64.5)
        self.assertEqual(result["score"], 65)
        self.assertEqual(result["label"], "High")

    def test_traffic_conflict_phrase_triggers_human_safety_review(self):
        result = score_priority('Cyclists are swerving into traffic beside a school crossing')
        self.assertTrue(result['safety_review'])
        self.assertIn('swerving into traffic', result['factor_signals']['safety'])

    def test_empty_or_missing_information_does_not_trigger_safety(self):
        result = score_priority("", None)
        self.assertFalse(result["safety_review"])
        self.assertEqual(result["components"]["age"], 0)

    def test_negated_injury_is_not_counted_as_an_affirmative_hazard(self):
        now = datetime(2026, 1, 15, tzinfo=timezone.utc)
        affirmative = score_priority("Injury reported at the school crossing", "2026-01-15T00:00:00+00:00", now=now)
        negated = score_priority("No injury reported at the school crossing", "2026-01-15T00:00:00+00:00", now=now)
        self.assertTrue(affirmative["safety_review"])
        self.assertFalse(negated["safety_review"])
        self.assertEqual(affirmative["components"]["severity"], 64)
        self.assertEqual(negated["components"]["severity"], 46)


class DuplicateTests(unittest.TestCase):
    def test_related_report_matches_but_category_and_location_alone_do_not(self):
        current = {"id": "new", "description": "Large pothole at the north school crossing on Cedar Lane",
            "category": "Roads and potholes", "lat": 1.0, "lon": 1.0}
        related = {"id": "old-1", "description": "Large pothole at north school crossing near Cedar Lane",
            "category": "Roads and potholes", "lat": 1.001, "lon": 1.001}
        unrelated = {"id": "old-2", "description": "Faded paint along the garden fence",
            "category": "Roads and potholes", "lat": 1.0, "lon": 1.0}
        matches = detect_duplicates(current, [related, unrelated])
        self.assertEqual([item["candidate_id"] for item in matches], ["old-1"])
        self.assertIn("token overlap", matches[0]["explanation"])
        self.assertIn("m apart", matches[0]["explanation"])
        self.assertIn("not a duplicate verdict", matches[0]["explanation"])

    def test_missing_coordinates_and_empty_descriptions_are_safe(self):
        current = {"id": "new", "description": "Standing water overflows the drain by Cedar Lane", "category": "Waterlogging and drainage"}
        prior = {"id": "old", "description": "Standing water overflows the drain near Cedar Lane", "category": "Waterlogging and drainage"}
        matches = detect_duplicates(current, [prior])
        self.assertEqual(len(matches), 1)
        self.assertNotIn("m apart", matches[0]["explanation"])
        self.assertEqual(detect_duplicates({"id": "empty", "description": " "}, [prior]), [])


class BriefPipelineTests(unittest.TestCase):
    def test_brief_statistics_are_computed_before_model_prompt_and_ids_stay_code_derived(self):
        reports = [
            {"id": "CP-1", "description": "Exposed wire", "category": "Public safety", "status": "Submitted", "priority_label": "Critical", "department": "Public Safety", "analysis": {"safety_review": True}},
            {"id": "CP-2", "description": "Dark street", "category": "Streetlights and electricity", "status": "Resolved", "priority_label": "Low", "department": "Utilities", "analysis": {}},
        ]
        captured = {}
        def fake_model(_system, prompt):
            captured.update(json.loads(prompt))
            return {"summary": "Two saved reports need different responses.", "next_action": "Inspect the exposed wire first."}
        brief = generate_action_brief(reports, model_call=fake_model)
        self.assertEqual(captured["evidence_count"], 2)
        self.assertEqual(captured["high_priority_ids"], ["CP-1"])
        self.assertEqual(brief["evidence_count"], 2)
        self.assertEqual(brief["unresolved_count"], 1)
        self.assertEqual(brief["report_ids"], ["CP-1", "CP-2"])
        self.assertEqual(brief["summary"], "Two saved reports need different responses.")

    def test_malformed_brief_model_output_falls_back_to_template(self):
        brief = generate_action_brief([], model_call=lambda *_: {"summary": "not enough"})
        self.assertEqual(brief["evidence_count"], 0)
        self.assertIn("fallback", brief["generation"])

    def test_submission_pipeline_uses_existing_report_candidates_and_priority(self):
        prior = {"id": "CP-OLD", "description": "Open manhole at the school crossing on Pine Road",
            "category": "Public safety", "lat": 4.2, "lon": 5.1}
        result = process_complaint({"id": "CP-NEW", "description": "Open manhole at school crossing on Pine Road",
            "category": "Other", "lat": 4.2, "lon": 5.1}, [prior], created_at="2026-01-01T00:00:00+00:00", use_llm=False)
        self.assertEqual(result["suggested_category"], "Public safety")
        self.assertEqual(result["department"], "Public Safety")
        self.assertTrue(result["safety_review"])
        self.assertEqual(result["confidence"], categorize_complaint("Open manhole at school crossing on Pine Road", "Other")["confidence"])
        self.assertEqual(result["duplicates"][0]["candidate_id"], "CP-OLD")
        self.assertEqual(result["engine"], "Deterministic local rules (no LLM call)")


class DashboardEvidenceTests(unittest.TestCase):
    def test_seed_dashboard_statistics_and_evidence_ids_come_from_records(self):
        import app
        with TemporaryDirectory() as directory:
            old_db = app.DB_PATH
            app.DB_PATH = Path(directory) / "dashboard.sqlite3"
            try:
                app.init_db()
                reports = app.all_reports()
                brief = generate_action_brief(reports)
                hotspots = cluster_reports(reports)
                self.assertEqual(len(reports), 45)
                self.assertEqual(brief["evidence_count"], len(reports))
                self.assertEqual(set(brief["report_ids"]), {r["id"] for r in reports})
                self.assertTrue(hotspots)
                known_ids = {r["id"] for r in reports}
                self.assertTrue(all(set(h["report_ids"]) <= known_ids for h in hotspots))
                self.assertTrue(any(detect_duplicates(r, reports) for r in reports))
            finally:
                app.DB_PATH = old_db


if __name__ == "__main__":
    unittest.main()
