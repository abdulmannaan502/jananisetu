"""Production-grade open-source ANC card OCR, PDF handling, and administrative field extractor.

STRICT CLINICAL & PRIVACY SAFEGUARDS:
- Extracts ONLY permitted administrative fields (name, IDs, dates, contact, facility, follow-up date).
- NEVER infers missing dates (e.g. never computes EDD from LMP) or clinical risk/diagnosis.
- NEVER sends documents to any external vision API without explicit configuration and data safeguard ack.
- Preserves word-level bounding boxes, confidence scores, missing-field flags, and conflict indicators.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
import time
from typing import Any, Optional

from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader
import pytesseract

from app.config import get_settings

# Protect against decompression bombs
Image.MAX_IMAGE_PIXELS = 25_000_000

PERMITTED_ADMIN_FIELDS: list[tuple[str, str]] = [
    ("patient_name", "Patient Name"),
    ("patient_identifier", "ANC / Mother ID"),
    ("contact_phone", "Contact Phone"),
    ("facility_name", "Facility / Clinic Name"),
    ("registration_date", "Registration Date"),
    ("lmp_date", "Documented LMP Date"),
    ("edd_date", "Documented EDD Date"),
    ("visit_date", "Documented Visit Date"),
    ("follow_up_date", "Next Follow-up Appointment Date"),
    ("address", "Village / Ward Address"),
]

FIELD_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "patient_name": [
        re.compile(r"^(?:patient\s*name|mother(?:'s)?\s*name|beneficiary\s*name|name)\s*[:\-]\s*(.+)$", re.I),
    ],
    "patient_identifier": [
        re.compile(r"^(?:anc\s*(?:reg(?:istration)?)?\s*(?:id|no|number)|rch\s*id|mother\s*id|patient\s*id)\s*[:\-]\s*(.+)$", re.I),
    ],
    "contact_phone": [
        re.compile(r"^(?:contact\s*(?:phone|no|number)?|phone(?:\s*number)?|mobile(?:\s*no)?|tel)\s*[:\-]\s*(.+)$", re.I),
    ],
    "facility_name": [
        re.compile(r"^(?:facility(?:\s*name)?|clinic(?:\s*name)?|phc|chc|hospital)\s*[:\-]\s*(.+)$", re.I),
    ],
    "registration_date": [
        re.compile(r"^(?:registration\s*date|reg\.?\s*date|date\s*of\s*registration)\s*[:\-]\s*(.+)$", re.I),
    ],
    "lmp_date": [
        re.compile(r"^(?:lmp(?:\s*date)?|last\s*menstrual\s*period)\s*[:\-]\s*(.+)$", re.I),
    ],
    "edd_date": [
        re.compile(r"^(?:edd(?:\s*date)?|expected\s*delivery\s*date)\s*[:\-]\s*(.+)$", re.I),
    ],
    "visit_date": [
        re.compile(r"^(?:visit\s*date|anc\s*visit\s*date|checkup\s*date|date\s*of\s*visit)\s*[:\-]\s*(.+)$", re.I),
    ],
    "follow_up_date": [
        re.compile(r"^(?:next\s*(?:follow[\-\s]?up|visit)\s*(?:date)?|follow[\-\s]?up\s*(?:appointment\s*)?date|next\s*appointment)\s*[:\-]\s*(.+)$", re.I),
    ],
    "address": [
        re.compile(r"^(?:address|village(?:\s*\/\s*ward)?|habitation|ward)\s*[:\-]\s*(.+)$", re.I),
    ],
}

DATE_FIELD_KEYS = {
    "registration_date",
    "lmp_date",
    "edd_date",
    "visit_date",
    "follow_up_date",
}


@dataclass
class OcrToken:
    text: str
    conf: float
    x: int
    y: int
    w: int
    h: int
    line_key: tuple[int, int, int]
    page: int = 1


@dataclass
class ExtractedFieldCandidate:
    field_key: str
    field_label: str
    extracted_value: Optional[str] = None
    normalized_value: Optional[str] = None
    confidence: Optional[float] = None
    uncertainty_flag: bool = False
    uncertainty_reason: str = ""
    conflict_detected: bool = False
    conflicting_values: list[str] = field(default_factory=list)
    source_page: int = 1
    bbox_x: Optional[int] = None
    bbox_y: Optional[int] = None
    bbox_w: Optional[int] = None
    bbox_h: Optional[int] = None
    source_snippet: str = ""
    tokens: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class OcrExtractionResult:
    ocr_status: str
    ocr_engine: str
    extracted_text: str
    image_width: int
    image_height: int
    page_count: int
    duration_ms: int
    word_count: int
    mean_confidence: Optional[float]
    fields: list[ExtractedFieldCandidate]
    missing_fields: list[str]
    conflicts: list[dict[str, Any]]
    raw_tokens: list[dict[str, Any]]
    error_message: str = ""
    preview_png_bytes: bytes = b""


class DocumentValidationError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def validate_and_inspect_upload(
    filename: str,
    content_type: str,
    contents: bytes,
) -> tuple[str, str]:
    """Validate file size, magic bytes, image/PDF structure, and reject malicious payloads."""
    if not contents:
        raise DocumentValidationError(422, "Uploaded file is empty")
    if len(contents) > 5_000_000:
        raise DocumentValidationError(413, "Maximum file size is 5 MB")

    allowed_types = {
        "image/jpeg",
        "image/jpg",
        "image/png",
        "image/webp",
        "application/pdf",
    }
    norm_ct = (content_type or "").lower().strip()
    if norm_ct == "image/jpg":
        norm_ct = "image/jpeg"

    if norm_ct not in allowed_types:
        raise DocumentValidationError(
            415, "Only JPEG, PNG, WEBP images or PDF documents are supported"
        )

    # Check for disguised script/executable headers
    head_bytes = contents[:512].lstrip()
    forbidden_prefixes = (b"MZ", b"\x7fELF", b"<!DOCTYPE", b"<html", b"<script", b"<?php")
    for prefix in forbidden_prefixes:
        if head_bytes.lower().startswith(prefix.lower()):
            raise DocumentValidationError(422, "Malicious or executable content rejected")

    sha256_hex = hashlib.sha256(contents).hexdigest()

    if norm_ct == "application/pdf":
        if not contents.startswith(b"%PDF-"):
            raise DocumentValidationError(422, "Invalid PDF header signature")
        # Scan raw PDF bytes for dangerous active content tags
        lower_pdf = contents.lower()
        for dangerous_tag in (b"/javascript", b"/js ", b"/js(", b"/js<", b"/launch", b"/richmedia"):
            if dangerous_tag in lower_pdf:
                raise DocumentValidationError(
                    422, "PDF rejected: active script or launch actions are prohibited"
                )
        try:
            reader = PdfReader(BytesIO(contents), strict=False)
            if len(reader.pages) < 1:
                raise DocumentValidationError(422, "PDF contains no pages")
            if len(reader.pages) > 10:
                raise DocumentValidationError(422, "PDF exceeds maximum 10 pages")
        except DocumentValidationError:
            raise
        except Exception as exc:
            raise DocumentValidationError(422, f"Corrupted or invalid PDF: {exc}") from exc
    else:
        # Verify magic bytes match image format
        is_png = contents.startswith(b"\x89PNG\r\n\x1a\n")
        is_jpeg = contents.startswith(b"\xff\xd8\xff")
        is_webp = contents.startswith(b"RIFF") and contents[8:12] == b"WEBP"
        if not (is_png or is_jpeg or is_webp):
            raise DocumentValidationError(422, "Invalid image magic bytes")
        try:
            pic = Image.open(BytesIO(contents))
            pic.verify()
        except Exception as exc:
            raise DocumentValidationError(422, f"Invalid or corrupted image: {exc}") from exc

    return norm_ct, sha256_hex


def _render_text_lines_to_image(lines: list[str], width: int = 1000) -> Image.Image:
    """Render extracted PDF text lines onto a clean page canvas for visual review and OCR bbox mapping."""
    line_height = 38
    height = max(720, 100 + len(lines) * line_height)
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 22)
    except Exception:
        font = ImageFont.load_default()

    # Draw subtle ANC card border
    draw.rectangle([20, 20, width - 20, height - 20], outline=(180, 200, 198), width=2)
    y = 48
    for line in lines:
        draw.text((48, y), line, fill=(15, 25, 30), font=font)
        y += line_height
    return img


def _prepare_image_from_upload(
    contents: bytes,
    content_type: str,
) -> tuple[Image.Image, int, str, list[str]]:
    """Convert uploaded image or PDF page into a standardized RGB PIL Image for OCR and preview."""
    pdf_native_lines: list[str] = []
    if content_type == "application/pdf":
        reader = PdfReader(BytesIO(contents), strict=False)
        page_count = len(reader.pages)
        first_page = reader.pages[0]

        # 1. Check if the PDF page has embedded scanned images
        try:
            images = list(first_page.images)
        except Exception:
            images = []

        if images:
            img_obj = Image.open(BytesIO(images[0].data)).convert("RGB")
            return img_obj, page_count, "pypdf+tesseract-5", pdf_native_lines

        # 2. Extract digital text from PDF page and render to visual canvas for preview + bbox indexing
        raw_text = first_page.extract_text() or ""
        pdf_native_lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]
        rendered = _render_text_lines_to_image(
            pdf_native_lines or ["[Empty PDF Page]"]
        )
        return rendered, page_count, "pypdf+tesseract-5", pdf_native_lines

    img_obj = Image.open(BytesIO(contents)).convert("RGB")
    return img_obj, 1, "tesseract-5", pdf_native_lines


def _parse_strict_date(raw_val: str) -> tuple[Optional[str], Optional[str]]:
    """Parse an explicit date string into YYYY-MM-DD without guessing or inventing dates.

    Returns (iso_date_or_none, error_reason_or_none).
    """
    cleaned = raw_val.strip()
    if not cleaned:
        return None, "Empty date value"

    # Reject strings containing question marks or explicit illegibility markers
    if "?" in cleaned or "illegible" in cleaned.lower() or "unclear" in cleaned.lower():
        return None, f"Illegible or uncertain date text: '{cleaned}'"

    # Extract potential date token
    m_iso = re.search(r"\b(\d{4})[\-\/\.](\d{1,2})[\-\/\.](\d{1,2})\b", cleaned)
    if m_iso:
        y, m, d = int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3))
        try:
            dt = date(y, m, d)
            if 1990 <= dt.year <= 2035:
                return dt.isoformat(), None
            return None, f"Date year out of plausible range: '{cleaned}'"
        except ValueError:
            return None, f"Invalid calendar date on card: '{cleaned}'"

    m_dmy = re.search(r"\b(\d{1,2})[\-\/\.](\d{1,2})[\-\/\.](\d{4})\b", cleaned)
    if m_dmy:
        d, m, y = int(m_dmy.group(1)), int(m_dmy.group(2)), int(m_dmy.group(3))
        try:
            dt = date(y, m, d)
            if 1990 <= dt.year <= 2035:
                return dt.isoformat(), None
            return None, f"Date year out of plausible range: '{cleaned}'"
        except ValueError:
            return None, f"Invalid calendar date on card: '{cleaned}'"

    return None, f"Unrecognized or incomplete date format: '{cleaned}'"


def _normalize_phone(raw_val: str) -> tuple[Optional[str], Optional[str]]:
    cleaned = raw_val.strip()
    if "?" in cleaned or "illegible" in cleaned.lower():
        return None, f"Illegible phone number: '{cleaned}'"
    digits = re.sub(r"[^\d+]", "", cleaned)
    only_digits = re.sub(r"\D", "", digits)
    if 10 <= len(only_digits) <= 13:
        return only_digits[-10:], None
    if 8 <= len(only_digits) < 10:
        return only_digits, f"Phone length ({len(only_digits)} digits) requires verification"
    return None, f"Invalid or incomplete phone number: '{cleaned}'"


def run_anc_ocr_pipeline(
    contents: bytes,
    content_type: str,
    existing_mother: Optional[dict[str, Any]] = None,
    previous_confirmed_fields: Optional[dict[str, Any]] = None,
    request_external_provider: bool = False,
    mother_consent: bool = False,
    simulate_ocr_failure: bool = False,
) -> OcrExtractionResult:
    """Execute the full ANC card OCR, bounding-box mapping, and conflict detection pipeline."""
    t0 = time.perf_counter()
    settings = get_settings()

    # Check external vision provider safeguard
    if request_external_provider or settings.external_ocr_enabled:
        if not (
            settings.external_ocr_enabled
            and settings.external_ocr_data_safeguard_ack
            and mother_consent
            and settings.external_ocr_provider_url
        ):
            raise PermissionError(
                "External vision provider blocked: patient documents cannot be transmitted "
                "to a third-party API without JANANI_EXTERNAL_OCR_ENABLED=true, "
                "JANANI_EXTERNAL_OCR_DATA_SAFEGUARD_ACK=true, and recorded patient consent."
            )

    img_obj, page_count, engine_name, pdf_native_lines = _prepare_image_from_upload(
        contents, content_type
    )
    width, height = img_obj.size

    preview_buf = BytesIO()
    img_obj.save(preview_buf, format="PNG")
    preview_bytes = preview_buf.getvalue()

    tokens: list[OcrToken] = []
    ocr_error = ""
    ocr_status = "completed"

    if simulate_ocr_failure:
        ocr_status = "failed"
        ocr_error = "OCR engine execution failed: simulated engine failure or unreadable image stream."
    else:
        try:
            pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd
            data = pytesseract.image_to_data(
                img_obj,
                output_type=pytesseract.Output.DICT,
                timeout=15,
            )
            n_boxes = len(data.get("text", []))
            for i in range(n_boxes):
                raw_txt = str(data["text"][i] or "").strip()
                if not raw_txt:
                    continue
                try:
                    conf_val = float(data["conf"][i])
                except (ValueError, TypeError):
                    conf_val = -1.0
                if conf_val < 0:
                    conf_val = 0.0
                line_key = (
                    int(data["block_num"][i]),
                    int(data["par_num"][i]),
                    int(data["line_num"][i]),
                )
                tokens.append(
                    OcrToken(
                        text=raw_txt,
                        conf=round(conf_val, 1),
                        x=int(data["left"][i]),
                        y=int(data["top"][i]),
                        w=int(data["width"][i]),
                        h=int(data["height"][i]),
                        line_key=line_key,
                        page=1,
                    )
                )
        except Exception as exc:
            ocr_status = "failed"
            ocr_error = f"OCR engine unavailable or failed: {exc}"

    # Group tokens by line
    lines_map: dict[tuple[int, int, int], list[OcrToken]] = {}
    for tok in tokens:
        lines_map.setdefault(tok.line_key, []).append(tok)

    reconstructed_lines: list[tuple[str, list[OcrToken]]] = []
    for _, line_tokens in lines_map.items():
        line_str = " ".join(t.text for t in line_tokens).strip()
        if line_str:
            reconstructed_lines.append((line_str, line_tokens))

    if not reconstructed_lines and pdf_native_lines and ocr_status != "failed":
        for idx, pline in enumerate(pdf_native_lines):
            fake_tok = OcrToken(
                text=pline,
                conf=95.0,
                x=48,
                y=48 + idx * 38,
                w=min(width - 96, max(120, len(pline) * 11)),
                h=28,
                line_key=(1, 1, idx + 1),
                page=1,
            )
            reconstructed_lines.append((pline, [fake_tok]))
            tokens.append(fake_tok)

    full_extracted_text = "\n".join(ln for ln, _ in reconstructed_lines)
    if not full_extracted_text.strip() and ocr_status != "failed":
        ocr_status = "completed_with_warnings"

    # Match permitted administrative fields from reconstructed lines
    matches_by_key: dict[str, list[tuple[str, str, list[OcrToken]]]] = {
        k: [] for k, _ in PERMITTED_ADMIN_FIELDS
    }

    for line_str, line_tokens in reconstructed_lines:
        for field_key, patterns in FIELD_PATTERNS.items():
            for pat in patterns:
                m = pat.match(line_str)
                if m:
                    raw_val = m.group(1).strip()
                    # Find value tokens (tokens after colon/hyphen if present, else all line tokens)
                    val_tokens: list[OcrToken] = []
                    colon_seen = False
                    for lt in line_tokens:
                        if colon_seen:
                            val_tokens.append(lt)
                        elif ":" in lt.text or lt.text == "-":
                            colon_seen = True
                            after = lt.text.partition(":")[2].strip()
                            if after:
                                val_tokens.append(lt)
                    if not val_tokens:
                        val_tokens = line_tokens
                    matches_by_key[field_key].append((raw_val, line_str, val_tokens))
                    break

    extracted_candidates: list[ExtractedFieldCandidate] = []
    missing_fields: list[str] = []
    conflicts_report: list[dict[str, Any]] = []

    existing_mother = existing_mother or {}
    previous_confirmed_fields = previous_confirmed_fields or {}

    for field_key, field_label in PERMITTED_ADMIN_FIELDS:
        occ = matches_by_key.get(field_key, [])
        non_empty_occ = [(v, ln, toks) for v, ln, toks in occ if v and v not in ("-", "—", "N/A", "none")]

        if not non_empty_occ:
            missing_fields.append(field_key)
            extracted_candidates.append(
                ExtractedFieldCandidate(
                    field_key=field_key,
                    field_label=field_label,
                    extracted_value=None,
                    normalized_value=None,
                    confidence=None,
                    uncertainty_flag=True,
                    uncertainty_reason="Field missing or blank on card",
                    conflict_detected=False,
                    conflicting_values=[],
                )
            )
            continue

        raw_val, source_line, val_tokens = non_empty_occ[0]
        distinct_vals: list[str] = []
        for v, _, _ in non_empty_occ:
            if v not in distinct_vals:
                distinct_vals.append(v)

        # Compute bounding box union and average confidence of value tokens
        x1 = min(t.x for t in val_tokens)
        y1 = min(t.y for t in val_tokens)
        x2 = max(t.x + t.w for t in val_tokens)
        y2 = max(t.y + t.h for t in val_tokens)
        avg_conf = round(sum(t.conf for t in val_tokens) / len(val_tokens), 1)

        uncertainty_reasons: list[str] = []
        conflict_flag = False
        conflict_values: list[str] = []

        # 1. Intra-document conflict check (multiple different values on the same card)
        if len(distinct_vals) > 1:
            conflict_flag = True
            conflict_values.extend(distinct_vals)
            reason = f"Multiple conflicting values on card: {' vs '.join(distinct_vals)}"
            uncertainty_reasons.append(reason)
            conflicts_report.append(
                {
                    "field_key": field_key,
                    "type": "intra_document_conflict",
                    "values": distinct_vals,
                    "message": reason,
                }
            )

        # 2. Normalization & format validation (without inventing values!)
        norm_val: Optional[str] = raw_val.strip()
        if field_key in DATE_FIELD_KEYS:
            parsed_date, date_err = _parse_strict_date(raw_val)
            norm_val = parsed_date
            if date_err:
                uncertainty_reasons.append(date_err)
        elif field_key == "contact_phone":
            parsed_phone, phone_err = _normalize_phone(raw_val)
            norm_val = parsed_phone
            if phone_err:
                uncertainty_reasons.append(phone_err)
        else:
            if "?" in raw_val or "illegible" in raw_val.lower() or "smudge" in raw_val.lower():
                norm_val = None
                uncertainty_reasons.append(f"Illegible or uncertain text: '{raw_val}'")

        # 3. Low OCR confidence check
        if avg_conf < 78.0:
            uncertainty_reasons.append(f"Low OCR confidence ({avg_conf}%)")

        # 4. Cross-record / previous version conflict check
        mother_field_map = {
            "patient_name": existing_mother.get("name"),
            "patient_identifier": existing_mother.get("patient_identifier"),
            "contact_phone": existing_mother.get("phone"),
            "lmp_date": existing_mother.get("lmp"),
            "edd_date": existing_mother.get("edd"),
            "address": existing_mother.get("address"),
        }
        prior_val = previous_confirmed_fields.get(field_key) or mother_field_map.get(field_key)
        compare_val = norm_val or raw_val
        if prior_val and compare_val and str(prior_val).strip() != str(compare_val).strip():
            conflict_flag = True
            if str(prior_val) not in conflict_values:
                conflict_values.append(str(prior_val))
            if str(compare_val) not in conflict_values:
                conflict_values.append(str(compare_val))
            diff_msg = f"Differs from existing confirmed record ('{prior_val}' -> '{compare_val}')"
            uncertainty_reasons.append(diff_msg)
            conflicts_report.append(
                {
                    "field_key": field_key,
                    "type": "confirmed_record_mismatch",
                    "previous_value": str(prior_val),
                    "extracted_value": str(compare_val),
                    "message": diff_msg,
                }
            )

        is_uncertain = bool(uncertainty_reasons) or conflict_flag
        token_dicts = [
            {
                "text": t.text,
                "conf": t.conf,
                "x": t.x,
                "y": t.y,
                "w": t.w,
                "h": t.h,
                "page": t.page,
            }
            for t in val_tokens
        ]

        extracted_candidates.append(
            ExtractedFieldCandidate(
                field_key=field_key,
                field_label=field_label,
                extracted_value=raw_val,
                normalized_value=norm_val,
                confidence=avg_conf,
                uncertainty_flag=is_uncertain,
                uncertainty_reason="; ".join(uncertainty_reasons),
                conflict_detected=conflict_flag,
                conflicting_values=conflict_values,
                source_page=1,
                bbox_x=x1,
                bbox_y=y1,
                bbox_w=max(10, x2 - x1),
                bbox_h=max(10, y2 - y1),
                source_snippet=source_line,
                tokens=token_dicts,
            )
        )

    if ocr_status == "completed" and (conflicts_report or len(missing_fields) >= 5):
        ocr_status = "completed_with_warnings"

    duration_ms = int((time.perf_counter() - t0) * 1000)
    mean_conf = (
        round(sum(t.conf for t in tokens) / len(tokens), 1) if tokens else None
    )
    raw_token_dicts = [
        {
            "text": t.text,
            "conf": t.conf,
            "x": t.x,
            "y": t.y,
            "w": t.w,
            "h": t.h,
            "page": t.page,
        }
        for t in tokens
    ]

    return OcrExtractionResult(
        ocr_status=ocr_status,
        ocr_engine=engine_name,
        extracted_text=full_extracted_text,
        image_width=width,
        image_height=height,
        page_count=page_count,
        duration_ms=duration_ms,
        word_count=len(tokens),
        mean_confidence=mean_conf,
        fields=extracted_candidates,
        missing_fields=missing_fields,
        conflicts=conflicts_report,
        raw_tokens=raw_token_dicts,
        error_message=ocr_error,
        preview_png_bytes=preview_bytes,
    )

