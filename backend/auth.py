# auth.py
"""Authentication module.

Supports two modes:

- ``AUTH_MODE=entra`` (default): validates Azure Entra ID bearer JWT tokens.
- ``AUTH_MODE=mock``: local-development mock users, no default fallback user.

Any unauthenticated request is rejected with HTTP 401.
"""

from __future__ import annotations

import json
import logging
import os
import time
from urllib.request import urlopen

import jwt
from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel


logger = logging.getLogger("ag_ui.auth")


class User(BaseModel):
    """Authenticated user profile."""
    user_id: str
    display_name: str
    email: str
    avatar_url: str | None = None
    initials: str  # e.g. "AJ" — used when avatar_url is None


# ── Mock user database ───────────────────────────────────────

MOCK_USERS: dict[str, User] = {
    "user-alice": User(
        user_id="user-alice",
        display_name="Alice Johnson",
        email="alice@contoso.com",
        initials="AJ",
    ),
    "user-bob": User(
        user_id="user-bob",
        display_name="Bob Smith",
        email="bob@contoso.com",
        initials="BS",
    ),
    "user-charlie": User(
        user_id="user-charlie",
        display_name="Charlie Lee",
        email="charlie@contoso.com",
        initials="CL",
    ),
}

_bearer_scheme = HTTPBearer(auto_error=False)
_OPENID_CACHE_TTL_SECONDS = 3600
_openid_cache: dict[str, object] = {"expires_at": 0.0, "document": None}


def _auth_mode() -> str:
    return os.getenv("AUTH_MODE", "entra").strip().lower()


def _build_initials(name: str, email: str) -> str:
    parts = [p for p in name.strip().split() if p]
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1][0]).upper()
    if len(parts) == 1:
        return parts[0][:2].upper()
    local = email.split("@", 1)[0] if email else "user"
    return local[:2].upper()


def _load_openid_configuration() -> dict:
    now = time.time()
    cached_doc = _openid_cache.get("document")
    cached_exp = float(_openid_cache.get("expires_at", 0.0) or 0.0)
    if isinstance(cached_doc, dict) and cached_exp > now:
        return cached_doc

    tenant_id = os.getenv("ENTRA_TENANT_ID", "common").strip()
    openid_url = os.getenv(
        "ENTRA_OPENID_CONFIG_URL",
        f"https://login.microsoftonline.com/{tenant_id}/v2.0/.well-known/openid-configuration",
    ).strip()

    with urlopen(openid_url, timeout=10) as response:
        doc = json.loads(response.read().decode("utf-8"))

    if not isinstance(doc, dict) or "jwks_uri" not in doc or "issuer" not in doc:
        raise RuntimeError("Invalid OpenID configuration response")

    _openid_cache["document"] = doc
    _openid_cache["expires_at"] = now + _OPENID_CACHE_TTL_SECONDS
    return doc


def _validate_required_permissions(claims: dict) -> None:
    required_scopes = [
        scope.strip()
        for scope in os.getenv("ENTRA_REQUIRED_SCOPES", "").split(",")
        if scope.strip()
    ]
    required_roles = [
        role.strip()
        for role in os.getenv("ENTRA_REQUIRED_ROLES", "").split(",")
        if role.strip()
    ]

    if not required_scopes and not required_roles:
        return

    token_scopes = set((claims.get("scp") or "").split())
    token_roles = set(claims.get("roles") or [])

    missing_scopes = [scope for scope in required_scopes if scope not in token_scopes]
    missing_roles = [role for role in required_roles if role not in token_roles]
    if missing_scopes or missing_roles:
        raise HTTPException(status_code=403, detail="Insufficient permissions")


def _validate_entra_bearer_token(token: str) -> dict:
    openid_doc = _load_openid_configuration()

    audiences = [
        value.strip()
        for value in os.getenv("ENTRA_AUDIENCE", "").split(",")
        if value.strip()
    ]
    if not audiences:
        raise RuntimeError("ENTRA_AUDIENCE is required in AUTH_MODE=entra")

    issuer = os.getenv("ENTRA_ISSUER", openid_doc["issuer"]).strip()
    jwks_uri = str(openid_doc["jwks_uri"])

    jwk_client = jwt.PyJWKClient(jwks_uri)
    signing_key = jwk_client.get_signing_key_from_jwt(token)

    claims = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience=audiences,
        issuer=issuer,
        options={"require": ["exp", "iat", "iss", "aud"]},
    )
    _validate_required_permissions(claims)
    return claims


def _user_from_claims(claims: dict) -> User:
    user_id = str(claims.get("oid") or claims.get("sub") or "").strip()
    if not user_id:
        raise HTTPException(status_code=401, detail="Token missing subject")

    email = str(claims.get("preferred_username") or claims.get("email") or "").strip()
    display_name = str(claims.get("name") or email or user_id).strip()
    initials = _build_initials(display_name, email)

    return User(
        user_id=user_id,
        display_name=display_name,
        email=email,
        avatar_url=None,
        initials=initials,
    )


# ── FastAPI dependency ───────────────────────────────────────

async def get_current_user(
    authorization: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-ID"),
) -> User:
    """Resolve the currently authenticated user."""
    mode = _auth_mode()

    if mode == "mock":
        user_id = (x_mock_user_id or "").strip()
        if not user_id:
            raise HTTPException(status_code=401, detail="Missing X-Mock-User-ID header")
        user = MOCK_USERS.get(user_id)
        if user is None:
            raise HTTPException(status_code=401, detail=f"Unknown mock user: {user_id}")
        return user

    if mode != "entra":
        raise RuntimeError(f"Unsupported AUTH_MODE: {mode}")

    if authorization is None or authorization.scheme.lower() != "bearer" or not authorization.credentials:
        raise HTTPException(status_code=401, detail="Missing bearer token")

    token = authorization.credentials
    try:
        claims = _validate_entra_bearer_token(token)
    except HTTPException:
        raise
    except Exception as ex:
        logger.warning("Bearer token validation failed: %s", str(ex))
        raise HTTPException(status_code=401, detail="Invalid bearer token")

    return _user_from_claims(claims)
