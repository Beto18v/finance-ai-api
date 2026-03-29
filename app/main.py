from contextlib import asynccontextmanager
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware

from app.core import settings
from app.database.base import Base
from app.database.connection import engine
from app.core.errors import install_exception_handlers
from app.routes import (
    analytics_routes,
    balance_routes,
    category_routes,
    transaction_routes,
    user_routes,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Import models so SQLAlchemy registers them in Base.metadata
    from app.models.user import User  # noqa: F401
    from app.models.category import Category  # noqa: F401
    from app.models.transaction import Transaction  # noqa: F401
    from app.models.exchange_rate import ExchangeRate  # noqa: F401

    # Schema should be managed by Alembic. For local/dev-only convenience you can enable:
    # AUTO_CREATE_TABLES=true
    if os.getenv("AUTO_CREATE_TABLES", "").lower() in {"1", "true", "yes"}:
        Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins(),
    allow_origin_regex=settings.cors_origin_regex(),
    allow_credentials=settings.cors_allow_credentials(),
    allow_methods=settings.cors_allow_methods(),
    allow_headers=settings.cors_allow_headers(),
)
app.add_middleware(GZipMiddleware, minimum_size=500)

if os.getenv("TESTING", "").lower() not in {"1", "true", "yes"}:
    install_exception_handlers(app)


@app.get("/healthz", tags=["System"])
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}

app.include_router(user_routes.router)
app.include_router(category_routes.router)
app.include_router(transaction_routes.router)
app.include_router(balance_routes.router)
app.include_router(analytics_routes.router)
