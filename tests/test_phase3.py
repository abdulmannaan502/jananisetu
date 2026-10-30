"""Phase 3 automated test suite for JananiSetu:
- Phase 2 Security Hardening (X-Staff-ID disabled, demo endpoints blocked in prod, JWT revocation, password policy)
- Real ANC Card OCR (PNG & PDF, Tesseract 5 word-level bounding boxes & confidence)
- Malicious file & external vision safeguard blocking
- Missing, uncertain, and conflicting field detection (zero clinical inference)
- Evidence-linked field verification (accept, correct, reject, illegible_manual)
- Multi-version document management & administrative change proposals (never overwriting CarePlans)
- Cross-clinic document isolation, RBAC, and persistence across restart
"""
from __future__ import annotations

from datetime import date
import os
from pathlib import Path
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.anc_fixtures import generate_fixture_image_bytes, generate_fixture_pdf_bytes
from app.main import SessionLocal, app
from scripts.migrate_sqlite_to_postgres import migrate_data

client = TestClient(app)


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def setup_clinic(clinic_slug: str) -> dict[str, dict]:
    client.cookies.clear()
    res_admin = client.post(
        "/api/auth/register",
        json={
            "name": f"Admin {clinic_slug}",
            "email": f"admin@{clinic_slug}.org",
            "password": "Password@123",
            "role": "admin",
            "clinic": clinic_slug,
            "phone": "9100000001",
        },
    )
    assert res_admin.status_code == 200, res_admin.text
    admin_data = res_admin.json()
    admin_token = admin_data["access_token"]

    roles: dict[str, dict] = {
        "admin": {"token": admin_token, "staff": admin_data["staff"]},
    }

    for role in ("doctor", "nurse", "field_coordinator"):
        r = client.post(
            "/api/staff",
            headers=auth_headers(admin_token),
            json={
                "name": f"{role.title()} {clinic_slug}",
                "email": f"{role}@{clinic_slug}.org",
                "password": "Password@123",
                "role": role,
                "phone": "9100000009",
            },
        )
        assert r.status_code == 200, r.text
        login_res = client.post(
            "/api/auth/login",
            json={
                "identifier": f"{role}@{clinic_slug}.org",
                "password": "Password@123",
            },
        )
        assert login_res.status_code == 200, login_res.text
        roles[role] = {
            "token": login_res.json()["access_token"],
            "staff": login_res.json()["staff"],
        }

    client.cookies.clear()
    return roles


def test_phase2_security_hardening_and_token_revocation(monkeypatch):
    roles = setup_clinic("sec-phase3-clinic")
    admin_tok = roles["admin"]["token"]
    admin_id = roles["admin"]["staff"]["id"]
    nurse_tok = roles["nurse"]["token"]

    # 1. X-Staff-ID header cannot authenticate protected endpoints
    assert client.get("/api/mothers", headers={"X-Staff-ID": admin_id}).status_code == 401
    assert client.get("/api/staff", headers={"X-Staff-ID": admin_id}).status_code == 401
    assert client.get("/api/staff").status_code == 401

    # 2. Password policy rejects weak passwords (missing digits or <8 chars)
    weak_pw = client.post(
        "/api/staff",
        headers=auth_headers(admin_tok),
        json={
            "name": "Weak Pw Staff",
            "email": "weak@sec-phase3-clinic.org",
            "password": "onlyletters",
            "role": "nurse",
        },
    )
    assert weak_pw.status_code == 422

    # 3. Production environment disables demo endpoints and X-Staff-ID even if env var set
    monkeypatch.setenv("JANANI_ENV", "production")
    monkeypatch.setenv("JANANI_ALLOW_LEGACY_HEADER", "true")
    assert client.get("/api/auth/demo-accounts").status_code == 403
    assert client.post("/api/auth/seed-demo").status_code == 403
    assert client.get("/api/mothers", headers={"X-Staff-ID": admin_id}).status_code == 401
    monkeypatch.setenv("JANANI_ENV", "development")
    monkeypatch.setenv("JANANI_ALLOW_LEGACY_HEADER", "false")

    # 4. Token revocation via /api/auth/logout immediately invalidates the JWT
    assert client.get("/api/auth/me", headers=auth_headers(nurse_tok)).status_code == 200
    logout_res = client.post("/api/auth/logout", headers=auth_headers(nurse_tok))
    assert logout_res.status_code == 200
    assert client.get("/api/auth/me", headers=auth_headers(nurse_tok)).status_code == 401


