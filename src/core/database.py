"""Database configuration and session management."""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import create_engine, event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from .settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# SQLAlchemy Base for ORM models
Base = declarative_base()

# Sync engine for migrations and non-async operations
sync_engine = create_engine(
    settings.database_url,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    pool_timeout=settings.database_pool_timeout,
    pool_recycle=settings.database_pool_recycle,
    echo=settings.debug,
)

# Async engine for FastAPI (only create if asyncpg is available)
async_engine = None
try:
    import asyncpg  # noqa: F401
    async_database_url = settings.database_url.replace("postgresql://", "postgresql+asyncpg://")
    async_engine = create_async_engine(
        async_database_url,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_timeout=settings.database_pool_timeout,
        pool_recycle=settings.database_pool_recycle,
        echo=settings.debug,
    )
except ImportError:
    logger.warning("asyncpg not available, async engine not created")

# Session makers
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=sync_engine,
)

AsyncSessionLocal = None
if async_engine:
    AsyncSessionLocal = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )


@event.listens_for(sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Set up Row-Level Security context on connection."""
    if "postgresql" in str(dbapi_connection):
        try:
            with dbapi_connection.cursor() as cursor:
                # Enable RLS by default for new connections
                cursor.execute("SET row_security = on")
                logger.debug("Enabled Row-Level Security for connection")
        except Exception as e:
            logger.warning(f"Failed to enable RLS: {e}")


if async_engine:
    @event.listens_for(async_engine.sync_engine, "connect")
    def set_async_sqlite_pragma(dbapi_connection, connection_record):
        """Set up Row-Level Security context on async connection."""
        if "postgresql" in str(dbapi_connection):
            try:
                with dbapi_connection.cursor() as cursor:
                    cursor.execute("SET row_security = on")
                    logger.debug("Enabled Row-Level Security for async connection")
            except Exception as e:
                logger.warning(f"Failed to enable RLS on async connection: {e}")


class DatabaseManager:
    """Database connection and session management."""

    def __init__(self):
        self._async_engine = async_engine
        self._sync_engine = sync_engine

    async def connect(self) -> None:
        """Initialize database connections."""
        try:
            # Test async connection if available
            if self._async_engine:
                async with self._async_engine.begin() as conn:
                    await conn.execute(text("SELECT 1"))
                logger.info("Database async connection established")
            
            # Test sync connection
            with self._sync_engine.begin() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("Database sync connection established")
            
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    async def disconnect(self) -> None:
        """Close database connections."""
        try:
            if self._async_engine:
                await self._async_engine.dispose()
            self._sync_engine.dispose()
            logger.info("Database connections closed")
        except Exception as e:
            logger.error(f"Error closing database connections: {e}")

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get async database session."""
        if not AsyncSessionLocal:
            raise RuntimeError("Async session not available - asyncpg not installed")
        async with AsyncSessionLocal() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    def get_sync_session(self):
        """Get sync database session."""
        return SessionLocal()


# Global database manager instance
_db_manager = DatabaseManager()


def get_database() -> DatabaseManager:
    """Get the database manager instance."""
    return _db_manager


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency to get database session for FastAPI."""
    if not AsyncSessionLocal:
        raise RuntimeError("Async session not available - asyncpg not installed")
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def set_tenant_context(session: AsyncSession, tenant_id: str) -> None:
    """Set tenant context for Row-Level Security."""
    try:
        await session.execute(
            text("SELECT set_config('app.current_tenant_id', :tenant_id, true)"),
            {"tenant_id": tenant_id}
        )
        logger.debug(f"Set tenant context to: {tenant_id}")
    except Exception as e:
        logger.error(f"Failed to set tenant context: {e}")
        raise


def set_sync_tenant_context(session, tenant_id: str) -> None:
    """Set tenant context for Row-Level Security (sync version)."""
    try:
        session.execute(
            text("SELECT set_config('app.current_tenant_id', :tenant_id, true)"),
            {"tenant_id": tenant_id}
        )
        logger.debug(f"Set sync tenant context to: {tenant_id}")
    except Exception as e:
        logger.error(f"Failed to set sync tenant context: {e}")
        raise