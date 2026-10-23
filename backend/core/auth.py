# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""Authentication utility functions: token generation, verification, and request inspection."""
import base64
import hashlib
import hmac
import json
import logging
import time
from typing import Optional
from fastapi import Request

from backend.config import settings

logger = logging.getLogger(__name__)

TOKEN_MAX_AGE_SECONDS = 30 * 24 * 3600  # 30 days


def _get_signing_key() -> bytes:
    key_src = (
        settings.AUTH_JWT_SECRET
        or settings.ENCRYPTION_KEY
        or settings.SECRET_KEY
        or "viralmint-secure-auth-signing-key"
    )
    return hashlib.sha256(key_src.encode("utf-8")).digest()


def is_auth_enabled() -> bool:
    """Return True if password protection is configured in .env."""
    return bool(settings.AUTH_PASSWORD and settings.AUTH_PASSWORD.strip())


def verify_login_credentials(username: str, password: str) -> bool:
    """Validate username and password against .env configuration."""
    if not is_auth_enabled():
        return False

    expected_user = settings.AUTH_USERNAME.strip() or "admin"
    expected_pass = settings.AUTH_PASSWORD.strip()

    user_matches = hmac.compare_digest(username.strip(), expected_user)
    pass_matches = hmac.compare_digest(password, expected_pass)
    return user_matches and pass_matches


def create_access_token(username: str) -> str:
    """Create a signed, base64-encoded URL-safe session token."""
    now = int(time.time())
    payload = {
        "sub": username,
        "iat": now,
        "exp": now + TOKEN_MAX_AGE_SECONDS,
    }
    raw_payload = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(raw_payload).decode("utf-8").rstrip("=")

    signature = hmac.new(_get_signing_key(), payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{signature}"


def verify_access_token(token: str) -> Optional[dict]:
    """Verify signature and expiration of token. Returns payload dict or None."""
    if not token or "." not in token:
        return None

    try:
        payload_b64, signature = token.split(".", 1)
        expected_sig = hmac.new(_get_signing_key(), payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected_sig):
            return None

        # Re-pad base64
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        raw_payload = base64.urlsafe_b64decode(padded.encode("utf-8"))
        payload = json.loads(raw_payload.decode("utf-8"))

        if payload.get("exp", 0) < time.time():
            return None

        return payload
    except Exception as e:
        logger.debug(f"Token verification failed: {e}")
        return None


def get_token_from_request(request: Request) -> Optional[str]:
    """Extract token from Authorization header, cookie, or query string."""
    # 1. Authorization header: Bearer <token>
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        if token:
            return token

    # 2. Cookie: vm_token
    cookie_token = request.cookies.get("vm_token")
    if cookie_token:
        return cookie_token

    # 3. Query param: token
    query_token = request.query_params.get("token")
    if query_token:
        return query_token

    return None