def test_valid_image_and_pdf_uploads_and_ocr_extraction():
    roles = setup_clinic("ocr-valid-clinic")
    nurse_tok = roles["nurse"]["token"]

    mother = client.post(
        "/api/mothers",
        headers=auth_headers(nurse_tok),
        json={
            "name": "Sravani Goud",
            "phone": "9800000101",
            "patient_identifier": "ANC-2026-1042",
            "lmp": "2026-05-22",
            "edd": "2027-02-26",
            "address": "Ward 4 Devarakonda",
            "consent": True,
        },
    ).json()
    mid = mother["id"]

    # 1. Upload clearly printed synthetic ANC card (PNG)
    png_bytes = generate_fixture_image_bytes("printed_clear")
    up_png = client.post(
        f"/api/mothers/{mid}/documents",
        headers=auth_headers(nurse_tok),
        files={"file": ("fixture_1_printed.png", png_bytes, "image/png")},
    )
    assert up_png.status_code == 200, up_png.text
    doc_png = up_png.json()
    assert doc_png["version_number"] == 1
    assert doc_png["confirmed"] is False
    assert doc_png["ocr_status"] in ("completed", "completed_with_warnings")
    assert doc_png["ocr_job"]["word_count"] >= 20
    assert doc_png["ocr_job"]["mean_confidence"] >= 80.0

    fields_by_key = {f["field_key"]: f for f in doc_png["fields"]}
    assert fields_by_key["patient_name"]["extracted_value"] == "Sravani Goud"
    assert fields_by_key["patient_identifier"]["extracted_value"] == "ANC-2026-1042"
    assert fields_by_key["contact_phone"]["normalized_value"] == "9800000101"
    assert fields_by_key["lmp_date"]["normalized_value"] == "2026-05-22"
    assert fields_by_key["edd_date"]["normalized_value"] == "2027-02-26"
    assert fields_by_key["follow_up_date"]["normalized_value"] == "2026-11-22"

    # Verify source bounding box coordinates and FieldSourceLocation records exist
    for key in ("patient_name", "patient_identifier", "lmp_date", "follow_up_date"):
        f_obj = fields_by_key[key]
        assert f_obj["bbox_x"] is not None and f_obj["bbox_y"] is not None
        assert f_obj["bbox_w"] > 0 and f_obj["bbox_h"] > 0
        assert len(f_obj["source_locations"]) >= 1

    # 2. Upload valid PDF ANC card (version 2)
    pdf_bytes = generate_fixture_pdf_bytes("printed_clear")
    up_pdf = client.post(
        f"/api/mothers/{mid}/documents",
        headers=auth_headers(nurse_tok),
        files={"file": ("fixture_1_printed.pdf", pdf_bytes, "application/pdf")},
    )
    assert up_pdf.status_code == 200, up_pdf.text
    doc_pdf = up_pdf.json()
    assert doc_pdf["version_number"] == 2
    assert doc_pdf["supersedes_document_id"] == doc_png["id"]
    assert doc_pdf["content_type"] == "application/pdf"
    assert doc_pdf["page_count"] == 1

    # Verify both raw PDF download and rendered PNG preview image work
    raw_dl = client.get(f"/api/documents/{doc_pdf['id']}/file", headers=auth_headers(nurse_tok))
    assert raw_dl.status_code == 200
    assert raw_dl.headers["content-type"] == "application/pdf"
    assert raw_dl.content.startswith(b"%PDF-")

    prev_dl = client.get(f"/api/documents/{doc_pdf['id']}/preview", headers=auth_headers(nurse_tok))
    assert prev_dl.status_code == 200
    assert prev_dl.headers["content-type"] == "image/png"
    assert prev_dl.content.startswith(b"\x89PNG")


