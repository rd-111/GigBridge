"""FastAPI application assembly."""

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.responses import Response
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import engine
from app.middleware.request_id import RequestIdFilter, RequestIdMiddleware
from app.integrations.paypal.client import PayPalAPIClient
from app.integrations.paypal.exceptions import PayPalError

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)
for handler in logging.getLogger().handlers:
    handler.addFilter(RequestIdFilter())


def error_payload(request: Request, code: str, message: str) -> dict[str, str]:
    """Build the standard API error envelope."""

    return {
        "code": code,
        "message": message,
        "request_id": getattr(request.state, "request_id", "-"),
    }


async def check_database_ready() -> None:
    """Execute a small query to confirm the database is reachable."""

    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Create shared outbound client and release process pools on shutdown."""

    application.state.paypal_client = PayPalAPIClient(settings)
    yield
    await application.state.paypal_client.close()
    await engine.dispose()


def create_app() -> FastAPI:
    """Create and configure a GigBridge API instance."""

    application = FastAPI(
        title=settings.app_name,
        description="Backend API foundation for GigBridge.",
        version="0.1.0",
        debug=settings.debug,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    application.add_middleware(RequestIdMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_url],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Validation details include submitted inputs; avoid logging passwords or tokens.
        logger.info("Request validation failed")
        return JSONResponse(
            status_code=422,
            content=error_payload(request, "VALIDATION_ERROR", "The request data is invalid."),
        )

    @application.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = "NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR"
        message = str(exc.detail) if isinstance(exc.detail, str) else "The request could not be completed."
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(request, code, message),
            headers=exc.headers,
        )

    @application.exception_handler(HTTPException)
    async def fastapi_http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
        return await http_error_handler(request, exc)

    @application.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled request error")
        return JSONResponse(
            status_code=500,
            content=error_payload(request, "INTERNAL_SERVER_ERROR", "An unexpected error occurred."),
        )

    @application.exception_handler(PayPalError)
    async def paypal_error_handler(request: Request, exc: PayPalError) -> JSONResponse:
        from app.integrations.paypal.exceptions import (
            PayPalAuthenticationError, PayPalConfigurationError, PayPalPermissionError,
            PayPalRateLimitError, PayPalTimeoutError, PayPalUnavailableError,
        )

        if isinstance(exc, PayPalConfigurationError):
            status_code, code = 503, "PAYPAL_NOT_CONFIGURED"
        elif isinstance(exc, PayPalAuthenticationError):
            status_code, code = 502, "PAYPAL_AUTHENTICATION_FAILED"
        elif isinstance(exc, PayPalPermissionError):
            status_code, code = 403, "PAYPAL_PERMISSION_UNAVAILABLE"
        elif isinstance(exc, PayPalRateLimitError):
            status_code, code = 429, "PAYPAL_RATE_LIMITED"
        elif isinstance(exc, PayPalTimeoutError):
            status_code, code = 504, "PAYPAL_TIMEOUT"
        elif isinstance(exc, PayPalUnavailableError):
            status_code, code = 503, "PAYPAL_UNAVAILABLE"
        else:
            status_code, code = 502, "PAYPAL_API_ERROR"
        return JSONResponse(status_code=status_code, content=error_payload(request, code, str(exc)))

    @application.get("/api/v1", include_in_schema=False)
    async def api_root() -> Response:
        """Keep the versioned API root available while no domain routes exist."""

        return Response(status_code=204)

    @application.get("/health/live", tags=["health"], summary="Liveness check")
    async def live() -> dict[str, str]:
        """Report that the API process can serve requests."""

        return {"status": "ok"}

    @application.get("/health/ready", tags=["health"], summary="Readiness check")
    async def ready(request: Request) -> Any:
        """Check that PostgreSQL can execute a lightweight query."""

        try:
            await check_database_ready()
        except SQLAlchemyError:
            logger.exception("Database readiness check failed")
            return JSONResponse(
                status_code=503,
                content=error_payload(request, "SERVICE_UNAVAILABLE", "Database is not ready."),
            )
        return {"status": "ok", "database": "ok"}

    application.include_router(api_router, prefix="/api/v1")
    return application


app = create_app()
