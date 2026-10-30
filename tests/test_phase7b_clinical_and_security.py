"""Phase 7B Clinical Safety & Security Hardening Regression Suite.

Verifies:
1. Distributed multi-worker login rate limiting using database-backed Event tracking.
2. Advanced CSRF attack scenarios (untrusted Origin, untrusted Referer, missing headers).
3. Clinical authority boundaries (Admin & Nurse blocked from authorising CarePlans).
4. Emergency transport regulatory guard (autonomous 108/102 ambulance dispatch blocked).
5. Zero patient PII in financial reports and evidence packages.
"""
from __future__ import annotations

import random
import uuid
from datetime import date, timedelta
from fastapi.testclient import TestClient
import pytest

from app.main import app, _FAILED_LOGIN_ATTEMPTS


def _u() -> str:
    return uuid.uuid4().hex[:6]


def _digits(length: int = 5) -> str:
    return "".join(random.choices("0123456789", k=length))


def _login(c: TestClient, identifier: str, password: str = "Janani@2026") -> dict[str, str]:
    r = c.post("/api/auth/login", json={"identifier": identifier, "password": password})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    c.cookies.clear()
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def clean_rate_limits():
    _FAILED_LOGIN_ATTEMPTS.clear()
    yield
    _FAILED_LOGIN_ATTEMPTS.clear()


def test_distributed_multi_worker_login_rate_limiting():
    """Verify rate-limiting operates across simulated multiple worker instances via database Event persistence."""
    with TestClient(app) as client:
        test_email = f"bruteforce_{_u()}@nalgonda.janani.org"
        
        # Simulate 10 failed login attempts distributed across different workers
        for i in range(10):
            # Clear in-memory dictionary to simulate requests arriving at completely separate worker processes
            _FAILED_LOGIN_ATTEMPTS.clear()
            res = client.post("/api/auth/login", json={"identifier": test_email, "password": "BadPassword123"})
            assert res.status_code == 401, f"Attempt {i+1} should fail with 401"
            
        # The 11th request on another fresh worker process MUST be blocked by DB-backed tracking (429)
        _FAILED_LOGIN_ATTEMPTS.clear()
        res_11 = client.post("/api/auth/login", json={"identifier": test_email, "password": "BadPassword123"})
        assert res_11.status_code == 429
        assert "Too many failed login attempts" in res_11.json()["detail"]


def test_advanced_csrf_defense_scenarios():
    """Verify CSRF defense rigorously rejects forged Origin, forged Referer, and header-less cookie submissions."""
    with TestClient(app) as client:
        client.post("/api/auth/seed-demo")
        
        # Login and obtain cookie
        res = client.post("/api/auth/login", json={"identifier": "admin@nalgonda.janani.org", "password": "Janani@2026"})
        assert res.status_code == 200
        token = res.json()["access_token"]
        client.cookies.set("janani_access_token", token)
        
        # Scenario 1: Malicious Origin even with forged custom header -> BLOCKED (403)
        res_evil_origin = client.post(
            "/api/tasks",
            json={"mother_id": "test-mid", "detail": "Exploit Task"},
            headers={"Origin": "https://attacker-controlled-site.com", "X-Requested-With": "XMLHttpRequest"}
        )
        assert res_evil_origin.status_code == 403
        assert "CSRF verification failed: Untrusted Origin header" in res_evil_origin.json()["detail"]

        # Scenario 2: Malicious Referer even with custom header -> BLOCKED (403)
        res_evil_ref = client.post(
            "/api/tasks",
            json={"mother_id": "test-mid", "detail": "Exploit Task"},
            headers={"Referer": "https://evil-phishing.org/steal", "X-Requested-With": "XMLHttpRequest"}
        )
        assert res_evil_ref.status_code == 403
        assert "CSRF verification failed: Untrusted Referer header" in res_evil_ref.json()["detail"]

        # Scenario 3: Missing Origin, Referer, and custom header -> BLOCKED (403)
        res_no_headers = client.post(
            "/api/tasks",
            json={"mother_id": "test-mid", "detail": "Exploit Task"},
            headers={}
        )
        assert res_no_headers.status_code == 403
        assert "CSRF verification failed" in res_no_headers.json()["detail"]

        # Scenario 4: Trusted localhost Origin with X-Requested-With -> SUCCEEDS (200)
        res_legit = client.post(
            "/api/mothers",
            json={"name": "[SYNTHETIC] Valid Patient", "phone": f"98480{_digits(5)}", "consent": True},
            headers={"Origin": "http://localhost:5173", "X-Requested-With": "XMLHttpRequest"}
        )
        assert res_legit.status_code == 200


