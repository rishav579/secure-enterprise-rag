import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import get_db
from backend.app.api.v1.auth import router as auth_router
from backend.app.config import Settings, get_settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan context manager for startup and shutdown events."""
    current_settings = get_settings()
    logger.info(f"Starting {current_settings.APP_NAME} in [{current_settings.APP_ENV}] mode")
    yield
    logger.info(f"Shutting down {current_settings.APP_NAME}")


def create_app() -> FastAPI:
    """Factory function for FastAPI application."""
    initial_settings = get_settings()
    application = FastAPI(
        title=initial_settings.APP_NAME,
        version="0.1.0",
        docs_url="/docs" if initial_settings.APP_ENV != "production" else None,
        redoc_url="/redoc" if initial_settings.APP_ENV != "production" else None,
        lifespan=lifespan,
    )

    # CORS Middleware
    application.add_middleware(
        CORSMiddleware,
        allow_origins=initial_settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount API routers
    application.include_router(auth_router, prefix="/api/v1")

    @application.get("/", tags=["Root"])
    async def root(settings: Settings = Depends(get_settings)):
        return {
            "name": settings.APP_NAME,
            "status": "online",
            "version": "0.1.0",
            "environment": settings.APP_ENV,
        }

    @application.get("/health", tags=["Monitoring"])
    async def health(
        db: AsyncSession = Depends(get_db),
        settings: Settings = Depends(get_settings),
    ):
        """Health check endpoint that verifies API and database responsiveness."""
        db_status = "healthy"
        try:
            await db.execute(text("SELECT 1"))
        except Exception as exc:
            logger.error(f"Database health check failed: {exc}")
            db_status = f"unhealthy: {type(exc).__name__}"
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"status": "degraded", "database": db_status},
            )

        return {
            "status": "healthy",
            "database": db_status,
            "environment": settings.APP_ENV,
        }

    return application


app = create_app()
