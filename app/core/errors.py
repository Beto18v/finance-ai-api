from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(_: Request, exc: IntegrityError):
        # Avoid leaking DB internals. Provide a clean, stable error surface.
        detail = "Conflict"

        raw = str(getattr(exc, "orig", exc))
        lowered = raw.lower()
        if "unique" in lowered or "duplicate" in lowered:
            detail = "Resource already exists"

        return JSONResponse(status_code=409, content={"detail": detail})

    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_error_handler(_: Request, __: SQLAlchemyError):
        return JSONResponse(status_code=500, content={"detail": "Database error"})
