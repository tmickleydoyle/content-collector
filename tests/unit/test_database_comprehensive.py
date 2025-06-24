"""Comprehensive tests for database functionality."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from content_collector.storage.database import DatabaseManager


class TestDatabaseManager:
    """Test DatabaseManager functionality."""

    @pytest.fixture
    def db_manager(self):
        """Create DatabaseManager instance for testing."""
        return DatabaseManager()

    def test_initialization(self, db_manager):
        """Test DatabaseManager initialization."""
        assert db_manager.engine is None
        assert db_manager.session_factory is None

    @pytest.mark.asyncio
    @patch("content_collector.storage.database.create_async_engine")
    @patch("content_collector.storage.database.async_sessionmaker")
    async def test_initialize_success(
        self, mock_sessionmaker, mock_create_engine, db_manager
    ):
        """Test successful database initialization."""
        mock_engine = AsyncMock()
        mock_create_engine.return_value = mock_engine

        mock_session_factory = AsyncMock()
        mock_sessionmaker.return_value = mock_session_factory

        await db_manager.initialize()

        assert db_manager.engine == mock_engine
        assert db_manager.session_factory == mock_session_factory
        mock_create_engine.assert_called_once()
        mock_sessionmaker.assert_called_once()

    @pytest.mark.asyncio
    @patch("content_collector.storage.database.create_async_engine")
    async def test_initialize_failure(self, mock_create_engine, db_manager):
        """Test database initialization failure."""
        mock_create_engine.side_effect = Exception("Connection failed")

        with pytest.raises(Exception, match="Connection failed"):
            await db_manager.initialize()

        assert db_manager.engine is None
        assert db_manager.session_factory is None

    @pytest.mark.asyncio
    async def test_close(self, db_manager):
        """Test database connection closure."""
        mock_engine = AsyncMock()
        db_manager.engine = mock_engine
        db_manager._initialized = True

        await db_manager.close()

        mock_engine.dispose.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_without_engine(self, db_manager):
        """Test closing when no engine exists."""
        await db_manager.close()
        assert db_manager.engine is None

    @pytest.mark.asyncio
    async def test_session_context_manager(self, db_manager):
        """Test session context manager."""
        mock_session = AsyncMock()

        @asynccontextmanager
        async def mock_session_factory():
            yield mock_session

        db_manager.session_factory = mock_session_factory

        async with db_manager.session() as session:
            assert session == mock_session

    @pytest.mark.asyncio
    async def test_session_without_initialization(self, db_manager):
        """Test session creation without initialization."""
        with pytest.raises(RuntimeError, match="Database not initialized"):
            async with db_manager.session():
                pass

    @pytest.mark.asyncio
    async def test_health_check_success(self, db_manager):
        """Test successful database health check."""
        mock_engine = AsyncMock()
        mock_conn = AsyncMock()

        @asynccontextmanager
        async def mock_begin():
            yield mock_conn

        mock_engine.begin = mock_begin
        db_manager.engine = mock_engine

        mock_conn.execute.return_value = AsyncMock()

        result = await db_manager.health_check()
        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self, db_manager):
        """Test database health check failure."""
        mock_engine = AsyncMock()

        @asynccontextmanager
        async def mock_begin():
            raise Exception("Database error")
            yield

        mock_engine.begin = mock_begin
        db_manager.engine = mock_engine

        result = await db_manager.health_check()
        assert result is False

    @pytest.mark.asyncio
    async def test_create_tables(self, db_manager):
        """Test table creation."""
        mock_engine = AsyncMock()
        mock_conn = AsyncMock()

        @asynccontextmanager
        async def mock_begin():
            yield mock_conn

        mock_engine.begin = mock_begin
        db_manager.engine = mock_engine

        with patch("content_collector.storage.models.Base") as mock_base:
            await db_manager.create_tables()
            mock_conn.run_sync.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_tables_without_engine(self, db_manager):
        """Test table creation without engine."""
        with pytest.raises(RuntimeError, match="Database not initialized"):
            await db_manager.create_tables()


class TestDatabaseUtilities:
    """Test database utility functions."""

    def test_database_url_parsing(self):
        """Test database URL parsing and validation."""
        from content_collector.config.settings import settings

        assert hasattr(settings, "database")