def test_unsupported_malicious_and_external_provider_safeguards():
    roles = setup_clinic("ocr-sec-clinic")
    nurse_tok = roles["nurse"]["token"]

    mother = client.post(
        "/api/mothers",
        headers=auth_headers(nurse_tok),
        json={"name": "Sec Mother", "phone": "9800000555", "consent": False},
    ).json()
    mid = mother["id"]

    # 1. Unsupported MIME type (415)
    r_html = client.post(
        f"/api/mothers/{mid}/documents",
        headers=auth_headers(nurse_tok),
        files={"file": ("evil.html", b"<html><script>alert(1)</script></html>", "text/html")},
    )
    assert r_html.status_code == 415

    # 2. Disguised Windows PE executable with PNG content-type (422)
    r_exe = client.post(
        f"/api/mothers/{mid}/documents",
        headers=auth_headers(nurse_tok),
        files={"file": ("fake.png", b"MZ\x90\x00\x03\x00\x00\x00", "image/png")},
    )
    assert r_exe.status_code == 422

    # 3. Malicious PDF with embedded /JavaScript action (422)
    malicious_pdf = b"%PDF-1.4\n1 0 obj << /Type /Catalog /OpenAction << /S /JavaScript /JS (app.alert(1)) >> >> endobj\n%%EOF"
    r_bad_pdf = client.post(
        f"/api/mothers/{mid}/documents",
        headers=auth_headers(nurse_tok),
        files={"file": ("exploit.pdf", malicious_pdf, "application/pdf")},
    )
    assert r_bad_pdf.status_code == 422

    # 4. Oversized file > 5 MB (413)
    big_bytes = b"\x89PNG\r\n\x1a\n" + (b"0" * 5_000_010)
    r_big = client.post(
        f"/api/mothers/{mid}/documents",
        headers=auth_headers(nurse_tok),
        files={"file": ("huge.png", big_bytes, "image/png")},
    )
    assert r_big.status_code == 413

    # 5. External vision provider blocked without explicit config & consent (403)
    png_bytes = generate_fixture_image_bytes("printed_clear")
    r_ext = client.post(
        f"/api/mothers/{mid}/documents?use_external_provider=true",
        headers=auth_headers(nurse_tok),
        files={"file": ("card.png", png_bytes, "image/png")},
    )
    assert r_ext.status_code == 403

    # 6. Simulated OCR engine failure records failed status and error message gracefully
    r_fail = client.post(
        f"/api/mothers/{mid}/documents?simulate_ocr_failure=true",
        headers=auth_headers(nurse_tok),
        files={"file": ("card.png", png_bytes, "image/png")},
    )
    assert r_fail.status_code == 200
    assert r_fail.json()["ocr_status"] == "failed"
    assert r_fail.json()["ocr_job"]["status"] == "failed"
    assert "failed" in r_fail.json()["ocr_error"].lower()


