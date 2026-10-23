# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""Authentication API: login, session check, and logout."""
import logging
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from backend.config import settings
from backend.core.auth import (
    is_auth_enabled,
    verify_login_credentials,
    create_access_token,
    verify_access_token,
    get_token_from_request,
    TOKEN_MAX_AGE_SECONDS,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
async def login(body: LoginRequest, response: Response):
    """Log in using credentials configured in .env."""
    if not is_auth_enabled():
        token = create_access_token("admin")
        return {"ok": True, "token": token, "username": "admin"}

    if not verify_login_credentials(body.username, body.password):
        raise HTTPException(status_code=401, detail="Username atau password salah")

    token = create_access_token(body.username.strip())
    response.set_cookie(
        key="vm_token",
        value=token,
        max_age=TOKEN_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return {"ok": True, "token": token, "username": body.username.strip()}


@router.get("/me")
async def get_current_user_status(request: Request):
    """Check current user session status."""
    if not is_auth_enabled():
        return {
            "authenticated": True,
            "auth_enabled": False,
            "username": "admin",
        }

    token = get_token_from_request(request)
    if not token:
        return {
            "authenticated": False,
            "auth_enabled": True,
            "username": None,
        }

    payload = verify_access_token(token)
    if not payload:
        return {
            "authenticated": False,
            "auth_enabled": True,
            "username": None,
        }

    return {
        "authenticated": True,
        "auth_enabled": True,
        "username": payload.get("sub", "admin"),
    }


@router.post("/logout")
async def logout(response: Response):
    """Clear session token cookie."""
    response.delete_cookie(key="vm_token", path="/")
    return {"ok": True}