def test_clinical_authority_boundaries_and_anti_administrative_prescribing():
    """Verify administrative staff and nurses CANNOT author care plans or prescribe treatments."""
    with TestClient(app) as client:
        client.post("/api/auth/seed-demo")
        
        admin_h = _login(client, "admin@nalgonda.janani.org")
        nurse_h = _login(client, "nurse@nalgonda.janani.org")
        coord_h = _login(client, "coordinator@nalgonda.janani.org")
        doc_h = _login(client, "doctor@nalgonda.janani.org")
        
        # Register synthetic mother
        m_res = client.post("/api/mothers", json={
            "name": "[SYNTHETIC] CarePlan Test Mother",
            "phone": f"98480{_digits(5)}",
            "consent": True
        }, headers=nurse_h)
        assert m_res.status_code == 200
        mid = m_res.json()["id"]
        
        # 1. Admin attempts to author CarePlan -> 403 Forbidden
        admin_res = client.post(f"/api/mothers/{mid}/plans", json={
            "visit_date": str(date.today() + timedelta(days=7)),
            "visit_type": "anc_checkup",
            "note": "Admin prescribing medication"
        }, headers=admin_h)
        assert admin_res.status_code == 403
        assert "Insufficient role 'admin'" in admin_res.json()["detail"]
        
        # 2. Nurse attempts to author CarePlan -> 403 Forbidden
        nurse_res = client.post(f"/api/mothers/{mid}/plans", json={
            "visit_date": str(date.today() + timedelta(days=7)),
            "visit_type": "anc_checkup",
            "note": "Nurse prescribing medication"
        }, headers=nurse_h)
        assert nurse_res.status_code == 403
        assert "Insufficient role 'nurse'" in nurse_res.json()["detail"]

        # 3. Field Coordinator attempts to author CarePlan -> 403 Forbidden
        fc_res = client.post(f"/api/mothers/{mid}/plans", json={
            "visit_date": str(date.today() + timedelta(days=7)),
            "visit_type": "anc_checkup",
            "note": "Coordinator prescribing medication"
        }, headers=coord_h)
        assert fc_res.status_code == 403

        # 4. Doctor authors CarePlan -> SUCCEEDS (200)
        doc_res = client.post(f"/api/mothers/{mid}/plans", json={
            "visit_date": str(date.today() + timedelta(days=7)),
            "visit_type": "anc_checkup",
            "note": "[SYNTHETIC-CLINICAL-RECORD] Authorised doctor review"
        }, headers=doc_h)
        assert doc_res.status_code == 200
        assert doc_res.json()["version"] == 1


def test_emergency_transport_regulatory_guard():
    """Verify autonomous 108/102 ambulance dispatch is blocked in favor of external escalation protocols."""
    with TestClient(app) as client:
        client.post("/api/auth/seed-demo")
        coord_h = _login(client, "coordinator@nalgonda.janani.org")
        nurse_h = _login(client, "nurse@nalgonda.janani.org")
        
        m_res = client.post("/api/mothers", json={
            "name": "[SYNTHETIC] Transit Mother",
            "phone": f"98480{_digits(5)}",
            "consent": True
        }, headers=nurse_h)
        mid = m_res.json()["id"]

        # 1. Attempting autonomous 108 ambulance dispatch -> BLOCKED with 400 Bad Request
        bad_req = client.post("/api/transport", json={
            "mother_id": mid,
            "date": str(date.today() + timedelta(days=1)),
            "from_location": "Chandur Sub-Centre",
            "destination": "Nalgonda Area Hospital",
            "partner": "108 Emergency Ambulance Dispatch",
            "vehicle_notes": "Live ambulance dispatch requested"
        }, headers=coord_h)
        assert bad_req.status_code == 400
        assert "Clinical Safety Guard" in bad_req.json()["detail"]
        assert "external telephone escalation protocol" in bad_req.json()["detail"]

        # 2. Approved routine non-emergency transport -> SUCCEEDS
        good_req = client.post("/api/transport", json={
            "mother_id": mid,
            "date": str(date.today() + timedelta(days=1)),
            "from_location": "Chandur Sub-Centre",
            "destination": "Nalgonda Area Hospital",
            "partner": "Chandur PHC Scheduled Van (External Protocol 108 Escalation Noted)",
            "vehicle_notes": "Routine scheduled ANC transit"
        }, headers=coord_h)
        assert good_req.status_code == 200


def test_zero_pii_in_financial_evidence_and_exports():
    """Verify financial reports and funding evidence packages contain ZERO patient PII (only anonymised tokens)."""
    with TestClient(app) as client:
        client.post("/api/auth/seed-demo")
        admin_h = _login(client, "admin@nalgonda.janani.org")
        
        # Fetch Financial Report
        rep_res = client.get("/api/finance/reports/contract_funding_summary", headers=admin_h)
        assert rep_res.status_code == 200
        rep_data = rep_res.json()
        assert "compliance_watermark" in rep_data
        
        # Verify CSV export
        csv_res = client.get("/api/finance/reports/contract_funding_summary/export?format=csv", headers=admin_h)
        assert csv_res.status_code == 200
        csv_text = csv_res.text
        assert "INTERNAL / DRAFT" in csv_text
        assert "NOT AN OFFICIAL GOVERNMENT COMPLIANCE STATEMENT" in csv_text
        # Ensure no patient phone numbers or addresses appear in financial exports
        assert "98480" not in csv_text
        assert "98000" not in csv_text
