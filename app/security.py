"""Authentication, password policy, password hashing, JWT management, and RBAC."""
from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import re
import secrets
from typing import Any
import uuid

from fastapi import HTTPException

from app.config import get_settings

try:
    import bcrypt as _bcrypt
except ImportError:  # pragma: no cover
    _bcrypt = None

try:
    import jwt as _pyjwt
except ImportError:  # pragma: no cover
    _pyjwt = None


VALID_ROLES = ("admin", "doctor", "nurse", "field_coordinator", "asha")


def normalize_role(role: str) -> str:
    """Normalize role aliases: 'asha' and 'field_coordinator' both represent field coordinators."""
    if role == "asha":
        return "field_coordinator"
    return role


def validate_password_strength(password: str) -> str:
    """Enforce production password policy: min 8 chars, at least one letter and one digit."""
    if not password or len(password) < 8:
        raise HTTPException(
            status_code=422,
            detail="Password must be at least 8 characters long",
        )
    if len(password) > 128:
        raise HTTPException(
            status_code=422,
            detail="Password must not exceed 128 characters",
        )
    if not re.search(r"[A-Za-z]", password) or not re.search(r"[0-9]", password):
        raise HTTPException(
            status_code=422,
            detail="Password must contain at least one letter and one number",
        )
    return password


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    if not plain_password:
        plain_password = secrets.token_urlsafe(16)
    if _bcrypt is not None:
        salt = _bcrypt.gensalt(rounds=10)
        return _bcrypt.hashpw(plain_password.encode("utf-8"), salt).decode("utf-8")
    salt_hex = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256", plain_password.encode("utf-8"), salt_hex.encode("utf-8"), 200_000
    )
    return f"pbkdf2_sha256${salt_hex}${dk.hex()}"


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Constant-time verification of a plaintext password against its stored hash."""
    if not plain_password or not password_hash:
        return False
    if password_hash.startswith("$2") and _bcrypt is not None:
        try:
            return _bcrypt.checkpw(
                plain_password.encode("utf-8"), password_hash.encode("utf-8")
            )
        except Exception:
            return False
    if password_hash.startswith("pbkdf2_sha256$"):
        parts = password_hash.split("$")
        if len(parts) != 3:
            return False
        _, salt_hex, stored_hex = parts
        dk = hashlib.pbkdf2_hmac(
            "sha256", plain_password.encode("utf-8"), salt_hex.encode("utf-8"), 200_000
        )
        return hmac.compare_digest(dk.hex(), stored_hex)
    return False


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(segment: str) -> bytes:
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + padding)


def create_access_token(
    subject: str,
    role: str,
    clinic: str,
    name: str = "",
    token_version: int = 1,
    jti: str | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a signed JWT access token with unique JTI and token_version for revocation support."""
    settings = get_settings()
    now_utc = datetime.now(timezone.utc)
    expire = now_utc + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.access_token_expire_minutes)
    )
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "clinic": clinic,
        "name": name,
        "tv": token_version,
        "jti": jti or str(uuid.uuid4()),
        "iat": int(now_utc.timestamp()),
        "exp": int(expire.timestamp()),
    }
    if _pyjwt is not None:
        return _pyjwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    header = {"alg": "HS256", "typ": "JWT"}
    h_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    p_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{h_b64}.{p_b64}".encode("ascii")
    sig = hmac.new(settings.jwt_secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{h_b64}.{p_b64}.{_b64url_encode(sig)}"


def decode_access_token(token: str) -> dict[str, Any]:
    """Verify and decode a JWT access token, raising HTTPException(401) if invalid or expired."""
    settings = get_settings()
    if _pyjwt is not None:
        try:
            payload = _pyjwt.decode(
                token,
                settings.jwt_secret,
                algorithms=[settings.jwt_algorithm],
            )
            return payload
        except Exception as exc:
            raise HTTPException(status_code=401, detail=f"Invalid or expired token: {exc}") from exc

    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("Malformed token")
        h_b64, p_b64, s_b64 = parts
        signing_input = f"{h_b64}.{p_b64}".encode("ascii")
        expected_sig = hmac.new(
            settings.jwt_secret.encode("utf-8"), signing_input, hashlib.sha256
        ).digest()
        actual_sig = _b64url_decode(s_b64)
        if not hmac.compare_digest(expected_sig, actual_sig):
            raise ValueError("Invalid token signature")
        payload = json.loads(_b64url_decode(p_b64).decode("utf-8"))
        if int(payload.get("exp", 0)) < int(datetime.now(timezone.utc).timestamp()):
            raise ValueError("Token expired")
        return payload
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Invalid or expired token: {exc}") from exc