def test_missing_uncertain_conflicting_fields_and_no_clinical_inference():
    roles = setup_clinic("ocr-conflict-clinic")
    nurse_tok = roles["nurse"]["token"]

    mother = client.post(
        "/api/mothers",
        headers=auth_headers(nurse_tok),
        json={
            "name": "Meena Begum",
            "phone": "9800000102",
            "patient_identifier": "ANC-2026-1088",
            "consent": True,
        },
    ).json()
    mid = mother["id"]

    # 1. Upload Fixture 3 (Difficult / Incomplete card: has LMP 2026-03-18, missing EDD, invalid Visit Date 2026-13-45)
    doc3 = client.post(
        f"/api/mothers/{mid}/documents/fixture/difficult_incomplete",
        headers=auth_headers(nurse_tok),
    )
    assert doc3.status_code == 200, doc3.text
    d3 = doc3.json()
    fmap3 = {f["field_key"]: f for f in d3["fields"]}

    # LMP was extracted, EDD is missing -> MUST NOT infer EDD from LMP!
    assert fmap3["lmp_date"]["normalized_value"] == "2026-03-18"
    assert fmap3["edd_date"]["extracted_value"] is None
    assert fmap3["edd_date"]["normalized_value"] is None
    assert "edd_date" in d3["ocr_job"]["missing_fields"]
    assert "address" in d3["ocr_job"]["missing_fields"]

    # Invalid calendar date 2026-13-45 must NOT be normalized to an invented date
    assert fmap3["visit_date"]["extracted_value"] == "2026-13-45"
    assert fmap3["visit_date"]["normalized_value"] is None
    assert fmap3["visit_date"]["uncertainty_flag"] is True

    # Attempting to "accept" an invalid date or missing field without correction must fail (422)
    visit_fid = fmap3["visit_date"]["id"]
    bad_accept = client.patch(
        f"/api/documents/{d3['id']}/fields/{visit_fid}",
        headers=auth_headers(nurse_tok),
        json={"decision": "accepted"},
    )
    assert bad_accept.status_code == 422

    # 2. Upload Fixture 2 (Partially handwritten card with 2 conflicting Next Follow-up Dates)
    doc2 = client.post(
        f"/api/mothers/{mid}/documents/fixture/partially_handwritten",
        headers=auth_headers(nurse_tok),
    )
    assert doc2.status_code == 200
    d2 = doc2.json()
    fmap2 = {f["field_key"]: f for f in d2["fields"]}
    assert fmap2["follow_up_date"]["conflict_detected"] is True
    assert "2026-11-18" in fmap2["follow_up_date"]["conflicting_values"]
    assert len(fmap2["follow_up_date"]["conflicting_values"]) == 2
    assert fmap2["visit_date"]["uncertainty_flag"] is True


