# auth.py
"""
Mock authentication module.

Provides a set of hardcoded users and a FastAPI dependency that resolves the
current user from an `X-User-ID` request header.

Migration to Azure Entra ID:
  Replace `get_current_user` with JWT/Bearer token validation via
  `azure-identity` / MSAL middleware.  The dependency signature stays the same
  so no endpoint code needs to change.
"""

from __future__ import annotations

from fastapi import Header, HTTPException
from pydantic import BaseModel


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

DEFAULT_USER_ID = "user-alice"


# ── FastAPI dependency ───────────────────────────────────────

async def get_current_user(
    x_user_id: str | None = Header(default=None, alias="X-User-ID"),
) -> User:
    """
    Resolve the current user from the request.

    In mock mode the user is identified by the ``X-User-ID`` header.
    If the header is absent the default user is returned.
    If the header contains an unknown user ID a 401 is raised.
    """
    user_id = x_user_id or DEFAULT_USER_ID
    user = MOCK_USERS.get(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail=f"Unknown user: {user_id}")
    return user
