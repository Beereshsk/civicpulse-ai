"""Repeatable fictional demo records; coordinates belong to a synthetic grid."""
import json
from datetime import datetime, timedelta, timezone

from civic_engine.pipeline import process_complaint

GROUPS = [
    ("Roads and potholes", "Deep pothole at the eastbound crossing on Lantern Avenue", "Lantern Avenue / Market crossing", .12, .08),
    ("Waterlogging and drainage", "Standing water keeps covering the footpath after rain", "Canal Walk, Block C", .14, .10),
    ("Streetlights and electricity", "Streetlight is out beside the school crossing", "Juniper School crossing", .42, .61),
    ("Waste management", "Overflowing waste bins are blocking the walkway", "Cedar Square, north path", .77, .32),
    ("Public safety", "Open manhole near the bus stop; pedestrians may fall in", "Lantern Avenue bus stop", .18, .12),
    ("Water supply", "No water supply reported in the upper apartment blocks", "Pebble Court, upper blocks", .71, .72),
    ("Roads and potholes", "Broken pavement makes the main road difficult to cross", "Market Road, west corner", .20, .10),
    ("Waterlogging and drainage", "Drain overflow leaves water across the lane", "Canal Walk, Block B", .13, .09),
    ("Streetlights and electricity", "Exposed wire is sparking beside the walkway", "Cedar Square service path", .74, .34),
]
VARIANTS = ["", " Residents say the problem has continued this week.", " It is close to a busy pedestrian route.", " Please inspect when the team is in the area.", " The condition appears worse after the evening commute."]
STATUSES = ["Submitted", "Under Review", "Assigned", "In Progress", "Resolved"]


def seed_demo(db):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    for i in range(45):
        group = GROUPS[i % len(GROUPS)]
        category, base, address, lat, lon = group
        # Each seed group contains repeated issue language at nearly the same location.
        description = base + VARIANTS[(i // len(GROUPS)) % len(VARIANTS)]
        days = [0, 1, 2, 4, 7, 12, 18, 27, 39][(i * 7 + i // 3) % 9]
        created = (now - timedelta(days=days, hours=i % 11)).isoformat()
        status = STATUSES[(i * 3 + i // 4) % len(STATUSES)]
        report_id = f"CP-DEMO-{i+1:03d}"
        tracking = f"TRK-DEMO-{i+1:03d}"
        analysis = process_complaint({"id": report_id, "description": description, "category": category,
            "address": address, "lat": lat, "lon": lon, "created_at": created},
            existing_reports=[], created_at=created, use_llm=False)
        # Coordinates are fictional values used only for the schematic demo grid.
        lat_v = lat + ((i % 4) - 1.5) * .0018
        lon_v = lon + (((i // 4) % 4) - 1.5) * .0018
        dept = analysis["department"] if i % 8 else ""
        resolution = "Crew completed the repair in this fictional demo scenario." if status == "Resolved" else ""
        db.execute("""INSERT OR IGNORE INTO reports(id,tracking_id,description,category,suggested_category,address,lat,lon,image_path,status,department,priority_score,priority_label,analysis,created_at,updated_at,resolution)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (report_id,tracking,description,category,analysis["suggested_category"],address,lat_v,lon_v,None,status,dept,analysis["score"],analysis["label"],json.dumps(analysis),created,created,resolution))
        db.execute("INSERT INTO history(report_id,kind,text,created_at) VALUES(?,?,?,?)", (report_id,"status",f"Demo report seeded as {status}",created))
        if i in (0, 2, 4, 9, 17):
            db.execute("INSERT INTO history(report_id,kind,text,created_at) VALUES(?,?,?,?)", (report_id,"public","Demonstration update: the report is in the civic review queue.",created))
