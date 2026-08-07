from pathlib import Path

from data_studio_api.auth import (
    Principal,
    authorize_repository_read,
    authorize_repository_write,
    create_session_token,
    hash_password,
    verify_password,
)
from data_studio_api.auth_routes import login, register
from data_studio_api.config import Settings
from data_studio_api.database import Base
from data_studio_api.errors import NotFoundError, StudioError
from data_studio_api.models import DatasetRepository, Visibility
from data_studio_api.schemas import UserLogin, UserRegister
from fastapi import Response
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_url="sqlite://",
        storage_backend="local",
        storage_root=tmp_path / "objects",
        staging_root=tmp_path / "uploads",
        auth_secret_key="test-secret-that-is-long-and-stable",
    )


def test_password_hashes_are_salted_and_verified() -> None:
    first = hash_password("correct horse battery staple")
    second = hash_password("correct horse battery staple")
    assert first != second
    assert verify_password("correct horse battery staple", first)
    assert not verify_password("wrong password", first)
    assert not verify_password("anything", "malformed")


def test_first_registration_adopts_existing_datasets_and_login_sets_cookie(
    tmp_path: Path,
) -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    settings = _settings(tmp_path)
    with Session(engine, expire_on_commit=False) as db:
        legacy = DatasetRepository(
            namespace="legacy",
            slug="imported",
            visibility=Visibility.private,
        )
        db.add(legacy)
        db.commit()

        register_response = Response()
        user = register(
            UserRegister(username="owner", password="secure-password"),
            register_response,
            db,
            settings,
        )
        assert user.is_admin
        db.refresh(legacy)
        assert legacy.owner_id == user.id
        assert "httponly" in register_response.headers["set-cookie"].lower()

        login_response = Response()
        logged_in = login(
            UserLogin(username="owner", password="secure-password"),
            login_response,
            db,
            settings,
        )
        assert logged_in.id == user.id
        assert create_session_token(logged_in, settings).count(".") == 1


def test_registration_accepts_blank_optional_profile_fields(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "username": "new-user",
            "display_name": "",
            "email": "",
            "password": "secure-password",
        },
    )

    assert response.status_code == 201
    assert response.json()["display_name"] == "new-user"
    assert response.json()["email"] is None


def test_repository_access_is_public_read_and_owner_write() -> None:
    owner = Principal("owner-id", "owner", False, frozenset({"read", "write"}), "session")
    stranger = Principal("stranger-id", "stranger", False, frozenset({"read", "write"}), "session")
    public = DatasetRepository(
        owner_id=owner.user_id,
        namespace="owner",
        slug="public-data",
        visibility=Visibility.public,
    )
    private = DatasetRepository(
        owner_id=owner.user_id,
        namespace="owner",
        slug="private-data",
        visibility=Visibility.private,
    )

    authorize_repository_read(public, None)
    authorize_repository_read(private, owner)
    authorize_repository_write(private, owner)

    try:
        authorize_repository_read(private, stranger)
    except NotFoundError:
        pass
    else:
        raise AssertionError("a private dataset must be hidden from another user")

    try:
        authorize_repository_write(public, stranger)
    except StudioError as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError("a non-owner must not edit a public dataset")


def test_user_can_manage_profile_password_and_tokens_but_not_username(
    client: TestClient,
) -> None:
    registered = client.post(
        "/api/v1/auth/register",
        json={
            "username": "owner",
            "display_name": "Original name",
            "email": "old@example.com",
            "password": "secure-password",
        },
    )
    assert registered.status_code == 201

    profile = client.patch(
        "/api/v1/auth/me",
        json={"display_name": "New Name", "email": "NEW@example.com"},
    )
    assert profile.status_code == 200
    assert profile.json()["display_name"] == "New Name"
    assert profile.json()["email"] == "new@example.com"
    assert profile.json()["username"] == "owner"

    immutable_username = client.patch("/api/v1/auth/me", json={"username": "renamed"})
    assert immutable_username.status_code == 422
    assert client.get("/api/v1/auth/me").json()["username"] == "owner"

    wrong_password = client.put(
        "/api/v1/auth/password",
        json={"current_password": "wrong-password", "new_password": "replacement-password"},
    )
    assert wrong_password.status_code == 400
    assert wrong_password.json()["code"] == "invalid_current_password"

    changed = client.put(
        "/api/v1/auth/password",
        json={
            "current_password": "secure-password",
            "new_password": "replacement-password",
        },
    )
    assert changed.status_code == 200
    client.post("/api/v1/auth/logout")
    assert client.post(
        "/api/v1/auth/login",
        json={"username": "owner", "password": "secure-password"},
    ).status_code == 401
    assert client.post(
        "/api/v1/auth/login",
        json={"username": "owner", "password": "replacement-password"},
    ).status_code == 200

    created_token = client.post(
        "/api/v1/auth/tokens",
        json={"name": "automation", "scopes": ["read", "write"]},
    )
    assert created_token.status_code == 201
    raw_token = created_token.json()["token"]
    assert raw_token.startswith("ds_pat_")
    token_id = created_token.json()["id"]
    listed_tokens = client.get("/api/v1/auth/tokens")
    assert listed_tokens.status_code == 200
    assert [token["id"] for token in listed_tokens.json()] == [token_id]
    assert "token" not in listed_tokens.json()[0]
    token_cannot_manage_account = client.get(
        "/api/v1/auth/tokens",
        headers={"Authorization": f"Bearer {raw_token}"},
    )
    assert token_cannot_manage_account.status_code == 403
    assert token_cannot_manage_account.json()["code"] == "session_required"
    assert client.delete(f"/api/v1/auth/tokens/{token_id}").status_code == 204
    assert client.get("/api/v1/auth/tokens").json() == []