def test_human_verification_versioning_and_change_proposals():
    roles = setup_clinic("ocr-verify-clinic")
    doc_tok = roles["doctor"]["token"]
    nurse_tok = roles["nurse"]["token"]

    # Register mother with initial phone 9800000101 and Doctor-approved CarePlan for 2026-11-10
    mother = client.post(
        "/api/mothers",
        headers=auth_headers(nurse_tok),
        json={
            "name": "Sravani Goud",
            "phone": "9800000101",
            "patient_identifier": "ANC-2026-1042",
            "lmp": "2026-05-22",
            "edd": "2027-02-26",
            "address": "Ward 4 Devarakonda",
            "consent": True,
        },
    ).json()
    mid = mother["id"]

    plan = client.post(
        f"/api/mothers/{mid}/plans",
        headers=auth_headers(doc_tok),
        json={"visit_date": "2026-11-10", "note": "Authoritative doctor plan"},
    ).json()

    # Upload Version 1 (printed_clear) and confirm it
    v1 = client.post(
        f"/api/mothers/{mid}/documents/fixture/printed_clear",
        headers=auth_headers(nurse_tok),
    ).json()
    assert v1["version_number"] == 1

    # Verify individual fields using accept, correct, reject, illegible_manual
    v1_fields = {f["field_key"]: f for f in v1["fields"]}

    # Accept patient_name
    r_acc = client.patch(
        f"/api/documents/{v1['id']}/fields/{v1_fields['patient_name']['id']}",
        headers=auth_headers(nurse_tok),
        json={"decision": "accepted", "reviewer_note": "Matches card"},
    )
    assert r_acc.status_code == 200

    # Confirm Version 1
    client.patch(
        f"/api/documents/{v1['id']}/confirm",
        headers=auth_headers(nurse_tok),
        json={
            "field_decisions": [
                {"field_key": "patient_name", "decision": "accepted"},
                {"field_key": "contact_phone", "decision": "accepted"},
                {"field_key": "lmp_date", "decision": "accepted"},
            ]
        },
    )

    # Now upload Version 2 (partially_handwritten) which has updated phone 9800000199 and follow_up_date 2026-11-28
    v2 = client.post(
        f"/api/mothers/{mid}/documents/fixture/partially_handwritten",
        headers=auth_headers(nurse_tok),
    ).json()
    assert v2["version_number"] == 2
    assert v2["supersedes_document_id"] == v1["id"]
    assert len(v2["versions"]) == 2

    # Ensure unconfirmed upload did NOT overwrite Mother's phone (still 9800000101)
    m_before = client.get(f"/api/mothers/{mid}", headers=auth_headers(nurse_tok)).json()
    assert m_before["phone"] == "9800000101"

    # Exercise all 4 field verification statuses on Version 2
    v2_fields = {f["field_key"]: f for f in v2["fields"]}
    # 1. Accept contact_phone (9800000199)
    client.patch(
        f"/api/documents/{v2['id']}/fields/{v2_fields['contact_phone']['id']}",
        headers=auth_headers(nurse_tok),
        json={"decision": "accepted"},
    )
    # 2. Correct conflicting follow_up_date to 2026-11-28
    client.patch(
        f"/api/documents/{v2['id']}/fields/{v2_fields['follow_up_date']['id']}",
        headers=auth_headers(nurse_tok),
        json={"decision": "corrected", "final_value": "2026-11-28", "reviewer_note": "Confirmed second line"},
    )
    # 3. Reject registration_date
    client.patch(
        f"/api/documents/{v2['id']}/fields/{v2_fields['registration_date']['id']}",
        headers=auth_headers(nurse_tok),
        json={"decision": "rejected", "reviewer_note": "Not needed for this update"},
    )
    # 4. Mark address as illegible_manual and enter clean text
    client.patch(
        f"/api/documents/{v2['id']}/fields/{v2_fields['address']['id']}",
        headers=auth_headers(nurse_tok),
        json={
            "decision": "illegible_manual",
            "final_value": "Ward 4 Devarakonda Sector B (Verified)",
            "reviewer_note": "Handwriting manually transcribed",
        },
    )

    # Confirm Version 2 document
    conf_v2 = client.patch(
        f"/api/documents/{v2['id']}/confirm",
        headers=auth_headers(nurse_tok),
        json={"corrected_text": v2["extracted_text"]},
    )
    assert conf_v2.status_code == 200
    conf_data = conf_v2.json()
    assert conf_data["confirmed"] is True

    # Crucial check: Even after document confirmation, Mother.phone is NOT automatically overwritten
    # until the AdminChangeProposal is explicitly reviewed and approved!
    m_mid_check = client.get(f"/api/mothers/{mid}", headers=auth_headers(nurse_tok)).json()
    assert m_mid_check["phone"] == "9800000101"

    proposals = conf_data["change_proposals"]
    prop_by_key = {p["field_key"]: p for p in proposals}
    assert "contact_phone" in prop_by_key
    assert prop_by_key["contact_phone"]["previous_value"] == "9800000101"
    assert prop_by_key["contact_phone"]["proposed_value"] == "9800000199"
    assert prop_by_key["contact_phone"]["status"] == "pending"

    assert "follow_up_date" in prop_by_key
    assert prop_by_key["follow_up_date"]["proposal_type"] == "appointment_schedule_note"

    # Approve contact_phone change proposal -> updates Mother.phone and records reviewer
    approve_phone = client.post(
        f"/api/change-proposals/{prop_by_key['contact_phone']['id']}/decide",
        headers=auth_headers(nurse_tok),
        json={"decision": "approved", "review_note": "Patient confirmed new number"},
    )
    assert approve_phone.status_code == 200
    assert approve_phone.json()["status"] == "approved"
    assert approve_phone.json()["reviewed_by"] == roles["nurse"]["staff"]["id"]

    # Approve follow_up_date note proposal -> MUST NOT overwrite doctor-authorised CarePlan!
    approve_fu = client.post(
        f"/api/change-proposals/{prop_by_key['follow_up_date']['id']}/decide",
        headers=auth_headers(doc_tok),
        json={"decision": "approved", "review_note": "Noted on chart"},
    )
    assert approve_fu.status_code == 200

    m_after = client.get(f"/api/mothers/{mid}", headers=auth_headers(nurse_tok)).json()
    assert m_after["phone"] == "9800000199"
    active_plans = [p for p in m_after["plans"] if p["active"]]
    assert len(active_plans) == 1
    assert active_plans[0]["id"] == plan["id"]
    assert active_plans[0]["visit_date"] == "2026-11-10"


