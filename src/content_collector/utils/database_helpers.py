"""Database session management utilities."""

from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Callable, Optional

import structlog

from ..storage.database import db_manager
from ..storage.models import Page, ScrapingRun

logger = structlog.get_logger(__name__)


class DatabaseSessionManager:
    """Utility class for managing database sessions with consistent error handling."""

    @staticmethod
    @asynccontextmanager
    async def session_with_error_handling(
        operation_name: str = "database_operation",
    ) -> AsyncGenerator[Any, None]:
        """
        Provide database session with standardized error handling.

        Args:
            operation_name: Name of the operation for logging

        Yields:
            Database session
        """
        try:
            async with db_manager.session() as session:
                yield session
        except Exception as e:
            logger.error(
                "Database operation failed", operation=operation_name, error=str(e)
            )
            raise

    @staticmethod
    async def update_scraping_run(
        run_id: str,
        update_func: Callable[[ScrapingRun], None],
        operation_name: str = "update_scraping_run",
    ) -> bool:
        """
        Update scraping run with consistent error handling.

        Args:
            run_id: ID of the scraping run to update
            update_func: Function that updates the scraping run object
            operation_name: Name of the operation for logging

        Returns:
            True if successful, False otherwise
        """
        try:
            async with db_manager.session() as session:
                scraping_run = await session.get(ScrapingRun, run_id)
                if scraping_run:
                    update_func(scraping_run)
                    await session.commit()
                    logger.debug(
                        "Scraping run updated successfully",
                        run_id=run_id,
                        operation=operation_name,
                    )
                    return True
                else:
                    logger.warning(
                        "Scraping run not found",
                        run_id=run_id,
                        operation=operation_name,
                    )
                    return False
        except Exception as e:
            logger.error(
                "Failed to update scraping run",
                run_id=run_id,
                operation=operation_name,
                error=str(e),
            )
            return False

    @staticmethod
    async def get_page_by_url(url: str, run_id: Optional[str] = None) -> Optional[str]:
        """
        Get page ID by URL with optional run filtering.

        Args:
            url: URL to search for
            run_id: Optional run ID to filter by

        Returns:
            Page ID if found, None otherwise
        """
        try:
            async with db_manager.session() as session:
                from sqlalchemy import select

                query = select(Page.id).where(Page.url == url)
                if run_id:
                    query = query.where(Page.scraping_run_id == run_id)
                query = query.limit(1)

                result = await session.execute(query)
                page_id = result.scalar_one_or_none()

                logger.debug(
                    "Page lookup completed", url=url, run_id=run_id, found=bool(page_id)
                )

                return page_id
        except Exception as e:
            logger.error(
                "Failed to get page by URL", url=url, run_id=run_id, error=str(e)
            )
            return None

    @staticmethod
    async def create_page_record(page_data: dict) -> bool:
        """
        Create page record with standardized error handling.

        Args:
            page_data: Dictionary containing page data

        Returns:
            True if successful, False otherwise
        """
        try:
            async with db_manager.session() as session:
                page = Page(**page_data)
                session.add(page)
                await session.commit()

                logger.debug(
                    "Page record created successfully",
                    page_id=page_data.get("id"),
                    url=page_data.get("url"),
                )
                return True
        except Exception as e:
            logger.error(
                "Failed to create page record", page_data=page_data, error=str(e)
            )
            return False


db_session_manager = DatabaseSessionManager()
