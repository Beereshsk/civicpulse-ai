import json
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import app
from http.server import ThreadingHTTPServer
from intelligence import action_brief, analyze, cluster_reports, duplicate_candidates, score_report, validate_status_update


class IntelligenceTests(unittest.TestCase):
    def test_priority_is_weighted_and_components_are_exposed(self):
        result = score_report("Exposed wire beside the school crossing", datetime.now(timezone.utc).isoformat())
        self.assertTrue(result["safety_review"])
        self.assertEqual(result["score"], round(sum(result["contributions"].values())))
        self.assertEqual(result["contributions"]["safety"], round(result["components"]["safety"] * .40, 1))
        self.assertIn(result["label"], ("Critical", "High", "Medium", "Low"))

    def test_categorization_is_rule_labeled_and_uncertainty_is_visible(self):
        result = analyze("A pothole near the school crossing", "Other", datetime.now(timezone.utc).isoformat())
        self.assertEqual(result["suggested_category"], "Roads and potholes")
        self.assertIn("no LLM", result["engine"])
        self.assertTrue(result["uncertainty"])

    def test_duplicate_requires_text_signal_not_category_alone(self):
        report = {"id":"a","description":"Large pothole beside the north school crossing","category":"Roads and potholes","lat":1,"lon":1}
        related = {"id":"b","description":"Large pothole beside the north school crossing near school","category":"Roads and potholes","lat":1.001,"lon":1.001}
        unrelated = {"id":"c","description":"Paint is faded on the playground fence","category":"Roads and potholes","lat":1,"lon":1}
        matches = duplicate_candidates(report,[report,related,unrelated])
        self.assertEqual([m["candidate_id"] for m in matches],["b"])
        self.assertIn("not a duplicate verdict",matches[0]["explanation"])

    def test_hotspots_and_briefs_use_report_evidence(self):
        reports=[{"id":str(i),"lat":.01+i*.0001,"lon":.01,"category":"Waste management","priority_label":"High","status":"Submitted","created_at":"2026-01-01","department":"Sanitation"} for i in range(3)]
        clusters=cluster_reports(reports)
        self.assertEqual(clusters[0]["count"],3)
        brief=action_brief(reports)
        self.assertEqual(brief["report_ids"],["0","1","2"])
        self.assertEqual(brief["high_priority_count"],3)

    def test_status_validation(self):
        self.assertEqual(validate_status_update("In Progress"),"In Progress")
        with self.assertRaises(ValueError): validate_status_update("Closed")


class ApiJourneyTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        self.old_db=app.DB_PATH
        app.DB_PATH=Path(self.temp.name)/"test.sqlite3"
        app.init_db()
        self.server=ThreadingHTTPServer(("127.0.0.1",0),app.Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base=f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=2)
        app.DB_PATH=self.old_db
        self.temp.cleanup()

    def request(self,path,method="GET",payload=None):
        data=json.dumps(payload).encode() if payload is not None else None
        req=urllib.request.Request(self.base+path,data=data,method=method,headers={"Content-Type":"application/json"})
        try:
            with urllib.request.urlopen(req,timeout=3) as response:return response.status,json.loads(response.read())
        except urllib.error.HTTPError as exc:return exc.code,json.loads(exc.read())

    def test_submit_operator_update_and_private_citizen_tracking(self):
        status,created=self.request("/api/reports","POST",{"description":"An exposed wire is sparking beside the north school crossing where pedestrians pass","category":"Public safety","address":"Fictional Cedar Lane","lat":.11,"lon":.12})
        self.assertEqual(status,201);self.assertTrue(created["tracking_id"].startswith("TRK-"))
        self.assertTrue(created["analysis"]["safety_review"])
        stored_status,stored=self.request(f"/api/reports/{created['id']}")
        self.assertEqual(stored_status,200)
        self.assertIn("priority (",stored["analysis"]["explanation"])
        self.assertIn("safety",stored["analysis"]["explanation"])
        self.assertEqual(stored["analysis"]["engine"],"Deterministic local rules (no LLM call)")
        dashboard_status,dashboard=self.request("/api/overview")
        self.assertEqual(dashboard_status,200)
        self.assertEqual(dashboard["counts"]["total"],46)
        self.assertEqual(dashboard["counts"]["safety_open"],sum(r["status"]!="Resolved" and r["analysis"].get("safety_review") for r in dashboard["reports"]))
        listed=next(r for r in dashboard["reports"] if r["id"]==created["id"])
        self.assertIn("possible_duplicate_count",listed)
        self.assertGreaterEqual(listed["possible_duplicate_count"],0)
        status,updated=self.request(f"/api/reports/{created['id']}","POST",{"status":"In Progress","department":"Public Works","internal_note":"crew dispatched privately","public_update":"A team has been assigned to inspect the site."})
        self.assertEqual(status,200);self.assertEqual(updated["status"],"In Progress")
        status,public=self.request(f"/api/track/{created['tracking_id']}")
        self.assertEqual(status,200);self.assertEqual(public["status"],"In Progress")
        self.assertEqual(len(public["public_updates"]),1)
        self.assertNotIn("internal_note",json.dumps(public));self.assertNotIn("crew dispatched",json.dumps(public))

    def test_rejects_invalid_status_and_lists_synthetic_records(self):
        self.assertEqual(self.request("/api/overview")[1]["counts"]["total"],45)
        status,body=self.request("/api/reports/CP-DEMO-001","POST",{"status":"Closed"})
        self.assertEqual(status,400);self.assertIn("valid workflow",body["error"])

    def test_invalid_long_note_does_not_partially_commit_status(self):
        status,body=self.request("/api/reports/CP-DEMO-001","POST",{"status":"In Progress","internal_note":"x"*1001})
        self.assertEqual(status,400)
        detail_status,detail=self.request("/api/reports/CP-DEMO-001")
        self.assertEqual(detail_status,200)
        self.assertEqual(detail["status"],"Submitted")

    def test_json_array_body_is_rejected_as_client_error(self):
        request=urllib.request.Request(self.base+"/api/reports",data=b"[]",method="POST",headers={"Content-Type":"application/json"})
        try:
            urllib.request.urlopen(request,timeout=3)
            self.fail("Expected a 400 response")
        except urllib.error.HTTPError as exc:
            self.assertEqual(exc.code,400)

    def test_duplicate_decision_is_saved_and_returned(self):
        status,body=self.request("/api/reports/CP-DEMO-001/duplicates","POST",{"candidate_id":"CP-DEMO-010","decision":"linked"})
        self.assertEqual(status,200)
        status,detail=self.request("/api/reports/CP-DEMO-001")
        self.assertEqual(status,200)
        self.assertEqual(detail["duplicate_links"][0]["decision"],"linked")

    def test_reset_restores_seed_data_in_test_database(self):
        status,created=self.request("/api/reports","POST",{"description":"A pothole report created for reset testing","category":"Roads and potholes","address":"Fictional Test Lane"})
        self.assertEqual(status,201)
        self.assertEqual(self.request("/api/overview")[1]["counts"]["total"],46)
        status,result=self.request("/api/reset","POST",{})
        self.assertEqual(status,200)
        self.assertEqual(self.request("/api/overview")[1]["counts"]["total"],45)


if __name__=="__main__":unittest.main()
