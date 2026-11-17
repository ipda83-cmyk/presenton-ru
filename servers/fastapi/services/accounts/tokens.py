"""Signed links in letters: e-mail confirmation and password reset.

A reset link carries a fingerprint of the current password hash, so it stops
working as soon as the password is changed (it can be used once).
"""

import hashlib
import time
import uuid

import jwt

from api.v1.auth.config import get_or_create_auth_secret
from models.sql.user import User

ALGORITHM = "HS256"
VERIFY_TTL_SECONDS = 48 * 60 * 60
RESET_TTL_SECONDS = 60 * 60
AUDIENCE = "kvant:account"


def _fingerprint(user: User) -> str:
    return hashlib.sha256(f"{user.hashed_password}|{user.auth_version}".encode()).hexdigest()[:24]


def make(user: User, purpose: str) -> str:
    ttl = VERIFY_TTL_SECONDS if purpose == "verify" else RESET_TTL_SECONDS
    payload = {
        "sub": str(user.id),
        "purpose": purpose,
        "email": user.username.casefold(),
        "aud": AUDIENCE,
        "exp": int(time.time()) + ttl,
    }
    if purpose == "reset":
        payload["fp"] = _fingerprint(user)
    return jwt.encode(payload, get_or_create_auth_secret(), algorithm=ALGORITHM)


def read(token: str, purpose: str) -> dict | None:
    """The payload of a valid, unexpired link of this purpose, else None."""
    try:
        payload = jwt.decode(
            token, get_or_create_auth_secret(), algorithms=[ALGORITHM], audience=AUDIENCE
        )
    except jwt.PyJWTError:
        return None
    if payload.get("purpose") != purpose:
        return None
    try:
        uuid.UUID(str(payload.get("sub")))
    except ValueError:
        return None
    return payload


def matches(user: User, payload: dict) -> bool:
    """The link is for this user, the same address and (reset) the same password."""
    if user is None or not user.is_active or str(user.id) != payload.get("sub"):
        return False
    if user.username.casefold() != payload.get("email"):
        return False
    if payload.get("purpose") == "reset" and payload.get("fp") != _fingerprint(user):
        return False
    return True
