import os, tempfile, sys
from pathlib import Path

os.environ["JANANI_DATA_DIR"] = tempfile.mkdtemp(prefix="janani-test-")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.security import create_access_token

c = TestClient(app)
_staff_cache: dict[str, dict] = {}


def api(path, method="get", staff=None, **kw):
    headers = {}
    if staff:
        info = _staff_cache.get(staff, {"role": "nurse", "clinic": "demo-clinic", "name": staff})
        tok = create_access_token(
            subject=staff,
            role=info["role"],
            clinic=info["clinic"],
            name=info["name"],
        )
        headers["Authorization"] = f"Bearer {tok}"
    return getattr(c, method)(path, headers=headers, **kw)


def test_flow():
    doc_row = api("/api/staff", "post", json={"name": "Dr Test", "role": "doctor"}).json()
    doc = doc_row["id"]
    _staff_cache[doc] = doc_row

    nurse_row = api("/api/staff", "post", json={"name": "Nurse Test", "role": "nurse"}).json()
    nurse = nurse_row["id"]
    _staff_cache[nurse] = nurse_row

    admin_row = api("/api/staff", "post", json={"name": "Admin Test", "role": "admin"}).json()
    admin = admin_row["id"]
    _staff_cache[admin] = admin_row

    # Verify legacy X-Staff-ID header is rejected on protected endpoints
    assert c.get("/api/mothers", headers={"X-Staff-ID": nurse}).status_code == 401

    r = api(
        "/api/mothers",
        "post",
        staff=nurse,
        json={"name": "Synthetic Mother", "phone": "0000000000", "consent": True, "language": "en"},
    )
    assert r.status_code == 200
    mid = r.json()["id"]
    assert api(f"/api/mothers/{mid}/plans", "post", staff=nurse, json={"visit_date": "2026-11-03"}).status_code == 403
    p = api(f"/api/mothers/{mid}/plans", "post", staff=doc, json={"visit_date": "2026-11-03"})
    assert p.status_code == 200
    p2 = api(f"/api/mothers/{mid}/plans", "post", staff=doc, json={"visit_date": "2026-11-05"})
    assert p2.json()["version"] == 2
    plans = api(f"/api/mothers/{mid}/plans", staff=nurse).json()
    assert len(plans) == 2 and sum(p["active"] for p in plans) == 1
    m = api("/api/reminders/send", "post", staff=nurse, json={"mother_id": mid})
    assert "2026-11-05" in m.json()["body"] and m.json()["status"] == "simulated"
    assert api("/api/messages/reply", "post", staff=nurse, json={"mother_id": mid, "body": "Please call me"}).status_code == 200
    tasks = api("/api/tasks", staff=nurse).json()
    assert len(tasks) == 1
    assert api("/api/tasks/" + tasks[0]["id"], "patch", staff=nurse, json={"status": "resolved"}).json()["status"] == "resolved"
    assert api("/api/transport", "post", staff=nurse, json={"mother_id": mid, "date": "2026-11-05", "from_location": "Village", "destination": "Clinic"}).status_code == 200
    assert api("/api/expenses", "post", staff=nurse, json={"category": "travel", "amount_rupees": 500}).status_code == 403
    exp = api("/api/expenses", "post", staff=admin, json={"category": "travel", "amount_rupees": 500}).json()
    assert api("/api/expenses/" + exp["id"], "patch", staff=admin, json={"approved": True}).json()["approved"]
    assert api("/api/analytics", staff=admin).json()["registered_mothers"] == 1
    assert len(api("/api/events", staff=admin).json()) >= 7
    assert api("/api/mothers/" + mid + "/consent", "patch", staff=nurse, json={"consent": False}).status_code == 200
    assert api("/api/reminders/send", "post", staff=nurse, json={"mother_id": mid}).status_code == 400
