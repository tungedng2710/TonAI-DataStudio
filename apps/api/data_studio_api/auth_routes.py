import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import (
    SESSION_COOKIE,
    Principal,
    authenticate_user,
    create_session_token,
    get_optional_principal,
    get_principal,
    hash_api_token,
    hash_password,
    issue_api_token,
    require_scope,
    verify_password,
)
from .config import Settings, get_settings
from .database import get_db
from .errors import ConflictError, NotFoundError, StudioError
from .models import ApiToken, DatasetRepository, User, UserFollow, utcnow
from .schemas import (
    AccountDelete,
    ApiTokenCreate,
    ApiTokenCreated,
    ApiTokenRead,
    PasswordChange,
    PublicUserList,
    PublicUserRead,
    UserLogin,
    UserProfileUpdate,
    UserRead,
    UserRegister,
    UserSearchResults,
)
from .service import DatasetService
from .storage import ObjectStorage

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])
Database = Annotated[Session, Depends(get_db)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]
CurrentPrincipal = Annotated[Principal, Depends(get_principal)]
OptionalPrincipal = Annotated[Principal | None, Depends(get_optional_principal)]
AVATAR_MAX_BYTES = 2 * 1024 * 1024


def _set_session_cookie(response: Response, user: User, settings: Settings) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        create_session_token(user, settings),
        max_age=settings.auth_session_ttl_seconds,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )


def _require_session(principal: Principal) -> None:
    if principal.credential != "session":
        raise StudioError(
            403,
            "session_required",
            "Browser session required",
            "Manage account settings from a signed-in browser session.",
        )


def _require_current_password(user: User, password: str) -> None:
    if not verify_password(password, user.password_hash):
        raise StudioError(
            400,
            "invalid_current_password",
            "Incorrect password",
            "The current password is incorrect.",
        )


def _avatar_file_type(content: bytes) -> tuple[str, str]:
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", "png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", "jpg"
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return "image/webp", "webp"
    raise StudioError(
        415,
        "unsupported_avatar_type",
        "Unsupported image",
        "Use a PNG, JPEG, or WebP image.",
    )


def _public_user_payload(
    db: Session,
    user: User,
    principal: Principal | None,
) -> dict[str, object]:
    followers_count = db.scalar(
        select(func.count()).select_from(UserFollow).where(UserFollow.followed_id == user.id)
    )
    following_count = db.scalar(
        select(func.count()).select_from(UserFollow).where(UserFollow.follower_id == user.id)
    )
    is_following = False
    if principal is not None and principal.user_id != user.id:
        is_following = (
            db.scalar(
                select(UserFollow.follower_id).where(
                    UserFollow.follower_id == principal.user_id,
                    UserFollow.followed_id == user.id,
                )
            )
            is not None
        )
    return {
        "username": user.username,
        "display_name": user.display_name,
        "avatar_updated_at": user.avatar_updated_at,
        "created_at": user.created_at,
        "followers_count": followers_count or 0,
        "following_count": following_count or 0,
        "is_following": is_following,
    }


@router.post("/register", response_model=UserRead, status_code=201)
def register(
    body: UserRegister,
    response: Response,
    db: Database,
    settings: SettingsDependency,
) -> User:
    username = body.username.strip().lower()
    email = body.email.strip().lower() if body.email else None
    is_first_user = (db.scalar(select(func.count()).select_from(User)) or 0) == 0
    user = User(
        username=username,
        display_name=body.display_name.strip() or username,
        email=email,
        password_hash=hash_password(body.password),
        is_admin=is_first_user,
    )
    db.add(user)
    try:
        db.flush()
        if is_first_user:
            db.execute(
                update(DatasetRepository)
                .where(DatasetRepository.owner_id.is_(None))
                .values(owner_id=user.id)
            )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("That username or email is already registered.") from exc
    db.refresh(user)
    _set_session_cookie(response, user, settings)
    return user


@router.post("/login", response_model=UserRead)
def login(
    body: UserLogin,
    response: Response,
    db: Database,
    settings: SettingsDependency,
) -> User:
    user = authenticate_user(db, body.username, body.password)
    _set_session_cookie(response, user, settings)
    return user


@router.post("/logout", status_code=204)
def logout(response: Response) -> Response:
    response.delete_cookie(SESSION_COOKIE, path="/", samesite="lax")
    response.status_code = 204
    return response


@router.get("/me", response_model=UserRead)
def me(principal: CurrentPrincipal, db: Database) -> User:
    user = db.get(User, principal.user_id)
    if user is None:
        raise NotFoundError("User")
    return user