def test_delete_account_removes_owned_repositories_and_session(client: TestClient) -> None:
    assert client.post(
        "/api/v1/auth/register",
        json={"username": "owner", "password": "secure-password"},
    ).status_code == 201
    assert client.post(
        "/api/v1/datasets",
        json={
            "namespace": "owner",
            "slug": "private-data",
            "visibility": "private",
            "description": "",
        },
    ).status_code == 201

    rejected = client.request(
        "DELETE",
        "/api/v1/auth/me",
        json={"password": "wrong-password"},
    )
    assert rejected.status_code == 400
    assert client.get("/api/v1/auth/me").status_code == 200

    deleted = client.request(
        "DELETE",
        "/api/v1/auth/me",
        json={"password": "secure-password"},
    )
    assert deleted.status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/datasets/owner/private-data").status_code == 404
    assert client.post(
        "/api/v1/auth/login",
        json={"username": "owner", "password": "secure-password"},
    ).status_code == 401


def test_user_can_upload_and_replace_a_limited_avatar(client: TestClient) -> None:
    registered = client.post(
        "/api/v1/auth/register",
        json={"username": "owner", "password": "secure-password"},
    )
    assert registered.status_code == 201
    assert registered.json()["avatar_updated_at"] is None

    png = b"\x89PNG\r\n\x1a\n" + b"avatar-content"
    uploaded = client.put(
        "/api/v1/auth/avatar",
        files={"avatar": ("avatar.png", png, "image/png")},
    )
    assert uploaded.status_code == 200
    assert uploaded.json()["avatar_updated_at"] is not None

    downloaded = client.get("/api/v1/auth/users/owner/avatar")
    assert downloaded.status_code == 200
    assert downloaded.headers["content-type"] == "image/png"
    assert downloaded.content == png

    unsupported = client.put(
        "/api/v1/auth/avatar",
        files={"avatar": ("avatar.txt", b"not-an-image", "text/plain")},
    )
    assert unsupported.status_code == 415
    assert unsupported.json()["code"] == "unsupported_avatar_type"

    oversized = client.put(
        "/api/v1/auth/avatar",
        files={
            "avatar": (
                "large.png",
                b"\x89PNG\r\n\x1a\n" + b"x" * (2 * 1024 * 1024),
                "image/png",
            )
        },
    )
    assert oversized.status_code == 413
    assert oversized.json()["code"] == "avatar_too_large"


def test_dataset_list_can_be_filtered_by_repository_owner(client: TestClient) -> None:
    assert client.post(
        "/api/v1/auth/register",
        json={"username": "owner", "password": "secure-password"},
    ).status_code == 201
    assert client.post(
        "/api/v1/datasets",
        json={"namespace": "owner", "slug": "first", "visibility": "private"},
    ).status_code == 201
    client.post("/api/v1/auth/logout")

    assert client.post(
        "/api/v1/auth/register",
        json={"username": "second", "password": "secure-password"},
    ).status_code == 201
    assert client.post(
        "/api/v1/datasets",
        json={"namespace": "second", "slug": "second", "visibility": "private"},
    ).status_code == 201
    client.post("/api/v1/auth/logout")
    assert client.post(
        "/api/v1/auth/login",
        json={"username": "owner", "password": "secure-password"},
    ).status_code == 200

    owner_items = client.get("/api/v1/datasets?owner=owner").json()["items"]
    second_items = client.get("/api/v1/datasets?owner=second").json()["items"]
    assert [item["slug"] for item in owner_items] == ["first"]
    assert [item["slug"] for item in second_items] == ["second"]


