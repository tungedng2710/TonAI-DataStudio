import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .auth_routes import router as auth_router
from .config import get_settings
from .database import init_db
from .errors import StudioError
from .routes import router
from .storage import create_storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    if settings.storage_backend == "local":
        settings.storage_root.mkdir(parents=True, exist_ok=True)
    settings.staging_root.mkdir(parents=True, exist_ok=True)
    if settings.auto_create_tables:
        init_db()
    app.state.storage = create_storage(settings)
    logger.info("event=application_started environment=%s", settings.environment)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description=(
            "Self-hosted dataset repository API accepting Hugging Face-compatible folder layouts."
        ),
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def correlation_id(request: Request, call_next):  # type: ignore[no-untyped-def]
        correlation = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
        request.state.correlation_id = correlation
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation
        return response

    @app.exception_handler(StudioError)
    async def studio_error(request: Request, exc: StudioError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            media_type="application/problem+json",
            headers={"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None,
            content={
                "type": f"https://data-studio.local/problems/{exc.code}",
                "title": exc.title,
                "status": exc.status_code,
                "detail": exc.detail,
                "code": exc.code,
                "instance": str(request.url.path),
                **exc.extra,
            },
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            media_type="application/problem+json",
            content={
                "type": "https://data-studio.local/problems/request-validation",
                "title": "Request validation failed",
                "status": 422,
                "detail": "The request did not match the API contract.",
                "code": "request_validation",
                "instance": str(request.url.path),
                "errors": jsonable_encoder(exc.errors()),
            },
        )

    @app.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok", "version": "0.1.0"}

    app.include_router(auth_router)
    app.include_router(router)
    return app


app = create_app()
