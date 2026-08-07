from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DATA_STUDIO_", env_file=".env", extra="ignore")

    app_name: str = "TonAI Data Studio"
    environment: str = "development"
    auto_create_tables: bool = True
    database_url: str = "sqlite:///./data/data-studio.db"
    storage_backend: str = "local"
    storage_root: Path = Path("./data/objects")
    staging_root: Path = Path("./data/uploads")
    versioning_enabled: bool = True
    versioning_root: Path = Path("./data/repositories")
    dvc_remote_url: str | None = None
    dvc_remote_name: str = "storage"
    git_executable: str = "git"
    dvc_executable: str = "dvc"
    versioning_command_timeout_seconds: int = Field(default=30 * 60, ge=30, le=24 * 60 * 60)
    s3_endpoint_url: str = "http://rustfs:9000"
    s3_access_key: str = "rustfsadmin"
    s3_secret_key: str = "rustfsadmin"
    s3_region: str = "us-east-1"
    s3_bucket: str = "datasets"
    s3_connect_retries: int = Field(default=30, ge=1, le=120)
    redis_url: str = "redis://localhost:6379/0"
    max_upload_bytes: int = Field(default=2 * 1024 * 1024 * 1024, ge=0)
    max_file_bytes: int = Field(default=512 * 1024 * 1024, ge=0)
    max_file_count: int = Field(default=10_000, ge=0)
    preview_rows: int = Field(default=100, ge=1, le=1_000)
    viewer_image_max_bytes: int = Field(default=25 * 1024 * 1024, ge=1)
    viewer_image_max_pixels: int = Field(default=40_000_000, ge=1)
    viewer_thumbnail_size: int = Field(default=320, ge=64, le=1_024)
    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    auth_secret_key: str = "development-only-change-me"
    auth_session_ttl_seconds: int = Field(default=7 * 24 * 60 * 60, ge=300)
    auth_cookie_secure: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
