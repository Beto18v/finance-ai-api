import sys
from pathlib import Path
import os
import uuid
import asyncio

# Ensure project root is on sys.path so `import app.*` works in pytest.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("TESTING", "1")

import pytest
import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.database.session import get_db
from app.main import app


class CompatTestClient:
    def __init__(self, app_, base_url: str = "http://testserver"):
        self.app = app_
        self.base_url = base_url
        self.headers = {"user-agent": "testclient"}

    def request(self, method: str, url: str, **kwargs):
        async def send():
            transport = httpx.ASGITransport(app=self.app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url=self.base_url,
                headers=self.headers,
                follow_redirects=True,
            ) as client:
                return await client.request(method, url, **kwargs)

        return asyncio.run(send())

    def get(self, url: str, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs):
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs):
        return self.request("PUT", url, **kwargs)

    def delete(self, url: str, **kwargs):
        return self.request("DELETE", url, **kwargs)

    def options(self, url: str, **kwargs):
        return self.request("OPTIONS", url, **kwargs)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


@pytest.fixture()
def test_user_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture()
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
    from app.models.exchange_rate import ExchangeRate

    _ = (User, Category, Transaction, ExchangeRate)

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
        # Keep one in-memory SQLite engine for the suite, but reset data per test.
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(table.delete())
        db.commit()

        yield db
    finally:
        db.rollback()
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

    with CompatTestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