def test_cross_clinic_and_role_based_document_isolation_and_persistence():
    clinic_1 = setup_clinic("doc-iso-clinic-1")
    clinic_2 = setup_clinic("doc-iso-clinic-2")

    c1_nurse = clinic_1["nurse"]["token"]
    c1_fc = clinic_1["field_coordinator"]["token"]
    c2_admin = clinic_2["admin"]["token"]
    c2_doc = clinic_2["doctor"]["token"]

    # Field coordinator uploads a scan in Clinic 1
    m1 = client.post(
        "/api/mothers",
        headers=auth_headers(c1_fc),
        json={"name": "Clinic 1 Mother", "phone": "9800000777", "consent": True},
    ).json()
    doc1 = client.post(
        f"/api/mothers/{m1['id']}/documents/fixture/printed_clear",
        headers=auth_headers(c1_fc),
    ).json()
    did = doc1["id"]
    fid = doc1["fields"][0]["id"]

    # 1. Field coordinator CANNOT verify fields or confirm documents (403)
    assert (
        client.patch(
            f"/api/documents/{did}/fields/{fid}",
            headers=auth_headers(c1_fc),
            json={"decision": "accepted"},
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"/api/documents/{did}/confirm",
            headers=auth_headers(c1_fc),
            json={"corrected_text": "FC attempt"},
        ).status_code
        == 403
    )

    # 2. Clinic 2 Admin/Doctor CANNOT view, download, preview, or confirm Clinic 1's document (404)
    assert client.get(f"/api/documents/{did}", headers=auth_headers(c2_admin)).status_code == 404
    assert client.get(f"/api/documents/{did}/file", headers=auth_headers(c2_admin)).status_code == 404
    assert client.get(f"/api/documents/{did}/preview", headers=auth_headers(c2_admin)).status_code == 404
    assert (
        client.patch(
            f"/api/documents/{did}/fields/{fid}",
            headers=auth_headers(c2_doc),
            json={"decision": "accepted"},
        ).status_code
        == 404
    )
    assert (
        client.patch(
            f"/api/documents/{did}/confirm",
            headers=auth_headers(c2_doc),
            json={"corrected_text": "Cross clinic"},
        ).status_code
        == 404
    )

    # 3. Verify persistence across new TestClient / DB session restart
    fresh_client = TestClient(app)
    persisted = fresh_client.get(f"/api/documents/{did}", headers=auth_headers(c1_nurse))
    assert persisted.status_code == 200
    assert persisted.json()["id"] == did
    assert len(persisted.json()["fields"]) == 10

    # 4. Run live OCR benchmark evaluation endpoint
    eval_res = fresh_client.get("/api/documents/fixtures/evaluate", headers=auth_headers(c1_nurse))
    assert eval_res.status_code == 200
    eval_data = eval_res.json()
    assert eval_data["overall_present_field_accuracy_percent"] >= 85.0
    assert len(eval_data["fixtures"]) == 3
