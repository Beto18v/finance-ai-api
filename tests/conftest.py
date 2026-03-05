import sys
from pathlib import Path
import os
import uuid

# Ensure project root is on sys.path so `import app.*` works in pytest.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("TESTING", "1")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.database.session import get_db
from app.main import app


@pytest.fixture(scope="session")
def test_user_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture(scope="session")
def test_claims(test_user_id: uuid.UUID) -> dict:
    return {
        "sub": str(test_user_id),
        "email": "test@example.com",
        "user_metadata": {"name": "Test User"},
    }


@pytest.fixture(scope="session")
def engine():
    engine_ = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # Import models so SQLAlchemy registers them
    from app.models.user import User
    from app.models.category import Category
    from app.models.transaction import Transaction

    _ = (User, Category, Transaction)

    Base.metadata.create_all(bind=engine_)
    return engine_


@pytest.fixture()
def db_session(engine):
    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
        bind=engine,
    )

    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def client(db_session, test_user_id, test_claims):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    # Override auth dependencies
    from app.core import auth as auth_module

    def override_get_current_user_id():
        return test_user_id

    def override_get_current_user_claims():
        return test_claims

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[auth_module.get_current_user_id] = override_get_current_user_id
    app.dependency_overrides[auth_module.get_current_user_claims] = override_get_current_user_claims

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
