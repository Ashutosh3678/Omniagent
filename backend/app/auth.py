"""Password hashing, JWT access tokens, and per-device tokens."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.config import JWT_EXPIRE_MINUTES, JWT_SECRET
from app.models import User, utcnow
from app.store import store

_hasher = PasswordHasher()
_DUMMY_HASH = _hasher.hash("not-a-real-password")
_oauth2 = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)


def token_from_header(authorization: str | None) -> str:
    if not authorization:
        return ""
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not value:
        return ""
    return value.strip()


# passwords
def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """Always does one Argon2 verification so unknown emails take as long as wrong passwords."""
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


# JWT
def create_access_token(user_id: str) -> str:
    now = utcnow()
    claims = {"sub": user_id, "iat": now, "exp": now + timedelta(minutes=JWT_EXPIRE_MINUTES)}
    return jwt.encode(claims, JWT_SECRET, algorithm="HS256")


def decode_claims(token: str) -> dict | None:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=["HS256"], options={"require": ["sub", "exp"]})
    except jwt.PyJWTError:
        return None


def decode_access_token(token: str) -> str | None:
    claims = decode_claims(token)
    return str(claims["sub"]) if claims else None


def get_current_user(token: str | None = Depends(_oauth2)) -> User:
    user_id = decode_access_token(token) if token else None
    user = store.get_user(user_id) if user_id else None
    if user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


# device tokens
def new_device_token() -> str:
    return secrets.token_urlsafe(32)


def hash_device_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def device_token_matches(token: str, token_hash: str | None) -> bool:
    return bool(token and token_hash) and hmac.compare_digest(hash_device_token(token), token_hash)
