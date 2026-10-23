from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

TEST_ROOT = Path(tempfile.mkdtemp(prefix="legal-mvp-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_ROOT / 'test.db'}"
os.environ["DATA_DIR"] = str(TEST_ROOT / "data")
os.environ["SECRET_KEY"] = "test-secret"
os.environ["RUN_WORKER_INPROCESS"] = "false"
os.environ["ADMIN_EMAIL"] = "admin@example.com"
os.environ["ADMIN_PASSWORD"] = "secret123"
os.environ["OCR_PROVIDER"] = "none"
os.environ["EMBEDDING_PROVIDER"] = "hash"
os.environ["ENVIRONMENT"] = "test"


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def admin_client(client):
    response = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "secret123"},
    )
    assert response.status_code == 200, response.text
    return client