@router.get("/users", response_model=UserSearchResults)
def search_users(
    db: Database,
    principal: OptionalPrincipal,
    q: Annotated[str, Query(min_length=1, max_length=64)],
    limit: Annotated[int, Query(ge=1, le=20)] = 8,
) -> dict[str, list[dict[str, object]]]:
    query = q.strip().lower()
    if not query:
        return {"items": []}
    users = list(
        db.scalars(
            select(User)
            .where(
                or_(
                    func.lower(User.username).contains(query, autoescape=True),
                    func.lower(User.display_name).contains(query, autoescape=True),
                )
            )
            .order_by(User.username)
            .limit(limit)
        ).all()
    )
    return {"items": [_public_user_payload(db, user, principal) for user in users]}


@router.get("/users/{username}", response_model=PublicUserRead)
def read_public_user(
    username: str,
    db: Database,
    principal: OptionalPrincipal,
) -> dict[str, object]:
    user = db.scalar(select(User).where(User.username == username.strip().lower()))
    if user is None:
        raise NotFoundError("User")
    return _public_user_payload(db, user, principal)


@router.get("/users/{username}/followers", response_model=PublicUserList)
def list_followers(
    username: str,
    db: Database,
    principal: OptionalPrincipal,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> dict[str, object]:
    user = db.scalar(select(User).where(User.username == username.strip().lower()))
    if user is None:
        raise NotFoundError("User")
    total = db.scalar(
        select(func.count()).select_from(UserFollow).where(UserFollow.followed_id == user.id)
    )
    users = list(
        db.scalars(
            select(User)
            .join(UserFollow, UserFollow.follower_id == User.id)
            .where(UserFollow.followed_id == user.id)
            .order_by(User.username)
            .offset(offset)
            .limit(limit)
        ).all()
    )
    return {
        "items": [_public_user_payload(db, item, principal) for item in users],
        "total": total or 0,
        "offset": offset,
        "limit": limit,
    }


@router.get("/users/{username}/following", response_model=PublicUserList)
def list_following(
    username: str,
    db: Database,
    principal: OptionalPrincipal,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> dict[str, object]:
    user = db.scalar(select(User).where(User.username == username.strip().lower()))
    if user is None:
        raise NotFoundError("User")
    total = db.scalar(
        select(func.count()).select_from(UserFollow).where(UserFollow.follower_id == user.id)
    )
    users = list(
        db.scalars(
            select(User)
            .join(UserFollow, UserFollow.followed_id == User.id)
            .where(UserFollow.follower_id == user.id)
            .order_by(User.username)
            .offset(offset)
            .limit(limit)
        ).all()
    )
    return {
        "items": [_public_user_payload(db, item, principal) for item in users],
        "total": total or 0,
        "offset": offset,
        "limit": limit,
    }


@router.put("/users/{username}/follow", response_model=PublicUserRead)
def follow_user(
    username: str,
    principal: CurrentPrincipal,
    db: Database,
) -> dict[str, object]:
    require_scope(principal, "write")
    user = db.scalar(select(User).where(User.username == username.strip().lower()))
    if user is None:
        raise NotFoundError("User")
    if user.id == principal.user_id:
        raise StudioError(
            422,
            "cannot_follow_self",
            "Cannot follow yourself",
            "Choose another user to follow.",
        )
    key = (principal.user_id, user.id)
    if db.get(UserFollow, key) is None:
        db.add(UserFollow(follower_id=principal.user_id, followed_id=user.id))
        db.commit()
    return _public_user_payload(db, user, principal)


@router.delete("/users/{username}/follow", response_model=PublicUserRead)
def unfollow_user(
    username: str,
    principal: CurrentPrincipal,
    db: Database,
) -> dict[str, object]:
    require_scope(principal, "write")
    user = db.scalar(select(User).where(User.username == username.strip().lower()))
    if user is None:
        raise NotFoundError("User")
    follow = db.get(UserFollow, (principal.user_id, user.id))
    if follow is not None:
        db.delete(follow)
        db.commit()
    return _public_user_payload(db, user, principal)


@router.patch("/me", response_model=UserRead)
def update_profile(
    body: UserProfileUpdate,
    principal: CurrentPrincipal,
    db: Database,
) -> User:
    _require_session(principal)
    user = db.get(User, principal.user_id)
    if user is None:
        raise NotFoundError("User")
    if "display_name" in body.model_fields_set and body.display_name is not None:
        user.display_name = body.display_name
    if "email" in body.model_fields_set:
        user.email = body.email
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("That email is already registered.") from exc
    db.refresh(user)
    return user


@router.put("/avatar", response_model=UserRead)
async def update_avatar(
    request: Request,
    principal: CurrentPrincipal,
    db: Database,
    avatar: Annotated[UploadFile, File(description="PNG, JPEG, or WebP avatar")],
) -> User:
    _require_session(principal)
    user = db.get(User, principal.user_id)
    if user is None:
        raise NotFoundError("User")
    content = await avatar.read(AVATAR_MAX_BYTES + 1)
    if not content:
        raise StudioError(422, "empty_avatar", "Empty image", "Choose a non-empty image file.")
    if len(content) > AVATAR_MAX_BYTES:
        raise StudioError(
            413,
            "avatar_too_large",
            "Image too large",
            "Avatar images must be 2 MB or smaller.",
        )
    media_type, suffix = _avatar_file_type(content)
    object_key = f"users/avatars/{user.id}/{uuid.uuid4().hex}.{suffix}"
    storage: ObjectStorage = request.app.state.storage
    storage.put_bytes(object_key, content, media_type)
    previous_key = user.avatar_object_key
    user.avatar_object_key = object_key
    user.avatar_media_type = media_type
    user.avatar_updated_at = utcnow()
    db.commit()
    db.refresh(user)
    if previous_key and previous_key != object_key:
        storage.delete_objects([previous_key])
    return user


@router.get("/users/{username}/avatar")
def read_avatar(username: str, request: Request, db: Database) -> StreamingResponse:
    user = db.scalar(select(User).where(User.username == username.strip().lower()))
    if user is None or user.avatar_object_key is None or user.avatar_media_type is None:
        raise NotFoundError("User avatar")
    storage: ObjectStorage = request.app.state.storage
    return StreamingResponse(
        storage.iter_object(user.avatar_object_key),
        media_type=user.avatar_media_type,
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.put("/password", response_model=UserRead)
def change_password(
    body: PasswordChange,
    response: Response,
    principal: CurrentPrincipal,
    db: Database,
    settings: SettingsDependency,
) -> User:
    _require_session(principal)
    user = db.get(User, principal.user_id)
    if user is None:
        raise NotFoundError("User")
    _require_current_password(user, body.current_password)
    if verify_password(body.new_password, user.password_hash):
        raise StudioError(
            400,
            "password_unchanged",
            "Choose a new password",
            "The new password must be different from the current password.",
        )
    user.password_hash = hash_password(body.new_password)
    db.commit()
    db.refresh(user)
    _set_session_cookie(response, user, settings)
    return user


@router.get("/tokens", response_model=list[ApiTokenRead])
def list_tokens(principal: CurrentPrincipal, db: Database) -> list[ApiToken]:
    _require_session(principal)
    return list(
        db.scalars(
            select(ApiToken)
            .where(ApiToken.user_id == principal.user_id)
            .order_by(ApiToken.created_at.desc())
        ).all()
    )


@router.post("/tokens", response_model=ApiTokenCreated, status_code=201)
def create_token(
    body: ApiTokenCreate,
    principal: CurrentPrincipal,
    db: Database,
) -> dict[str, object]:
    _require_session(principal)
    require_scope(principal, "write")
    raw_token = issue_api_token()
    stored = ApiToken(
        user_id=principal.user_id,
        name=body.name.strip(),
        token_prefix=raw_token[:14],
        token_hash=hash_api_token(raw_token),
        scopes=body.scopes,
    )
    db.add(stored)
    db.commit()
    db.refresh(stored)
    return {
        "id": stored.id,
        "name": stored.name,
        "token_prefix": stored.token_prefix,
        "scopes": stored.scopes,
        "expires_at": stored.expires_at,
        "last_used_at": stored.last_used_at,
        "created_at": stored.created_at,
        "token": raw_token,
    }


@router.delete("/tokens/{token_id}", status_code=204)
def delete_token(token_id: str, principal: CurrentPrincipal, db: Database) -> Response:
    _require_session(principal)
    token = db.scalar(
        select(ApiToken).where(
            ApiToken.id == token_id,
            ApiToken.user_id == principal.user_id,
        )
    )
    if token is None:
        raise NotFoundError("API token")
    db.delete(token)
    db.commit()
    return Response(status_code=204)


@router.delete("/me", status_code=204)
def delete_account(
    body: AccountDelete,
    request: Request,
    response: Response,
    principal: CurrentPrincipal,
    db: Database,
    settings: SettingsDependency,
) -> Response:
    _require_session(principal)
    user = db.get(User, principal.user_id)
    if user is None:
        raise NotFoundError("User")
    _require_current_password(user, body.password)

    storage: ObjectStorage = request.app.state.storage
    datasets = DatasetService(db, storage, settings)
    repositories = list(
        db.execute(
            select(DatasetRepository.namespace, DatasetRepository.slug).where(
                DatasetRepository.owner_id == user.id
            )
        ).all()
    )
    for namespace, slug in repositories:
        datasets.delete_repository(namespace, slug)

    if user.avatar_object_key:
        storage.delete_objects([user.avatar_object_key])
    db.execute(
        delete(UserFollow).where(
            or_(UserFollow.follower_id == user.id, UserFollow.followed_id == user.id)
        )
    )
    db.execute(delete(ApiToken).where(ApiToken.user_id == user.id))
    db.delete(user)
    db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/", samesite="lax")
    response.status_code = 204
    return response
