"""Account registration and login."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.auth import create_access_token, get_current_user, hash_password, verify_password
from app.models import LoginRequest, RegisterUserRequest, TokenResponse, User, UserPublic
from app.store import store

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

_BAD_LOGIN = "Invalid email or password"


def _token_for(user: User) -> TokenResponse:
    return TokenResponse(access_token=create_access_token(user.id), user=UserPublic.from_user(user))


def _authenticate(email: str, password: str) -> User:
    user = store.get_user_by_email(email.strip().lower())
    if not verify_password(password, user.password_hash if user else None) or user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, _BAD_LOGIN, headers={"WWW-Authenticate": "Bearer"}
        )
    return user


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterUserRequest) -> TokenResponse:
    user = User(
        id=store.new_id(),
        email=body.email.strip().lower(),
        name=body.name.strip(),
        password_hash=hash_password(body.password),
    )
    if not store.add_user(user):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    return _token_for(user)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest) -> TokenResponse:
    return _token_for(_authenticate(body.email, body.password))


@router.post("/token", response_model=TokenResponse, include_in_schema=True)
def token(form: OAuth2PasswordRequestForm = Depends()) -> TokenResponse:
    """OAuth2 password flow (used by the Swagger 'Authorize' button)."""
    return _token_for(_authenticate(form.username, form.password))


@router.get("/me", response_model=UserPublic)
def me(user: User = Depends(get_current_user)) -> UserPublic:
    return UserPublic.from_user(user)
