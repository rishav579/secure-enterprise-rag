from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from backend.app.config import get_settings

settings = get_settings()


class Base(DeclarativeBase):
    """Base declarative class for all SQLAlchemy ORM models."""
    pass


def create_engine_for_url(url: str, echo: bool = False) -> AsyncEngine:
    """Create async SQLAlchemy engine with connection parameters tailored to backend driver."""
    # Ensure URL is normalized to asyncpg if legacy/cloud postgres scheme is passed directly
    normalized_url = url.strip()
    if normalized_url.startswith("postgres://"):
        normalized_url = "postgresql+asyncpg://" + normalized_url[len("postgres://"):]
    elif normalized_url.startswith("postgresql://"):
        normalized_url = "postgresql+asyncpg://" + normalized_url[len("postgresql://"):]

    kwargs = {"echo": echo}
    if "sqlite" not in normalized_url:
        kwargs["pool_size"] = settings.DB_POOL_SIZE
        kwargs["max_overflow"] = settings.DB_MAX_OVERFLOW
        kwargs["pool_pre_ping"] = True
        kwargs["pool_recycle"] = 1800

    return create_async_engine(normalized_url, **kwargs)


engine = create_engine_for_url(settings.DATABASE_URL, echo=settings.DB_ECHO)
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that yields an async database session and guarantees cleanup."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
