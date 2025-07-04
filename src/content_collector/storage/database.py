"""Database management for content collector."""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from content_collector.config.settings import settings
from content_collector.storage.models import Base

logger = structlog.get_logger(__name__)


class DatabaseManager:
    """Async database manager for content collector."""

    def __init__(self):
        self.engine: Optional[AsyncEngine] = None
        self.session_factory: Optional[async_sessionmaker] = None

    async def initialize(self) -> None:
        """Initialize database connection."""
        try:
            self.engine = create_async_engine(
                settings.database.url,
                echo=settings.debug,
                pool_pre_ping=True,
                pool_recycle=3600,
            )

            self.session_factory = async_sessionmaker(
                self.engine, class_=AsyncSession, expire_on_commit=False
            )

            url_for_log = settings.database.url
            if "@" in url_for_log:
                url_for_log = url_for_log.split("@")[1]
            logger.info("Database connection initialized", url=url_for_log)

        except Exception as e:
            logger.error("Failed to initialize database", error=str(e))
            raise

    async def create_tables(self) -> None:
        """Create all database tables."""
        if not self.engine:
            raise RuntimeError("Database not initialized")

        try:
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables created successfully")
        except Exception as e:
            logger.error("Failed to create tables", error=str(e))
            raise

    async def drop_tables(self) -> None:
        """Drop all database tables."""
        if not self.engine:
            raise RuntimeError("Database not initialized")

        try:
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
            logger.info("Database tables dropped successfully")
        except Exception as e:
            logger.error("Failed to drop tables", error=str(e))
            raise

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get async database session."""
        if not self.session_factory:
            raise RuntimeError("Database not initialized")

        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def health_check(self) -> bool:
        """Check database connectivity."""
        if not self.engine:
            return False

        try:
            async with self.engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.error("Database health check failed", error=str(e))
            return False

    async def close(self) -> None:
        """Close database connections."""
        if self.engine:
            await self.engine.dispose()
            logger.info("Database connections closed")


db_manager = DatabaseManager()


class Database:
    """Compatibility wrapper for tests - wraps DatabaseManager with simplified interface."""

    def __init__(self):
        self.manager = db_manager

    def connect(self):
        """Connect to database - synchronous wrapper."""
        asyncio.run(self.manager.initialize())

    def disconnect(self):
        """Disconnect from database - synchronous wrapper."""
        asyncio.run(self.manager.close())

    async def aconnect(self):
        """Async connect to database."""
        await self.manager.initialize()

    async def adisconnect(self):
        """Async disconnect from database."""
        await self.manager.close()
