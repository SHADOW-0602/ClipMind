from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
TEST_DATA = BACKEND / ".pytest-data"
if TEST_DATA.exists():
    shutil.rmtree(TEST_DATA, ignore_errors=True)
TEST_DATA.mkdir(parents=True, exist_ok=True)

os.environ["DATA_DIR"] = str(TEST_DATA)
os.environ["DATABASE_URL"] = f"sqlite:///{(TEST_DATA / 'test.db').as_posix()}"
os.environ["MOCK_MODE"] = "true"
os.environ["PROVIDER"] = "mock"
os.environ["AUTO_RESUME_JOBS"] = "false"
os.environ["PUBLIC_API_URL"] = "http://testserver"
os.environ["RATE_LIMIT_PER_MINUTE"] = "1000"
os.environ["MAX_UPLOAD_MB"] = "500"

from app.db import init_db, reset_engine  # noqa: E402
from app.providers import reset_provider  # noqa: E402

reset_engine()
init_db()
reset_provider()


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
