import os
from pathlib import Path

os.environ["DATA_STUDIO_DATABASE_URL"] = "sqlite:///./data/test-data-studio.db"
os.environ["DATA_STUDIO_STORAGE_BACKEND"] = "local"
os.environ["DATA_STUDIO_STORAGE_ROOT"] = "./data/test-objects"
os.environ["DATA_STUDIO_STAGING_ROOT"] = "./data/test-uploads"
os.environ["DATA_STUDIO_VERSIONING_ROOT"] = "./data/test-repositories"

import pytest
from data_studio_api.config import get_settings
from data_studio_api.database import Base, engine
from data_studio_api.main import app
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def clean_state() -> None:
    settings = get_settings()
    Path("data").mkdir(parents=True, exist_ok=True)
    Base.metadata.drop_all(bind=engine)
    for root in (settings.storage_root, settings.staging_root, settings.versioning_root):
        if root.exists():
            import shutil

            shutil.rmtree(root)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client