def test_users_can_be_searched_and_public_profiles_hide_private_fields(
    client: TestClient,
) -> None:
    assert (
        client.post(
            "/api/v1/auth/register",
            json={
                "username": "owner",
                "display_name": "Dataset Owner",
                "email": "owner@example.com",
                "password": "secure-password",
            },
        ).status_code
        == 201
    )
    client.post("/api/v1/auth/logout")
    assert (
        client.post(
            "/api/v1/auth/register",
            json={
                "username": "researcher",
                "display_name": "Vision Researcher",
                "email": "researcher@example.com",
                "password": "secure-password",
            },
        ).status_code
        == 201
    )
    client.post("/api/v1/auth/logout")

    search = client.get("/api/v1/auth/users?q=vision")
    assert search.status_code == 200
    assert [item["username"] for item in search.json()["items"]] == ["researcher"]
    assert "email" not in search.json()["items"][0]
    assert "is_admin" not in search.json()["items"][0]

    profile = client.get("/api/v1/auth/users/OWNER")
    assert profile.status_code == 200
    assert profile.json()["display_name"] == "Dataset Owner"
    assert "email" not in profile.json()
    assert client.get("/api/v1/auth/users/missing-user").status_code == 404


def test_users_can_follow_and_unfollow_other_users(client: TestClient) -> None:
    assert client.post(
        "/api/v1/auth/register",
        json={"username": "owner", "password": "secure-password"},
    ).status_code == 201
    client.post("/api/v1/auth/logout")
    assert client.post(
        "/api/v1/auth/register",
        json={"username": "researcher", "password": "secure-password"},
    ).status_code == 201

    initial = client.get("/api/v1/auth/users/owner")
    assert initial.status_code == 200
    assert initial.json()["followers_count"] == 0
    assert initial.json()["following_count"] == 0
    assert initial.json()["is_following"] is False

    followed = client.put("/api/v1/auth/users/owner/follow")
    assert followed.status_code == 200, followed.text
    assert followed.json()["followers_count"] == 1
    assert followed.json()["is_following"] is True

    repeated = client.put("/api/v1/auth/users/owner/follow")
    assert repeated.status_code == 200
    assert repeated.json()["followers_count"] == 1

    search_result = client.get("/api/v1/auth/users?q=owner").json()["items"][0]
    assert search_result["followers_count"] == 1
    assert search_result["is_following"] is True

    followers = client.get("/api/v1/auth/users/owner/followers?offset=0&limit=10")
    assert followers.status_code == 200
    assert followers.json()["total"] == 1
    assert [item["username"] for item in followers.json()["items"]] == ["researcher"]

    following = client.get("/api/v1/auth/users/researcher/following?offset=0&limit=10")
    assert following.status_code == 200
    assert following.json()["total"] == 1
    assert [item["username"] for item in following.json()["items"]] == ["owner"]
    assert following.json()["items"][0]["is_following"] is True

    own_profile = client.get("/api/v1/auth/users/researcher")
    assert own_profile.json()["following_count"] == 1
    assert own_profile.json()["is_following"] is False

    self_follow = client.put("/api/v1/auth/users/researcher/follow")
    assert self_follow.status_code == 422
    assert self_follow.json()["code"] == "cannot_follow_self"

    unfollowed = client.delete("/api/v1/auth/users/owner/follow")
    assert unfollowed.status_code == 200
    assert unfollowed.json()["followers_count"] == 0
    assert unfollowed.json()["is_following"] is False
    assert client.delete("/api/v1/auth/users/owner/follow").status_code == 200

    client.post("/api/v1/auth/logout")
    anonymous = client.put("/api/v1/auth/users/owner/follow")
    assert anonymous.status_code == 401
    assert client.get("/api/v1/auth/users/missing-user/followers").status_code == 404


def test_dataset_search_only_returns_repositories_visible_to_the_visitor(
    client: TestClient,
) -> None:
    assert client.post(
        "/api/v1/auth/register",
        json={"username": "owner", "password": "secure-password"},
    ).status_code == 201
    for slug, visibility in (("public-cats", "public"), ("private-cats", "private")):
        assert client.post(
            "/api/v1/datasets",
            json={
                "namespace": "owner",
                "slug": slug,
                "visibility": visibility,
                "description": "Cat image collection",
                "tags": ["computer-vision"],
            },
        ).status_code == 201
    client.post("/api/v1/auth/logout")

    results = client.get("/api/v1/datasets?search=cats&limit=8")
    assert results.status_code == 200
    assert [item["slug"] for item in results.json()["items"]] == ["public-cats"]

    tag_results = client.get("/api/v1/datasets?search=computer-vision&limit=1")
    assert [item["slug"] for item in tag_results.json()["items"]] == ["public-cats"]
