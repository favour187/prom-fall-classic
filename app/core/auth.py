"""Authentication: users, hashed passwords, opaque session tokens.

- Passwords: PBKDF2-HMAC-SHA256 (stdlib `hashlib`, no extra dependency),
  per-user random salt, configurable iteration count.
- Sessions: random 256-bit tokens; only the SHA-256 hash is stored, so a
  database leak does not leak usable tokens. Tokens expire.
- Transport: `Authorization: Bearer <token>` header. (A production app would
  use HttpOnly secure cookies; the bearer header keeps the demo simple.)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

import uuid as uuid_mod

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import ForeignKey, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from .config import Settings
from .db import Base, get_db, iso_utc, session_scope, TimestampsMixin, UUIDMixin, utcnow
from .errors import AuthenticationError, ConflictError, PermissionDeniedError, ValidationFailedError
from .state import get_app_state
from .logging import get_logger

logger = get_logger("app.auth")

_ALGO = "pbkdf2_sha256"
_HEADER_PREFIX = "Bearer "


# --------------------------------------------------------------------------
# Password hashing (stdlib)
# --------------------------------------------------------------------------
def hash_password(password: str, *, iterations: int | None = None) -> str:
    if iterations is None:
        try:
            iterations = get_app_state().settings.password_iterations
        except RuntimeError:
            iterations = Settings.password_iterations
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"{_ALGO}${iterations}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iter_str, salt_b64, digest_b64 = stored.split("$")
        if algo != _ALGO:
            return False
        iterations = int(iter_str)
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
    except (ValueError, TypeError):
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(candidate, expected)


# --------------------------------------------------------------------------
# Models
# --------------------------------------------------------------------------
class User(UUIDMixin, TimestampsMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(512))
    is_active: Mapped[bool] = mapped_column(default=True)

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "email": self.email,
            "display_name": self.display_name,
            "created_at": iso_utc(self.created_at),
        }


class UserSession(UUIDMixin, Base):
    __tablename__ = "user_sessions"

    user_id: Mapped[uuid_mod.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(index=True)


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------
_EMAIL_RE = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class RegisterIn(BaseModel):
    email: str = Field(min_length=3, max_length=320, pattern=_EMAIL_RE)
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    id: str
    email: str
    display_name: str
    created_at: str | None = None


class SessionOut(BaseModel):
    token: str
    expires_at: str
    user: UserOut


def _make_session_token() -> str:
    return secrets.token_urlsafe(32)


def _session_expiry(settings: Settings) -> datetime:
    return utcnow() + timedelta(hours=settings.session_ttl_hours)


def _purge_expired_sessions(session: Session) -> None:
    from sqlalchemy import delete

    session.execute(delete(UserSession).where(UserSession.expires_at < utcnow()))


# --------------------------------------------------------------------------
# Business logic
# --------------------------------------------------------------------------
def register_user(
    db: Session, email: str, display_name: str, password: str
) -> User:
    email = email.strip().lower()
    existing = db.scalar(select(User).where(User.email == email))
    if existing:
        raise ConflictError("An account with this email already exists.", code="email_exists")
    user = User(email=email, display_name=display_name.strip(), password_hash=hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info("Registered user %s (%s)", user.id, email)
    return user


def authenticate(db: Session, email: str, password: str) -> User:
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None or not verify_password(password, user.password_hash):
        raise AuthenticationError("Invalid email or password.", code="invalid_credentials")
    if not user.is_active:
        raise PermissionDeniedError("This account is disabled.")
    return user


def create_session(db: Session, user: User) -> tuple[str, datetime]:
    _purge_expired_sessions(db)
    settings: Settings = get_app_state().settings
    token = _make_session_token()
    expiry = _session_expiry(settings)
    db.add(UserSession(user_id=user.id, token_hash=sha256_hex(token), expires_at=expiry))
    db.commit()
    return token, expiry


def resolve_token(db: Session, token: str) -> User:
    if not token:
        raise AuthenticationError("Not authenticated. Provide a bearer token.", code="unauthenticated")
    row = db.scalar(select(UserSession).where(UserSession.token_hash == sha256_hex(token)))
    if row is None or row.expires_at < utcnow():
        raise AuthenticationError("Session is invalid or expired. Please log in again.", code="session_expired")
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("Account not found or disabled.", code="unauthenticated")
    return user


def revoke_session(db: Session, token: str) -> None:
    from sqlalchemy import delete

    db.execute(delete(UserSession).where(UserSession.token_hash == sha256_hex(token)))
    db.commit()


# --------------------------------------------------------------------------
# FastAPI dependencies
# --------------------------------------------------------------------------
def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    header = request.headers.get("authorization", "")
    if header.startswith(_HEADER_PREFIX):
        token = header[len(_HEADER_PREFIX):].strip()
    else:
        token = ""
    return resolve_token(db, token)


def require_active_user(user: User = Depends(get_current_user)) -> User:
    if not user.is_active:
        raise PermissionDeniedError("This account is disabled.")
    return user


# --------------------------------------------------------------------------
# Router
# --------------------------------------------------------------------------
def build_auth_router() -> APIRouter:
    """Returns the `/auth` router. Kept as a factory so each competition repo
    can mount it on its own prefix."""

    def _user_out(user: User) -> UserOut:
        return UserOut(
            id=str(user.id),
            email=user.email,
            display_name=user.display_name,
            created_at=iso_utc(user.created_at),
        )

    router = APIRouter(prefix="/auth", tags=["auth"])

    @router.post("/register", response_model=SessionOut, status_code=201)
    def register(payload: RegisterIn, db: Session = Depends(get_db)) -> SessionOut:
        user = register_user(db, payload.email, payload.display_name, payload.password)
        token, expiry = create_session(db, user)
        return SessionOut(token=token, expires_at=iso_utc(expiry) or "", user=_user_out(user))

    @router.post("/login", response_model=SessionOut)
    def login(payload: LoginIn, db: Session = Depends(get_db)) -> SessionOut:
        user = authenticate(db, payload.email, payload.password)
        token, expiry = create_session(db, user)
        return SessionOut(token=token, expires_at=iso_utc(expiry) or "", user=_user_out(user))

    @router.post("/logout", status_code=204)
    def logout(request: Request, db: Session = Depends(get_db)) -> None:
        header = request.headers.get("authorization", "")
        if header.startswith(_HEADER_PREFIX):
            revoke_session(db, header[len(_HEADER_PREFIX):].strip())

    @router.get("/me", response_model=UserOut)
    def me(user: User = Depends(require_active_user)) -> UserOut:
        return _user_out(user)

    return router


def bootstrap_demo_user() -> None:
    """Create a well-known demo account in development for easy testing."""
    settings: Settings = get_app_state().settings
    if settings.environment != "development" or not settings.auto_create_tables:
        return
    factory = get_app_state().session_factory
    if factory is None:
        return
    with session_scope(factory) as db:
        email = "demo@example.com"
        if db.scalar(select(User).where(User.email == email)) is None:
            db.add(
                User(
                    email=email,
                    display_name="Demo User",
                    password_hash=hash_password("demo-password-123"),
                )
            )
            logger.info("Seeded demo account %s / demo-password-123", email)
