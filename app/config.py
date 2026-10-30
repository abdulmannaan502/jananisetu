"""Application configuration loaded from environment variables with strict production defaults."""
from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import shutil

ROOT_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(dotenv_path: Path) -> None:
    """Load key=value pairs from .env file if present without overriding existing env vars."""
    if not dotenv_path.is_file():
        return
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = val


_load_dotenv(ROOT_DIR / ".env")


def _detect_tesseract_cmd() -> str:
    env_cmd = os.getenv("JANANI_TESSERACT_CMD", "").strip()
    if env_cmd and Path(env_cmd).is_file():
        return env_cmd
    which_cmd = shutil.which("tesseract")
    if which_cmd:
        return which_cmd
    win_default = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    if win_default.is_file():
        return str(win_default)
    return "tesseract"


@dataclass
class Settings:
    env: str = field(default_factory=lambda: os.getenv("JANANI_ENV", "development"))
    data_dir: Path = field(
        default_factory=lambda: Path(os.getenv("JANANI_DATA_DIR", str(ROOT_DIR / "data")))
    )
    db_url: str = field(default="")
    jwt_secret: str = field(
        default_factory=lambda: os.getenv(
            "JANANI_JWT_SECRET",
            "jananisetu-round2-default-dev-secret-key-2026-do-not-use-in-prod",
        )
    )
    jwt_algorithm: str = field(default_factory=lambda: os.getenv("JANANI_JWT_ALGORITHM", "HS256"))
    access_token_expire_minutes: int = field(
        default_factory=lambda: int(os.getenv("JANANI_ACCESS_TOKEN_EXPIRE_MINUTES", "480"))
    )
    # Security hardening: X-Staff-ID legacy header is disabled by default and ALWAYS false in production
    allow_legacy_header: bool = field(
        default_factory=lambda: os.getenv("JANANI_ALLOW_LEGACY_HEADER", "false").lower()
        in ("1", "true", "yes")
    )
    # Demo endpoints are disabled in production
    enable_demo_mode: bool = field(
        default_factory=lambda: os.getenv("JANANI_ENABLE_DEMO_MODE", "true").lower()
        in ("1", "true", "yes")
    )
    bootstrap_token: str = field(
        default_factory=lambda: os.getenv("JANANI_BOOTSTRAP_TOKEN", "")
    )
    cors_origins: list[str] = field(
        default_factory=lambda: [
            o.strip()
            for o in os.getenv(
                "JANANI_CORS_ORIGINS",
                "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000,http://127.0.0.1:8000",
            ).split(",")
            if o.strip()
        ]
    )
    seed_demo_data: bool = field(
        default_factory=lambda: os.getenv("JANANI_SEED_DEMO_DATA", "false").lower()
        in ("1", "true", "yes")
    )
    # OCR & External Vision Provider Safeguards
    tesseract_cmd: str = field(default_factory=_detect_tesseract_cmd)
    external_ocr_enabled: bool = field(
        default_factory=lambda: os.getenv("JANANI_EXTERNAL_OCR_ENABLED", "false").lower()
        in ("1", "true", "yes")
    )
    external_ocr_data_safeguard_ack: bool = field(
        default_factory=lambda: os.getenv("JANANI_EXTERNAL_OCR_DATA_SAFEGUARD_ACK", "false").lower()
        in ("1", "true", "yes")
    )
    external_ocr_provider_url: str = field(
        default_factory=lambda: os.getenv("JANANI_EXTERNAL_OCR_PROVIDER_URL", "")
    )
    external_ocr_api_key: str = field(
        default_factory=lambda: os.getenv("JANANI_EXTERNAL_OCR_API_KEY", "")
    )
    # Phase 4: Durable Reminder Infrastructure & Messaging Configuration
    redis_url: str = field(
        default_factory=lambda: os.getenv("JANANI_REDIS_URL", "redis://localhost:6379/0")
    )
    default_timezone: str = field(
        default_factory=lambda: os.getenv("JANANI_TIMEZONE", "Asia/Kolkata")
    )
    webhook_secret: str = field(
        default_factory=lambda: os.getenv(
            "JANANI_WEBHOOK_SECRET", "jananisetu-webhook-hmac-secret-2026"
        )
    )
    whatsapp_verify_token: str = field(
        default_factory=lambda: os.getenv(
            "JANANI_WHATSAPP_VERIFY_TOKEN", "jananisetu-meta-verify-2026"
        )
    )
    # Meta WhatsApp Cloud API credentials (live messaging requires explicit credentials + approved templates)
    whatsapp_api_base_url: str = field(
        default_factory=lambda: os.getenv(
            "JANANI_WHATSAPP_API_BASE_URL", "https://graph.facebook.com/v20.0"
        )
    )
    whatsapp_phone_number_id: str = field(
        default_factory=lambda: os.getenv("JANANI_WHATSAPP_PHONE_NUMBER_ID", "")
    )
    whatsapp_access_token: str = field(
        default_factory=lambda: os.getenv("JANANI_WHATSAPP_ACCESS_TOKEN", "")
    )
    whatsapp_template_approved: bool = field(
        default_factory=lambda: os.getenv("JANANI_WHATSAPP_TEMPLATE_APPROVED", "false").lower()
        in ("1", "true", "yes")
    )
    # Optional SMS Gateway Provider credentials
    sms_provider_url: str = field(
        default_factory=lambda: os.getenv("JANANI_SMS_PROVIDER_URL", "")
    )
    sms_api_key: str = field(
        default_factory=lambda: os.getenv("JANANI_SMS_API_KEY", "")
    )
    sms_sender_id: str = field(
        default_factory=lambda: os.getenv("JANANI_SMS_SENDER_ID", "JANANI")
    )

    @property
    def is_production(self) -> bool:
        return self.env.lower() in ("production", "prod")

    def __post_init__(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if self.env.lower() in ("production", "prod"):
            # Never allow legacy X-Staff-ID header or demo account disclosure in production
            self.allow_legacy_header = False
            self.enable_demo_mode = False
            self.seed_demo_data = False

        if not self.db_url:
            default_sqlite = f"sqlite:///{self.data_dir / 'janani.db'}"
            self.db_url = os.getenv("JANANI_DB_URL", os.getenv("DATABASE_URL", default_sqlite))
            if self.db_url.startswith("postgres://"):
                self.db_url = self.db_url.replace("postgres://", "postgresql+psycopg://", 1)
            elif self.db_url.startswith("postgresql://"):
                self.db_url = self.db_url.replace("postgresql://", "postgresql+psycopg://", 1)


def get_settings() -> Settings:
    return Settings()
