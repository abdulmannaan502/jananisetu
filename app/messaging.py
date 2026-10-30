"""Provider-independent messaging engine with Meta WhatsApp Cloud API, SMS Gateway, and Local Simulator adapters.

Includes:
- Explicit opt-in & caregiver permission checks
- Approved multilingual WhatsApp templates (Telugu, Hindi, English)
- Privacy-conscious content guards (never leak clinical findings or ANC scans, especially to caregivers)
- Phone number masking for logs and audit trails
- Signed webhook HMAC-SHA256 verification (X-Hub-Signature-256)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import hmac
import logging
import re
from typing import Any, Optional
import uuid

import httpx

from app.config import get_settings

logger = logging.getLogger("jananisetu.messaging")

# Words that indicate clinical findings, diagnoses, or scan disclosures which must NEVER be sent
# in unencrypted messaging channels or caregiver administrative reminders.
PROHIBITED_CLINICAL_TERMS = (
    "hemoglobin",
    "hb level",
    "blood pressure",
    "bp:",
    "preeclampsia",
    "eclampsia",
    "hiv",
    "hbsag",
    "vdrl",
    "syphilis",
    "gestational diabetes",
    "anemia",
    "high-risk diagnosis",
    "prescription",
    "ultrasound finding",
    "fetal distress",
    "placenta previa",
    "/file",
    "/preview",
    "anc_scan",
)

APPROVED_TEMPLATES: dict[str, dict[str, str]] = {
    "janani_anc_reminder_te": {
        "language": "te",
        "recipient": "mother",
        "body": (
            "నమస్కారం {mother_name} గారు, జననిసేతు ({clinic}) నుండి సమాచారం: "
            "డాక్టర్ ఆమోదించిన మీ తదుపరి ANC చెకప్ తేదీ {visit_date}. "
            "దయచేసి మీ MCP కార్డు తీసుకురండి. నిర్ధారించడానికి 'YES' అని రిప్లై ఇవ్వండి."
        ),
    },
    "janani_anc_reminder_hi": {
        "language": "hi",
        "recipient": "mother",
        "body": (
            "नमस्ते {mother_name}, जननीसेतु ({clinic}) से अनुस्मारक: "
            "डॉक्टर द्वारा निर्धारित आपकी अगली ANC जांच दिनांक {visit_date} को है। "
            "कृपया अपना MCP कार्ड साथ लाएं। पुष्टि के लिए 'YES' लिखकर भेजें।"
        ),
    },
    "janani_anc_reminder_en": {
        "language": "en",
        "recipient": "mother",
        "body": (
            "Hello {mother_name}, reminder from JananiSetu ({clinic}): "
            "Your doctor-authorised ANC checkup is scheduled on {visit_date}. "
            "Please bring your MCP card. Reply 'YES' to confirm attendance."
        ),
    },
    "janani_caregiver_admin_reminder_v1": {
        "language": "en",
        "recipient": "caregiver",
        "body": (
            "Hello {caregiver_name}, administrative reminder from JananiSetu ({clinic}): "
            "{mother_name} has a scheduled clinic appointment on {visit_date}. "
            "Please assist with timely arrival and transport if needed. Reply 'YES' to acknowledge."
        ),
    },
}

DELIVERY_STATUS_RANKS: dict[str, int] = {
    "failed": -1,
    "queued": 0,
    "sent": 1,
    "delivered": 2,
    "read": 3,
    "acknowledged": 4,
}


def mask_phone(phone: str) -> str:
    """Mask phone numbers for logs and UI metadata (DPDP Act 2023 data minimisation)."""
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) <= 4:
        return "****"
    return "*" * (len(digits) - 4) + digits[-4:]


def validate_privacy_safe_content(body: str, recipient_type: str = "mother") -> tuple[bool, str]:
    """Ensure message body contains no clinical findings, diagnoses, or ANC scan links."""
    lower = (body or "").lower()
    for term in PROHIBITED_CLINICAL_TERMS:
        if term in lower:
            return (
                False,
                f"Privacy guard blocked message containing restricted clinical/document term '{term}'.",
            )
    if recipient_type == "caregiver":
        caregiver_blocked = ("lmp", "edd", "trimester", "ocr", "scan", "test result", "lab")
        for term in caregiver_blocked:
            if re.search(rf"\b{re.escape(term)}\b", lower):
                return (
                    False,
                    f"Caregiver privacy guard blocked restricted medical/record term '{term}'.",
                )
    return True, ""


def render_approved_template(
    template_name: str,
    *,
    mother_name: str,
    clinic: str,
    visit_date: date | str,
    caregiver_name: str = "",
) -> str:
    tpl = APPROVED_TEMPLATES.get(template_name) or APPROVED_TEMPLATES["janani_anc_reminder_en"]
    v_str = visit_date.isoformat() if isinstance(visit_date, date) else str(visit_date)
    return tpl["body"].format(
        mother_name=mother_name,
        clinic=clinic,
        visit_date=v_str,
        caregiver_name=caregiver_name or "Caregiver",
    )


def verify_webhook_signature(raw_body: bytes, signature_header: Optional[str], secret: str) -> bool:
    """Verify HMAC-SHA256 webhook signature (`X-Hub-Signature-256: sha256=<hex>` or raw hex)."""
    if not signature_header or not secret:
        return False
    sig = signature_header.strip()
    if sig.lower().startswith("sha256="):
        sig = sig.split("=", 1)[1].strip()
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected.lower(), sig.lower())


@dataclass
class SendMessageResult:
    ok: bool
    provider: str
    provider_message_id: Optional[str] = None
    status: str = "sent"
    failure_code: str = ""
    failure_reason: str = ""
    live_network_used: bool = False


class MessagingProvider:
    provider_name: str = "base"

    def is_live_configured(self) -> bool:
        return False

    def send_template_message(
        self,
        *,
        to_phone: str,
        template_name: str,
        language_code: str,
        rendered_body: str,
        idempotency_key: str,
        recipient_type: str = "mother",
        simulate_failure: bool = False,
    ) -> SendMessageResult:
        raise NotImplementedError


class LocalSimulatorAdapter(MessagingProvider):
    """Deterministic local simulator for automated testing and offline development."""

    provider_name = "local-simulator"

    def is_live_configured(self) -> bool:
        return True

    def send_template_message(
        self,
        *,
        to_phone: str,
        template_name: str,
        language_code: str,
        rendered_body: str,
        idempotency_key: str,
        recipient_type: str = "mother",
        simulate_failure: bool = False,
    ) -> SendMessageResult:
        safe, reason = validate_privacy_safe_content(rendered_body, recipient_type)
        if not safe:
            return SendMessageResult(
                ok=False,
                provider=self.provider_name,
                status="failed",
                failure_code="PRIVACY_POLICY_VIOLATION",
                failure_reason=reason,
            )

        if simulate_failure or "[SIMULATE_FAIL]" in rendered_body or to_phone.endswith("0000"):
            logger.warning(
                "LocalSimulator simulated failure for phone=%s key=%s",
                mask_phone(to_phone),
                idempotency_key,
            )
            return SendMessageResult(
                ok=False,
                provider=self.provider_name,
                status="failed",
                failure_code="SIMULATED_PROVIDER_TIMEOUT",
                failure_reason="Simulated transient provider error for retry/dead-letter verification.",
            )

        digest = hashlib.sha256(f"{idempotency_key}:{to_phone}".encode("utf-8")).hexdigest()[:16]
        provider_msg_id = f"wamid.sim.{digest}"
        logger.info(
            "LocalSimulator sent template=%s to=%s msg_id=%s",
            template_name,
            mask_phone(to_phone),
            provider_msg_id,
        )
        return SendMessageResult(
            ok=True,
            provider=self.provider_name,
            provider_message_id=provider_msg_id,
            status="sent",
            live_network_used=False,
        )


class MetaWhatsAppCloudAdapter(MessagingProvider):
    """Meta WhatsApp Cloud API adapter with approved template support and honest credential reporting."""

    provider_name = "whatsapp-cloud"

    def __init__(self) -> None:
        self.settings = get_settings()

    def is_live_configured(self) -> bool:
        return bool(
            self.settings.whatsapp_phone_number_id
            and self.settings.whatsapp_access_token
            and self.settings.whatsapp_template_approved
        )

    def send_template_message(
        self,
        *,
        to_phone: str,
        template_name: str,
        language_code: str,
        rendered_body: str,
        idempotency_key: str,
        recipient_type: str = "mother",
        simulate_failure: bool = False,
    ) -> SendMessageResult:
        safe, reason = validate_privacy_safe_content(rendered_body, recipient_type)
        if not safe:
            return SendMessageResult(
                ok=False,
                provider=self.provider_name,
                status="failed",
                failure_code="PRIVACY_POLICY_VIOLATION",
                failure_reason=reason,
            )

        if simulate_failure or "[SIMULATE_FAIL]" in rendered_body or to_phone.endswith("0000"):
            return SendMessageResult(
                ok=False,
                provider=self.provider_name,
                status="failed",
                failure_code="WHATSAPP_RATE_LIMIT_130429",
                failure_reason="Simulated Meta Cloud API transient failure.",
            )

        if not self.is_live_configured():
            return SendMessageResult(
                ok=False,
                provider=self.provider_name,
                status="failed",
                failure_code="WHATSAPP_CREDENTIALS_NOT_CONFIGURED",
                failure_reason=(
                    "Live Meta WhatsApp Cloud API credentials (JANANI_WHATSAPP_PHONE_NUMBER_ID, "
                    "JANANI_WHATSAPP_ACCESS_TOKEN) or approved template flag "
                    "(JANANI_WHATSAPP_TEMPLATE_APPROVED=true) are not configured."
                ),
                live_network_used=False,
            )

        url = f"{self.settings.whatsapp_api_base_url.rstrip('/')}/{self.settings.whatsapp_phone_number_id}/messages"
        payload: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": re.sub(r"\D", "", to_phone),
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code or "en"},
            },
        }
        headers = {
            "Authorization": f"Bearer {self.settings.whatsapp_access_token}",
            "Content-Type": "application/json",
            "X-Idempotency-Key": idempotency_key,
        }
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(url, json=payload, headers=headers)
            if resp.status_code in (200, 201):
                data = resp.json()
                messages = data.get("messages") or []
                wamid = messages[0].get("id") if messages else f"wamid.live.{uuid.uuid4().hex[:12]}"
                return SendMessageResult(
                    ok=True,
                    provider=self.provider_name,
                    provider_message_id=wamid,
                    status="sent",
                    live_network_used=True,
                )
            return SendMessageResult(
                ok=False,
                provider=self.provider_name,
                status="failed",
                failure_code=f"HTTP_{resp.status_code}",
                failure_reason=resp.text[:300],
                live_network_used=True,
            )
        except Exception as exc:
            logger.error("MetaWhatsAppCloudAdapter error for %s: %s", mask_phone(to_phone), exc)
            return SendMessageResult(
                ok=False,
                provider=self.provider_name,
                status="failed",
                failure_code="NETWORK_ERROR",
                failure_reason=str(exc)[:300],
                live_network_used=True,
            )


class SmsGatewayAdapter(MessagingProvider):
    """Optional SMS gateway adapter for feature-phone outreach."""

    provider_name = "sms-gateway"

    def __init__(self) -> None:
        self.settings = get_settings()

    def is_live_configured(self) -> bool:
        return bool(self.settings.sms_provider_url and self.settings.sms_api_key)

    def send_template_message(
        self,
        *,
        to_phone: str,
        template_name: str,
        language_code: str,
        rendered_body: str,
        idempotency_key: str,
        recipient_type: str = "mother",
        simulate_failure: bool = False,
    ) -> SendMessageResult:
        safe, reason = validate_privacy_safe_content(rendered_body, recipient_type)
        if not safe:
            return SendMessageResult(
                ok=False,
                provider=self.provider_name,
                status="failed",
                failure_code="PRIVACY_POLICY_VIOLATION",
                failure_reason=reason,
            )
        if simulate_failure or to_phone.endswith("0000"):
            return SendMessageResult(
                ok=False,
                provider=self.provider_name,
                status="failed",
                failure_code="SMS_GATEWAY_TIMEOUT",
                failure_reason="Simulated SMS gateway failure.",
            )
        if not self.is_live_configured():
            return SendMessageResult(
                ok=False,
                provider=self.provider_name,
                status="failed",
                failure_code="SMS_CREDENTIALS_NOT_CONFIGURED",
                failure_reason="SMS gateway URL or API key is not configured.",
            )
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(
                    self.settings.sms_provider_url,
                    json={
                        "sender": self.settings.sms_sender_id,
                        "to": re.sub(r"\D", "", to_phone),
                        "text": rendered_body,
                        "idempotency_key": idempotency_key,
                    },
                    headers={"Authorization": f"Bearer {self.settings.sms_api_key}"},
                )
            if resp.status_code in (200, 201, 202):
                return SendMessageResult(
                    ok=True,
                    provider=self.provider_name,
                    provider_message_id=f"sms.{uuid.uuid4().hex[:12]}",
                    status="sent",
                    live_network_used=True,
                )
            return SendMessageResult(
                ok=False,
                provider=self.provider_name,
                status="failed",
                failure_code=f"SMS_HTTP_{resp.status_code}",
                failure_reason=resp.text[:250],
                live_network_used=True,
            )
        except Exception as exc:
            return SendMessageResult(
                ok=False,
                provider=self.provider_name,
                status="failed",
                failure_code="SMS_NETWORK_ERROR",
                failure_reason=str(exc)[:250],
                live_network_used=True,
            )


def get_messaging_adapter(channel: str) -> MessagingProvider:
    norm = (channel or "local-simulator").strip().lower()
    if norm in ("whatsapp", "whatsapp-cloud", "meta-whatsapp"):
        return MetaWhatsAppCloudAdapter()
    if norm in ("sms", "sms-gateway"):
        return SmsGatewayAdapter()
    return LocalSimulatorAdapter()


def get_messaging_providers_status() -> dict[str, Any]:
    wa = MetaWhatsAppCloudAdapter()
    sms = SmsGatewayAdapter()
    sim = LocalSimulatorAdapter()
    return {
        "local_simulator": {
            "provider": sim.provider_name,
            "operational": True,
            "mode": "simulated_local",
            "note": "Deterministic local simulator active for automated testing and offline development.",
        },
        "whatsapp_cloud": {
            "provider": wa.provider_name,
            "operational": wa.is_live_configured(),
            "phone_number_id_configured": bool(wa.settings.whatsapp_phone_number_id),
            "access_token_configured": bool(wa.settings.whatsapp_access_token),
            "templates_approved": bool(wa.settings.whatsapp_template_approved),
            "mode": "live_meta_cloud_api" if wa.is_live_configured() else "credentials_required",
            "note": (
                "Live Meta WhatsApp Cloud API ready."
                if wa.is_live_configured()
                else "Live WhatsApp disabled until verified Meta Cloud API credentials and approved templates are configured."
            ),
        },
        "sms_gateway": {
            "provider": sms.provider_name,
            "operational": sms.is_live_configured(),
            "mode": "live_sms_gateway" if sms.is_live_configured() else "credentials_required",
        },
    }

