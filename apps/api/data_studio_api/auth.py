import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .database import get_db
from .errors import NotFoundError, StudioError
from .models import ApiToken, DatasetRepository, User, Visibility

SESSION_COOKIE = "cognidoc_data_studio_session"
PASSWORD_ITERATIONS = 600_000
SESSION_SCOPES = frozenset({"read", "write"})


@dataclass(frozen=True)
class Principal:
    user_id: str
    username: str
    is_admin: bool
    scopes: frozenset[str]
    credential: str


def _authentication_error(detail: str = "Sign in to continue.") -> StudioError:
    return StudioError(401, "authentication_required", "Authentication required", detail)


def _forbidden(detail: str) -> StudioError:
    return StudioError(403, "forbidden", "Access denied", detail)


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${_b64encode(salt)}${_b64encode(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations_raw, salt_raw, expected_raw = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_raw)
        if iterations < 100_000 or iterations > 2_000_000:
            return False
        salt = _b64decode(salt_raw)
        expected = _b64decode(expected_raw)
    except (ValueError, TypeError):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def authenticate_user(db: Session, username: str, password: str) -> User:
    normalized = username.strip().lower()
    user = db.scalar(select(User).where(User.username == normalized))
    if user is None:
        hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), b"missing-user-salt", PASSWORD_ITERATIONS
        )
        raise _authentication_error("The username or password is incorrect.")
    if not verify_password(password, user.password_hash):
        raise _authentication_error("The username or password is incorrect.")
    return user


def create_session_token(user: User, settings: Settings) -> str:
    payload = {
        "sub": user.id,
        "exp": int(time.time()) + settings.auth_session_ttl_seconds,
    }
    encoded = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(
        settings.auth_secret_key.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256
    ).digest()
    return f"{encoded}.{_b64encode(signature)}"


def _principal_from_session(db: Session, token: str, settings: Settings) -> Principal:
    try:
        encoded, signature_raw = token.split(".", 1)
        supplied_signature = _b64decode(signature_raw)
        expected_signature = hmac.new(
            settings.auth_secret_key.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(supplied_signature, expected_signature):
            raise ValueError("signature mismatch")
        payload = json.loads(_b64decode(encoded))
        user_id = payload["sub"]
        expires_at = payload["exp"]
        if not isinstance(user_id, str) or not isinstance(expires_at, int):
            raise ValueError("invalid payload")
        if expires_at <= int(time.time()):
            raise ValueError("expired")
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise _authentication_error("The session is invalid or expired.") from exc
    user = db.get(User, user_id)
    if user is None:
        raise _authentication_error("The session user no longer exists.")
    return Principal(user.id, user.username, user.is_admin, SESSION_SCOPES, "session")


def hash_api_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_api_token() -> str:
    return f"ds_pat_{secrets.token_urlsafe(32)}"


def _principal_from_api_token(db: Session, token: str) -> Principal:
    stored = db.scalar(select(ApiToken).where(ApiToken.token_hash == hash_api_token(token)))
    if stored is None:
        raise _authentication_error("The API token is invalid.")
    if stored.expires_at is not None:
        expires_at = stored.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= datetime.now(UTC):
            raise _authentication_error("The API token has expired.")
    user = db.get(User, stored.user_id)
    if user is None:
        raise _authentication_error("The API token user no longer exists.")
    return Principal(
        user.id,
        user.username,
        user.is_admin,
        frozenset(stored.scopes),
        "api_token",
    )


def get_optional_principal(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Principal | None:
    authorization = request.headers.get("Authorization", "")
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise _authentication_error("Use an Authorization: Bearer token header.")
        if token.startswith("ds_pat_"):
            return _principal_from_api_token(db, token)
        return _principal_from_session(db, token, settings)
    cookie = request.cookies.get(SESSION_COOKIE)
    if cookie:
        return _principal_from_session(db, cookie, settings)
    return None


def get_principal(
    principal: Annotated[Principal | None, Depends(get_optional_principal)],
) -> Principal:
    if principal is None:
        raise _authentication_error()
    return principal


def require_scope(principal: Principal, scope: str) -> None:
    if scope not in principal.scopes:
        raise _forbidden(f"This credential does not have the {scope!r} scope.")


def can_read_repository(repository: DatasetRepository, principal: Principal | None) -> bool:
    if repository.visibility == Visibility.public:
        return True
    if principal is None or "read" not in principal.scopes:
        return False
    if repository.visibility == Visibility.internal:
        return True
    return principal.is_admin or repository.owner_id == principal.user_id


def authorize_repository_read(repository: DatasetRepository, principal: Principal | None) -> None:
    if can_read_repository(repository, principal):
        return
    if principal is None:
        raise _authentication_error("Sign in to access this dataset.")
    raise NotFoundError(f"Dataset {repository.namespace}/{repository.slug}")


def authorize_repository_write(repository: DatasetRepository, principal: Principal) -> None:
    require_scope(principal, "write")
    if principal.is_admin or repository.owner_id == principal.user_id:
        return
    raise _forbidden("Only the dataset owner can change this dataset.")
