"""Synthetic ANC card generator and labelled ground-truth evaluation benchmark for Phase 3."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
import random
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont
from pypdf import PdfWriter
from pypdf.generic import ContentStream, DecodedStreamObject, DictionaryObject, NameObject

from app.ocr_engine import PERMITTED_ADMIN_FIELDS, run_anc_ocr_pipeline

FIXTURE_SPECS: dict[str, dict[str, Any]] = {
    "printed_clear": {
        "id": "printed_clear",
        "title": "1. Clearly Printed ANC Card (Synthetic)",
        "description": (
            "Clean, high-contrast machine-printed Maternal & Child Protection (MCP/ANC) card "
            "with all 10 administrative fields clearly legible."
        ),
        "ground_truth": {
            "facility_name": "PHC Nalgonda",
            "patient_identifier": "ANC-2026-1042",
            "patient_name": "Sravani Goud",
            "contact_phone": "9800000101",
            "registration_date": "2026-06-15",
            "lmp_date": "2026-05-22",
            "edd_date": "2027-02-26",
            "visit_date": "2026-10-25",
            "follow_up_date": "2026-11-22",
            "address": "Ward 4 Devarakonda",
        },
        "lines": [
            "JANANISETU MATERNAL CARE ADMINISTRATIVE CARD (SYNTHETIC)",
            "Facility Name: PHC Nalgonda",
            "ANC Reg ID: ANC-2026-1042",
            "Patient Name: Sravani Goud",
            "Contact Phone: 9800000101",
            "Registration Date: 2026-06-15",
            "LMP Date: 2026-05-22",
            "EDD Date: 2027-02-26",
            "Visit Date: 2026-10-25",
            "Next Follow-up Date: 2026-11-22",
            "Address: Ward 4 Devarakonda",
        ],
    },
    "partially_handwritten": {
        "id": "partially_handwritten",
        "title": "2. Partially Handwritten ANC Card with Date Conflict (Synthetic)",
        "description": (
            "Printed labels with handwritten-style ink entries, updated contact phone, "
            "and two conflicting Next Follow-up Dates recorded on the card."
        ),
        "ground_truth": {
            "facility_name": "PHC Nalgonda",
            "patient_identifier": "ANC-2026-1042",
            "patient_name": "Sravani Goud",
            "contact_phone": "9800000199",
            "registration_date": "2026-06-15",
            "lmp_date": "2026-05-22",
            "edd_date": "2027-02-26",
            "visit_date": "2026-10-29",
            "follow_up_date": "2026-11-28",
            "address": "Ward 4 Devarakonda Sector B",
        },
        "lines": [
            "JANANISETU ANC VISIT RECORD - HANDWRITTEN UPDATE (SYNTHETIC)",
            "Facility Name: PHC Nalgonda",
            "ANC Reg ID: ANC-2026-1042",
            "Patient Name: Sravani Goud",
            "Contact Phone: 9800000199",
            "Registration Date: 2026-06-15",
            "LMP Date: 2026-05-22",
            "EDD Date: 2027-02-26",
            "Visit Date: 2026-10-29",
            "Next Follow-up Date: 2026-11-18",
            "Next Follow-up Date: 2026-11-28",
            "Address: Ward 4 Devarakonda Sector B",
        ],
    },
    "difficult_incomplete": {
        "id": "difficult_incomplete",
        "title": "3. Difficult / Incomplete Degraded Scan ANC Card (Synthetic)",
        "description": (
            "Low-contrast, noisy scan with missing EDD and Address, smudged phone number, "
            "and an invalid/ambiguous Visit Date requiring human correction or manual entry."
        ),
        "ground_truth": {
            "facility_name": "PHC Nalgonda",
            "patient_identifier": "ANC-2026-1088",
            "patient_name": "Meena Begum",
            "contact_phone": None,  # Smudged / illegible on scan
            "registration_date": "2026-04-10",
            "lmp_date": "2026-03-18",
            "edd_date": None,  # Missing on card — must NOT be inferred from LMP!
            "visit_date": None,  # Invalid date 2026-13-45 on scan
            "follow_up_date": "2026-11-15",
            "address": None,  # Missing on card
        },
        "lines": [
            "JANANISETU FIELD SCAN - DEGRADED SAMPLE (SYNTHETIC)",
            "Facility Name: PHC Nalgonda",
            "ANC Reg ID: ANC-2026-1088",
            "Patient Name: Meena Begum",
            "Contact Phone: 9800??illegible",
            "Registration Date: 2026-04-10",
            "LMP Date: 2026-03-18",
            "Visit Date: 2026-13-45",
            "Next Follow-up Date: 2026-11-15",
        ],
    },
}


def _load_fonts() -> tuple[Any, Any, Any]:
    try:
        header_font = ImageFont.truetype("arialbd.ttf", 24)
        body_font = ImageFont.truetype("arial.ttf", 22)
        hand_font = ImageFont.truetype("comic.ttf", 23)
    except Exception:
        try:
            header_font = ImageFont.truetype("arial.ttf", 24)
            body_font = ImageFont.truetype("arial.ttf", 22)
            hand_font = ImageFont.truetype("arial.ttf", 22)
        except Exception:
            try:
                # Linux fallback: Liberation Sans is metric-compatible with Arial (package fonts-liberation)
                header_font = ImageFont.truetype("LiberationSans-Bold.ttf", 24)
                body_font = ImageFont.truetype("LiberationSans-Regular.ttf", 22)
                hand_font = ImageFont.truetype("LiberationSans-Italic.ttf", 23)
            except Exception:
                header_font = ImageFont.load_default()
                body_font = ImageFont.load_default()
                hand_font = ImageFont.load_default()
    return header_font, body_font, hand_font


def generate_fixture_image_bytes(fixture_id: str) -> bytes:
    """Render a deterministic synthetic ANC card PNG image for the requested fixture ID."""
    if fixture_id not in FIXTURE_SPECS:
        raise ValueError(f"Unknown fixture_id: {fixture_id}")

    # Prefer the committed reference PNG so every host (Windows, Linux, Docker) evaluates the same
    # pixels; fall back to rendering only if the file is missing.
    bundled = Path(__file__).resolve().parent.parent / "data" / "fixtures" / f"{fixture_id}.png"
    if bundled.is_file():
        return bundled.read_bytes()

    spec = FIXTURE_SPECS[fixture_id]
    lines: list[str] = spec["lines"]
    header_font, body_font, hand_font = _load_fonts()

    width, height = 1050, 760
    bg_color = (255, 255, 255) if fixture_id != "difficult_incomplete" else (234, 232, 225)
    img = Image.new("RGB", (width, height), color=bg_color)
    draw = ImageDraw.Draw(img)

    # Card border & header box
    draw.rectangle([24, 24, width - 24, height - 24], outline=(20, 90, 82), width=3)
    draw.rectangle([24, 24, width - 24, 88], fill=(225, 242, 238), outline=(20, 90, 82), width=2)
    draw.text((48, 44), lines[0], fill=(15, 55, 50), font=header_font)

    rng = random.Random(42 if fixture_id == "partially_handwritten" else 99)

    y = 115
    for idx, line in enumerate(lines[1:]):
        if fixture_id == "printed_clear":
            draw.line([(44, y + 36), (width - 44, y + 36)], fill=(230, 236, 235), width=1)
            draw.text((52, y), line, fill=(15, 25, 30), font=body_font)
            y += 54
        elif fixture_id == "partially_handwritten":
            label_part, sep, val_part = line.partition(":")
            draw.line([(44, y + 38), (width - 44, y + 38)], fill=(220, 228, 230), width=1)
            # Printed label
            label_text = f"{label_part}{sep}"
            draw.text((52, y), label_text, fill=(30, 40, 45), font=body_font)
            # Simulated handwritten ink value with slight vertical jitter & blue-black ink
            val_x = 52 + len(label_text) * 12
            jitter_y = rng.randint(-2, 2)
            draw.text((val_x, y + jitter_y), val_part.strip(), fill=(18, 35, 110), font=hand_font)
            y += 50
        else:
            # Difficult / incomplete degraded scan
            jitter_x = rng.randint(-2, 3)
            draw.text((52 + jitter_x, y), line, fill=(65, 65, 65), font=body_font)
            y += 58

    if fixture_id == "difficult_incomplete":
        # Add deterministic scan speckle noise and slight blur to simulate difficult field scan
        px = img.load()
        if px is not None:
            for _ in range(4500):
                nx = rng.randint(30, width - 30)
                ny = rng.randint(95, height - 30)
                shade = rng.randint(120, 190)
                px[nx, ny] = (shade, shade, shade)
        img = img.filter(ImageFilter.GaussianBlur(radius=0.45))

    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def generate_fixture_pdf_bytes(fixture_id: str = "printed_clear") -> bytes:
    """Generate a valid single-page PDF containing the synthetic ANC card lines."""
    if fixture_id not in FIXTURE_SPECS:
        raise ValueError(f"Unknown fixture_id: {fixture_id}")
    lines = FIXTURE_SPECS[fixture_id]["lines"]

    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)

    font_dict = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    resources = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_dict}),
        }
    )
    page[NameObject("/Resources")] = resources

    content_ops = ["BT", "/F1 12 Tf", "50 730 Td", "18 TL"]
    for line in lines:
        escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        content_ops.append(f"({escaped}) Tj T*")
    content_ops.append("ET")
    stream_data = "\n".join(content_ops).encode("latin-1", errors="ignore")

    stream = DecodedStreamObject()
    stream.set_data(stream_data)
    page[NameObject("/Contents")] = stream

    out = BytesIO()
    writer.write(out)
    return out.getvalue()


def ensure_fixtures_on_disk(target_dir: Path) -> dict[str, Path]:
    """Write all 3 PNG fixtures and 1 PDF fixture to disk and return their file paths."""
    target_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for fid in FIXTURE_SPECS:
        p = target_dir / f"{fid}.png"
        p.write_bytes(generate_fixture_image_bytes(fid))
        paths[fid] = p
    pdf_path = target_dir / "printed_clear.pdf"
    pdf_path.write_bytes(generate_fixture_pdf_bytes("printed_clear"))
    paths["printed_clear_pdf"] = pdf_path
    return paths


def evaluate_fixtures_benchmark() -> dict[str, Any]:
    """Run real Tesseract OCR across all 3 synthetic ANC card fixtures and measure field accuracy."""
    fixture_reports: list[dict[str, Any]] = []
    total_expected_present = 0
    total_exact_matched = 0

    for fid, spec in FIXTURE_SPECS.items():
        img_bytes = generate_fixture_image_bytes(fid)
        res = run_anc_ocr_pipeline(img_bytes, "image/png")
        gt: dict[str, Any] = spec["ground_truth"]

        extracted_map = {f.field_key: f for f in res.fields}
        field_comparisons: list[dict[str, Any]] = []
        present_count = 0
        matched_count = 0

        for fkey, flabel in PERMITTED_ADMIN_FIELDS:
            expected_val = gt.get(fkey)
            cand = extracted_map.get(fkey)
            actual_val = (cand.normalized_value or cand.extracted_value) if cand else None

            if expected_val is not None:
                present_count += 1
                total_expected_present += 1
                is_match = (
                    actual_val is not None
                    and str(actual_val).strip().lower() == str(expected_val).strip().lower()
                )
                # For partially_handwritten follow_up_date, check if conflict detector caught both dates
                if (
                    fid == "partially_handwritten"
                    and fkey == "follow_up_date"
                    and cand is not None
                    and cand.conflict_detected
                    and expected_val in cand.conflicting_values
                ):
                    is_match = True
                if is_match:
                    matched_count += 1
                    total_exact_matched += 1
            else:
                # Expected missing or invalid (should have normalized_value == None and uncertainty_flag == True)
                is_match = bool(cand and cand.normalized_value is None and cand.uncertainty_flag)

            field_comparisons.append(
                {
                    "field_key": fkey,
                    "field_label": flabel,
                    "expected": expected_val,
                    "extracted_raw": cand.extracted_value if cand else None,
                    "normalized": cand.normalized_value if cand else None,
                    "confidence": cand.confidence if cand else None,
                    "uncertainty_flag": cand.uncertainty_flag if cand else True,
                    "conflict_detected": cand.conflict_detected if cand else False,
                    "matched_expectation": is_match,
                }
            )

        accuracy_pct = round((matched_count / present_count) * 100, 1) if present_count else 100.0
        fixture_reports.append(
            {
                "fixture_id": fid,
                "title": spec["title"],
                "ocr_status": res.ocr_status,
                "word_count": res.word_count,
                "mean_confidence": res.mean_confidence,
                "present_fields_expected": present_count,
                "present_fields_matched": matched_count,
                "field_accuracy_percent": accuracy_pct,
                "missing_fields_detected": res.missing_fields,
                "conflicts_detected": res.conflicts,
                "fields": field_comparisons,
            }
        )

    overall_accuracy = (
        round((total_exact_matched / total_expected_present) * 100, 1)
        if total_expected_present
        else 0.0
    )
    return {
        "engine": "tesseract-5",
        "overall_present_field_accuracy_percent": overall_accuracy,
        "total_expected_present_fields": total_expected_present,
        "total_matched_present_fields": total_exact_matched,
        "fixtures": fixture_reports,
    }

