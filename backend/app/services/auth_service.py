from datetime import datetime, timedelta, timezone
import secrets

import jwt
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from pwdlib import PasswordHash

from app.core.config import settings
from app.models.user import User, UserRole
from app.schemas.auth import ManagedUserCreate, RegisterRequest


password_hash = PasswordHash.recommended()
_development_secret = secrets.token_urlsafe(48)


def _signing_secret() -> str:
    configured_secret = (settings.session_secret or "").strip()
    if len(configured_secret) >= 32:
        return configured_secret
    if settings.app_env.lower() in {"development", "test"}:
        return _development_secret
    raise RuntimeError(
        "SESSION_SECRET must be configured with at least 32 characters."
    )


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return password_hash.verify(password, hashed_password)


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email.lower()))


def register_user(db: Session, payload: RegisterRequest) -> User:
    if get_user_by_email(db, payload.email):
        raise ValueError("An account with this email already exists.")

    user_count = db.scalar(select(func.count(User.id))) or 0
    user = User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role=UserRole.ADMIN if user_count == 0 else UserRole.VIEWER,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def create_managed_user(db: Session, payload: ManagedUserCreate) -> User:
    if get_user_by_email(db, payload.email):
        raise ValueError("An account with this email already exists.")
    user = User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    user = get_user_by_email(db, email)
    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


def create_access_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": str(user.id),
        "role": user.role.value,
        "iat": now,
        "exp": expires_at,
    }
    return jwt.encode(payload, _signing_secret(), algorithm=settings.jwt_algorithm)


def user_from_token(db: Session, token: str) -> User | None:
    try:
        payload = jwt.decode(
            token,
            _signing_secret(),
            algorithms=[settings.jwt_algorithm],
        )
        subject = payload.get("sub")
        user_id = int(subject)
    except (jwt.InvalidTokenError, TypeError, ValueError):
        return None

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        return None
    return user


def update_user_role(db: Session, user: User, role: UserRole) -> User:
    user.role = role
    db.commit()
    db.refresh(user)
    return user