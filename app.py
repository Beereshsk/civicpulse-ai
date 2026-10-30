"""Local CivicPulse prototype: Python stdlib HTTP server + SQLite."""
from __future__ import annotations

import json
import mimetypes
import os
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from civic_engine.briefs import generate_action_brief
from civic_engine.categorization import CATEGORIES
from civic_engine.duplicates import detect_duplicates
from civic_engine.geography import cluster_reports
from civic_engine.pipeline import process_complaint
from intelligence import validate_status_update
from seed_data import seed_demo

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("CIVICPULSE_DB", ROOT / "civicpulse.sqlite3"))
STATIC = ROOT / "static"
UPLOADS = Path(os.environ.get("CIVICPULSE_UPLOAD_DIR", STATIC / "uploads")).resolve()
MAX_BODY = 3 * 1024 * 1024


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db():
    UPLOADS.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS reports (
          id TEXT PRIMARY KEY, tracking_id TEXT UNIQUE NOT NULL, description TEXT NOT NULL,
          category TEXT NOT NULL, suggested_category TEXT NOT NULL, address TEXT NOT NULL,
          lat REAL, lon REAL, image_path TEXT, status TEXT NOT NULL, department TEXT,
          priority_score INTEGER NOT NULL, priority_label TEXT NOT NULL, analysis TEXT NOT NULL,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL, resolution TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS history (
          id INTEGER PRIMARY KEY AUTOINCREMENT, report_id TEXT NOT NULL, kind TEXT NOT NULL,
          text TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS duplicate_links (
          id INTEGER PRIMARY KEY AUTOINCREMENT, report_a TEXT NOT NULL, report_b TEXT NOT NULL,
          decision TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(report_a, report_b)
        );
        CREATE INDEX IF NOT EXISTS idx_reports_created ON reports(created_at);
        """)
        if db.execute("SELECT COUNT(*) FROM reports").fetchone()[0] == 0:
            seed_demo(db)


def report_dict(row):
    item = dict(row)
    item["analysis"] = json.loads(item["analysis"])
    item["priority_components"] = item["analysis"].get("components", {})
    return item


def all_reports():
    with connect() as db:
        return [report_dict(r) for r in db.execute("SELECT * FROM reports ORDER BY created_at DESC")]


def public_view(item):
    """Explicit allowlist: never expose internal notes or operator-only fields."""
    with connect() as db:
        updates = [dict(r) for r in db.execute("SELECT text,created_at FROM history WHERE report_id=? AND kind='public' ORDER BY id", (item["id"],))]
    return {key: item.get(key) for key in ("id", "tracking_id", "description", "category", "suggested_category", "address", "status", "department", "priority_label", "created_at", "updated_at", "resolution") if key in item} | {"summary": item["analysis"].get("summary"), "public_updates": updates}


class Handler(BaseHTTPRequestHandler):
    server_version = "CivicPulseLocal/1.0"

    def log_message(self, fmt, *args):
        print("[%s] %s" % (self.log_date_time_string(), fmt % args))

    def send_json(self, data, status=200):
        payload = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def body(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length > MAX_BODY: raise ValueError("Request exceeds 3 MB limit")
        payload = json.loads(self.rfile.read(length) or b"{}")
        if not isinstance(payload, dict):
            raise ValueError("Request body must be a JSON object.")
        return payload

    def do_GET(self):
        path = unquote(urlparse(self.path).path)
        if path == "/api/reports":
            reports = all_reports()
            query = parse_qs(urlparse(self.path).query)
            search = query.get("q", [""])[0].strip().lower()
            if search: reports = [r for r in reports if search in (r["id"] + r["description"] + r["category"] + r["address"] + r["status"]).lower()]
            return self.send_json(reports)
        if path == "/api/overview":
            reports = all_reports()
            for report in reports:
                report["possible_duplicate_count"] = len(detect_duplicates(report, reports))
            unresolved_safety = [r for r in reports if r["status"] != "Resolved" and r["analysis"].get("safety_review")]
            counts = {"total": len(reports), "open": sum(r["status"] != "Resolved" for r in reports),
                      "urgent": sum(r["priority_label"] in ("Critical", "High") for r in reports),
                      "unassigned": sum(not r["department"] for r in reports), "resolved": sum(r["status"] == "Resolved" for r in reports),
                      "safety_open": len(unresolved_safety)}
            category = {}
            priority = {}
            for r in reports:
                category[r["category"]] = category.get(r["category"], 0) + 1
                priority[r["priority_label"]] = priority.get(r["priority_label"], 0) + 1
            hotspots = cluster_reports(reports)
            return self.send_json({"counts": counts, "categories": category, "priorities": priority,
                "reports": reports, "hotspots": hotspots,
                "safety_report_ids": [r["id"] for r in unresolved_safety],
                "brief": generate_action_brief(reports, "District situation brief"),
                "engine": "Rule-based local analysis; synthetic demo records are labeled in the UI."})
        if path.startswith("/api/track/"):
            tracking = path.rsplit("/", 1)[-1].strip().upper()
            with connect() as db: row = db.execute("SELECT * FROM reports WHERE tracking_id=?", (tracking,)).fetchone()
            if not row: return self.send_json({"error": "No report found for that tracking ID."}, 404)
            return self.send_json(public_view(report_dict(row)))
        if path.startswith("/api/reports/"):
            report_id = path.rsplit("/", 1)[-1]
            with connect() as db: row = db.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone()
            if not row: return self.send_json({"error": "Report not found."}, 404)
            item = report_dict(row)
            reports = all_reports()
            item["duplicates"] = detect_duplicates(item, reports)
            with connect() as db:
                item["history"] = [dict(r) for r in db.execute("SELECT kind,text,created_at FROM history WHERE report_id=? ORDER BY id", (report_id,))]
                item["duplicate_links"] = [dict(r) for r in db.execute("SELECT * FROM duplicate_links WHERE report_a=? OR report_b=?", (report_id, report_id))]
            return self.send_json(item)
        if path == "/" or path.startswith("/static/"):
            name = "index.html" if path == "/" else path.removeprefix("/static/")
            if name == "uploads" or name.startswith("uploads/"):
                root = UPLOADS
                relative_name = name.removeprefix("uploads/")
            else:
                root = STATIC
                relative_name = name
            target = (root / relative_name).resolve()
            if not target.is_relative_to(root.resolve()) or not target.is_file(): return self.send_error(404)
            data = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            return self.wfile.write(data)
        return self.send_error(404)

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            payload = self.body()
            if path == "/api/reports": return self.create_report(payload)
            if path == "/api/reset":
                with connect() as db:
                    db.execute("DELETE FROM history"); db.execute("DELETE FROM duplicate_links"); db.execute("DELETE FROM reports")
                    seed_demo(db)
                return self.send_json({"ok": True, "message": "Synthetic demonstration data restored."})
            if path.startswith("/api/reports/") and path.endswith("/duplicates"):
                report_id = path.split("/")[-2]
                other = payload.get("candidate_id", "")
                decision = payload.get("decision")
                if decision not in ("linked", "dismissed"): return self.send_json({"error": "Decision must be linked or dismissed."}, 400)
                if not isinstance(other, str) or not other or other == report_id:
                    return self.send_json({"error": "Choose a different candidate report."}, 400)
                with connect() as db:
                    ids = {r[0] for r in db.execute("SELECT id FROM reports WHERE id IN (?,?)", (report_id, other))}
                    if ids != {report_id, other}:
                        return self.send_json({"error": "One or both reports were not found."}, 404)
                    a,b = sorted([report_id, other])
                    db.execute("INSERT OR REPLACE INTO duplicate_links(report_a,report_b,decision,created_at) VALUES(?,?,?,?)", (a,b,decision,now()))
                return self.send_json({"ok": True})
            if path.startswith("/api/reports/"): return self.update_report(path.rsplit("/",1)[-1], payload)
            return self.send_error(404)
        except (ValueError, json.JSONDecodeError) as exc:
            return self.send_json({"error": str(exc)}, 400)
        except Exception as exc:
            return self.send_json({"error": "The request could not be saved. " + str(exc)}, 500)

    def create_report(self, data):
        description = str(data.get("description", "")).strip()
        category = str(data.get("category", "Other"))
        address = str(data.get("address", "")).strip()
        if len(description) < 12: return self.send_json({"error": "Please add at least 12 characters describing the issue."}, 400)
        if len(description) > 2000: return self.send_json({"error": "Description must be 2,000 characters or fewer."}, 400)
        if category not in CATEGORIES: return self.send_json({"error": "Choose a listed category."}, 400)
        if not address or len(address) > 180: return self.send_json({"error": "Enter a location up to 180 characters."}, 400)
        lat = data.get("lat"); lon = data.get("lon")
        try:
            if (lat is None) != (lon is None): raise ValueError()
            if lat is not None:
                lat, lon = float(lat), float(lon)
                if not (-90 <= lat <= 90 and -180 <= lon <= 180): raise ValueError()
        except (TypeError, ValueError): return self.send_json({"error": "Enter valid latitude and longitude together."}, 400)
        image_path = None
        image = data.get("image")
        if image:
            match = re.fullmatch(r"data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=]+)", image)
            if not match: return self.send_json({"error": "Use a PNG, JPG, or WebP image."}, 400)
            import base64
            binary = base64.b64decode(match.group(2), validate=True)
            if len(binary) > 2 * 1024 * 1024: return self.send_json({"error": "Image must be 2 MB or smaller."}, 400)
            ext = "jpg" if match.group(1) == "jpeg" else match.group(1)
            image_name = uuid.uuid4().hex + "." + ext
            image_path = "/static/uploads/" + image_name
            (UPLOADS / image_name).write_bytes(binary)
        created = now(); report_id = "CP-" + uuid.uuid4().hex[:8].upper(); tracking = "TRK-" + uuid.uuid4().hex[:8].upper()
        analysis = process_complaint({"id": report_id, "description": description, "category": category,
            "address": address, "lat": lat, "lon": lon, "created_at": created},
            existing_reports=all_reports(), created_at=created)
        with connect() as db:
            db.execute("""INSERT INTO reports(id,tracking_id,description,category,suggested_category,address,lat,lon,image_path,status,department,priority_score,priority_label,analysis,created_at,updated_at)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (report_id,tracking,description,category,analysis["suggested_category"],address,lat,lon,image_path,"Submitted",analysis["department"],analysis["score"],analysis["label"],json.dumps(analysis),created,created))
            db.execute("INSERT INTO history(report_id,kind,text,created_at) VALUES(?,?,?,?)", (report_id,"status","Report submitted",created))
        with connect() as db: row = db.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone()
        item = report_dict(row); item["duplicates"] = detect_duplicates(item, all_reports())
        return self.send_json(item, 201)

    def update_report(self, report_id, data):
        with connect() as db: row = db.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone()
        if not row: return self.send_json({"error": "Report not found."}, 404)
        item = report_dict(row); status = data.get("status", item["status"]); department = str(data.get("department", item["department"] or ""))[:80]
        try: validate_status_update(status)
        except ValueError as exc: return self.send_json({"error": str(exc)}, 400)
        notes = {"internal_note": str(data.get("internal_note", "")).strip(),
                 "public_update": str(data.get("public_update", "")).strip()}
        for note in notes.values():
            if len(note) > 1000:
                return self.send_json({"error": "Notes and updates must be 1,000 characters or fewer."}, 400)
        resolution = str(data.get("resolution", "")).strip()
        if len(resolution) > 1000:
            return self.send_json({"error": "Resolution details must be 1,000 characters or fewer."}, 400)
        updated = now()
        with connect() as db:
            db.execute("UPDATE reports SET status=?,department=?,updated_at=?,resolution=? WHERE id=?", (status,department,updated,resolution or item["resolution"],report_id))
            if status != item["status"]: db.execute("INSERT INTO history(report_id,kind,text,created_at) VALUES(?,?,?,?)", (report_id,"status",f"Status changed to {status}",updated))
            if department != (item["department"] or ""): db.execute("INSERT INTO history(report_id,kind,text,created_at) VALUES(?,?,?,?)", (report_id,"internal",f"Assigned to {department or 'Unassigned'}",updated))
            for kind, key in (("internal","internal_note"),("public","public_update")):
                text = notes[key]
                if text:
                    db.execute("INSERT INTO history(report_id,kind,text,created_at) VALUES(?,?,?,?)", (report_id,kind,text,updated))
            if resolution and status == "Resolved": db.execute("INSERT INTO history(report_id,kind,text,created_at) VALUES(?,?,?,?)", (report_id,"public", "Resolution: " + resolution,updated))
        with connect() as db: result = report_dict(db.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone())
        return self.send_json(result)


def main():
    init_db()
    port = int(os.environ.get("PORT", "8000"))
    default_host = "0.0.0.0" if "PORT" in os.environ else "127.0.0.1"
    host = os.environ.get("CIVICPULSE_HOST", default_host)
    print(f"CivicPulse AI demo: http://{host}:{port}  (SQLite: {DB_PATH})")
    print("Local prototype only; operator routes have no authentication.")
    ThreadingHTTPServer((host,port), Handler).serve_forever()


if __name__ == "__main__": main()
