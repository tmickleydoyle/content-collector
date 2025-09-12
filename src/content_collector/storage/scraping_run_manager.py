"""Centralized database operations for scraping runs and pages."""

import hashlib
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import uuid4

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from content_collector.storage.models import Page, ScrapingRun

logger = structlog.get_logger(__name__)


class ScrapingRunManager:
    """Manages all database operations for scraping runs and pages."""

    @staticmethod
    async def create_scraping_run(
        session: AsyncSession, input_file: str, max_depth: int = 1
    ) -> str:
        """Create a new scraping run record.

        Args:
            session: Database session
            input_file: Path to input CSV file
            max_depth: Maximum crawl depth

        Returns:
            Run ID for the created scraping run
        """
        run_id = str(uuid4())

        scraping_run = ScrapingRun(
            id=run_id,
            input_file=input_file,
            status="running",
            max_depth=max_depth,
            total_urls=0,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        session.add(scraping_run)
        await session.commit()

        logger.info("Created scraping run", run_id=run_id, input_file=input_file)
        return run_id

    @staticmethod
    async def update_total_urls_count(
        session: AsyncSession, run_id: str, total_urls: int
    ) -> None:
        """Update the total URLs count for a scraping run.

        Args:
            session: Database session
            run_id: Scraping run ID
            total_urls: Total number of URLs to process
        """
        stmt = (
            update(ScrapingRun)
            .where(ScrapingRun.id == run_id)
            .values(total_urls=total_urls, updated_at=datetime.utcnow())
        )
        await session.execute(stmt)
        await session.commit()

        logger.info("Updated total URLs count", run_id=run_id, total_urls=total_urls)

    @staticmethod
    async def mark_run_completed(session: AsyncSession, run_id: str) -> None:
        """Mark a scraping run as completed.

        Args:
            session: Database session
            run_id: Scraping run ID
        """
        stmt = (
            update(ScrapingRun)
            .where(ScrapingRun.id == run_id)
            .values(status="completed", updated_at=datetime.utcnow())
        )
        await session.execute(stmt)
        await session.commit()

        logger.info("Marked run as completed", run_id=run_id)

    @staticmethod
    async def mark_run_failed(
        session: AsyncSession, run_id: str, error_message: str
    ) -> None:
        """Mark a scraping run as failed.

        Args:
            session: Database session
            run_id: Scraping run ID
            error_message: Error message describing the failure
        """
        stmt = (
            update(ScrapingRun)
            .where(ScrapingRun.id == run_id)
            .values(
                status="failed",
                error_message=error_message,
                updated_at=datetime.utcnow(),
            )
        )
        await session.execute(stmt)
        await session.commit()

        logger.error("Marked run as failed", run_id=run_id, error=error_message)

    @staticmethod
    async def store_page_result(
        session: AsyncSession,
        run_id: str,
        url: str,
        parsed_content: Dict[str, Any],
        status_code: Optional[int] = None,
        error: Optional[str] = None,
        parent_id: Optional[str] = None,
        depth: int = 0,
        referer_url: Optional[str] = None,
    ) -> str:
        """Store page scraping result in database.

        Args:
            session: Database session
            run_id: Scraping run ID
            url: Page URL
            parsed_content: Parsed content dictionary
            status_code: HTTP status code
            error: Error message if failed
            parent_id: Parent page ID for crawled pages
            depth: Crawl depth
            referer_url: Referring URL

        Returns:
            Page ID for the stored page
        """
        # Generate content hash
        content_hash = None
        if parsed_content and parsed_content.get("body_text"):
            content_hash = hashlib.sha256(
                parsed_content["body_text"].encode("utf-8")
            ).hexdigest()

        # Extract domain from URL
        from urllib.parse import urlparse

        domain = urlparse(url).netloc

        page_id = str(uuid4())

        page = Page(
            id=page_id,
            url=url,
            scraping_run_id=run_id,
            parent_id=parent_id,
            domain=domain,
            status_code=status_code,
            depth=depth,
            referer_url=referer_url,
            content_hash=content_hash,
            title=parsed_content.get("title") if parsed_content else None,
            meta_description=(
                parsed_content.get("meta_description") if parsed_content else None
            ),
            content_type=parsed_content.get("content_type") if parsed_content else None,
            content_length=(
                len(parsed_content.get("body_text", "")) if parsed_content else 0
            ),
            last_error=error,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        session.add(page)
        await session.commit()

        if error:
            logger.warning("Stored failed page", url=url, error=error)
        else:
            logger.debug(
                "Stored successful page", url=url, content_length=page.content_length
            )

        return page_id

    @staticmethod
    async def check_url_already_scraped(
        session: AsyncSession, run_id: str, url: str
    ) -> bool:
        """Check if a URL has already been scraped in this run.

        Args:
            session: Database session
            run_id: Scraping run ID
            url: URL to check

        Returns:
            True if URL already scraped, False otherwise
        """
        stmt = (
            select(func.count())
            .select_from(Page)
            .where(Page.scraping_run_id == run_id, Page.url == url)
        )
        result = await session.execute(stmt)
        count = result.scalar()
        return count > 0

    @staticmethod
    async def get_run_statistics(session: AsyncSession, run_id: str) -> Dict[str, Any]:
        """Get statistics for a scraping run.

        Args:
            session: Database session
            run_id: Scraping run ID

        Returns:
            Dictionary with run statistics
        """
        # Get total pages
        total_stmt = (
            select(func.count()).select_from(Page).where(Page.scraping_run_id == run_id)
        )
        total_result = await session.execute(total_stmt)
        total_pages = total_result.scalar()

        # Get successful pages
        success_stmt = (
            select(func.count())
            .select_from(Page)
            .where(Page.scraping_run_id == run_id, Page.status_code.between(200, 299))
        )
        success_result = await session.execute(success_stmt)
        successful_pages = success_result.scalar()

        # Get failed pages
        failed_pages = total_pages - successful_pages

        # Get total content size
        content_stmt = select(func.sum(Page.content_length)).where(
            Page.scraping_run_id == run_id
        )
        content_result = await session.execute(content_stmt)
        total_content_size = content_result.scalar() or 0

        return {
            "total_pages": total_pages,
            "successful_pages": successful_pages,
            "failed_pages": failed_pages,
            "success_rate": (
                (successful_pages / total_pages * 100) if total_pages > 0 else 0
            ),
            "total_content_size": total_content_size,
        }
