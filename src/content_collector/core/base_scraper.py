"""Base scraper class with common functionality for all scraper implementations."""

from typing import Any, Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse

import structlog

from content_collector.base import BaseAsyncComponent
from content_collector.core.content_parser import ContentParser
from content_collector.storage.database import db_manager
from content_collector.storage.scraping_run_manager import ScrapingRunManager
from content_collector.utils.validators import URLValidator

logger = structlog.get_logger(__name__)


class BaseScraper(BaseAsyncComponent):
    """Base class for all scraper implementations with common functionality."""

    def __init__(
        self,
        max_depth: int = 1,
        allow_cross_domain: bool = False,
        respect_robots: bool = True,
        component_name: str = "base_scraper",
    ):
        """Initialize base scraper.

        Args:
            max_depth: Maximum crawl depth
            allow_cross_domain: Whether to allow cross-domain crawling
            respect_robots: Whether to respect robots.txt
            component_name: Component name for logging
        """
        super().__init__(component_name)

        self.max_depth = max_depth
        self.allow_cross_domain = allow_cross_domain
        self.respect_robots = respect_robots

        # Components
        self.url_validator = URLValidator()
        self.content_parser = ContentParser()
        self.run_manager = ScrapingRunManager()

        # State tracking
        self.run_id: Optional[str] = None
        self.scraped_urls: Set[str] = set()
        self.url_to_page_id: Dict[str, str] = {}

        # Statistics
        self.stats = {"total_urls": 0, "successful": 0, "failed": 0, "skipped": 0}

    async def _initialize(self) -> None:
        """Initialize the scraper and its components."""
        await db_manager.initialize()
        await self.content_parser.initialize()
        logger.info(
            "Base scraper initialized",
            max_depth=self.max_depth,
            allow_cross_domain=self.allow_cross_domain,
        )

    async def _close(self) -> None:
        """Clean up resources."""
        await self.content_parser.cleanup()
        logger.info("Base scraper cleaned up")

    async def _create_scraping_run(self, input_file: str) -> str:
        """Create a new scraping run record.

        Args:
            input_file: Input file name

        Returns:
            Run ID
        """
        async with db_manager.session() as session:
            self.run_id = await self.run_manager.create_scraping_run(
                session, input_file, self.max_depth
            )
        return self.run_id

    async def _update_total_urls_count(self, total: int) -> None:
        """Update total URLs count for the run.

        Args:
            total: Total number of URLs
        """
        async with db_manager.session() as session:
            await self.run_manager.update_total_urls_count(session, self.run_id, total)

    async def _mark_run_completed(self) -> None:
        """Mark the scraping run as completed."""
        async with db_manager.session() as session:
            await self.run_manager.mark_run_completed(session, self.run_id)

    async def _mark_run_failed(self, error: str) -> None:
        """Mark the scraping run as failed.

        Args:
            error: Error message
        """
        async with db_manager.session() as session:
            await self.run_manager.mark_run_failed(session, self.run_id, error)

    async def _store_page_result(
        self,
        url: str,
        parsed_content: Optional[Dict[str, Any]],
        status_code: Optional[int] = None,
        error: Optional[str] = None,
        parent_id: Optional[str] = None,
        depth: int = 0,
        referer_url: Optional[str] = None,
    ) -> str:
        """Store page scraping result.

        Args:
            url: Page URL
            parsed_content: Parsed content
            status_code: HTTP status code
            error: Error message if failed
            parent_id: Parent page ID
            depth: Crawl depth
            referer_url: Referring URL

        Returns:
            Page ID
        """
        async with db_manager.session() as session:
            page_id = await self.run_manager.store_page_result(
                session,
                self.run_id,
                url,
                parsed_content or {},
                status_code,
                error,
                parent_id,
                depth,
                referer_url,
            )

        # Update statistics
        if error:
            self.stats["failed"] += 1
        else:
            self.stats["successful"] += 1

        # Track URL to page ID mapping
        self.url_to_page_id[url] = page_id

        return page_id

    async def _check_url_already_scraped(self, url: str) -> bool:
        """Check if URL has already been scraped in this run.

        Args:
            url: URL to check

        Returns:
            True if already scraped
        """
        if url in self.scraped_urls:
            return True

        async with db_manager.session() as session:
            return await self.run_manager.check_url_already_scraped(
                session, self.run_id, url
            )

    def _should_scrape_url(self, url: str, base_domain: str, depth: int) -> bool:
        """Check if a URL should be scraped.

        Args:
            url: URL to check
            base_domain: Base domain for cross-domain check
            depth: Current crawl depth

        Returns:
            True if URL should be scraped
        """
        # Check if already scraped
        if url in self.scraped_urls:
            logger.debug("URL already scraped", url=url)
            return False

        # Check depth limit
        if depth > self.max_depth:
            logger.debug(
                "URL exceeds max depth", url=url, depth=depth, max_depth=self.max_depth
            )
            return False

        # Check if valid URL
        if not self.url_validator.is_valid_url(url):
            logger.debug("Invalid URL", url=url)
            return False

        # Check cross-domain restriction
        if not self.allow_cross_domain:
            url_domain = urlparse(url).netloc
            if url_domain != base_domain:
                logger.debug(
                    "Cross-domain URL skipped",
                    url=url,
                    domain=url_domain,
                    base_domain=base_domain,
                )
                return False

        return True

    def _extract_links_for_crawling(
        self,
        parsed_content: Dict[str, Any],
        base_url: str,
        base_domain: str,
        current_depth: int,
    ) -> List[str]:
        """Extract links from parsed content for crawling.

        Args:
            parsed_content: Parsed content containing links
            base_url: Base URL for resolving relative links
            base_domain: Base domain for cross-domain check
            current_depth: Current crawl depth

        Returns:
            List of URLs to crawl
        """
        if current_depth >= self.max_depth:
            return []

        links_to_crawl = []

        for link in parsed_content.get("links", []):
            # Resolve relative URLs
            absolute_url = urljoin(base_url, link)

            # Normalize URL
            normalized_url = self.url_validator.normalize_url(absolute_url)

            # Check if should scrape
            if self._should_scrape_url(normalized_url, base_domain, current_depth + 1):
                links_to_crawl.append(normalized_url)

        return links_to_crawl

    async def _parse_content_if_successful(
        self, content: str, url: str, status_code: int
    ) -> Optional[Dict[str, Any]]:
        """Parse content if fetch was successful.

        Args:
            content: Raw content
            url: Page URL
            status_code: HTTP status code

        Returns:
            Parsed content or None
        """
        if status_code >= 200 and status_code < 300 and content:
            try:
                parsed = await self.content_parser.parse(content, url)
                return parsed
            except Exception as e:
                logger.error("Failed to parse content", url=url, error=str(e))
                return None
        return None

    def get_statistics(self) -> Dict[str, Any]:
        """Get scraping statistics.

        Returns:
            Dictionary with statistics
        """
        return {
            "run_id": self.run_id,
            "total_urls": self.stats["total_urls"],
            "successful": self.stats["successful"],
            "failed": self.stats["failed"],
            "skipped": self.stats["skipped"],
            "success_rate": (
                self.stats["successful"] / self.stats["total_urls"] * 100
                if self.stats["total_urls"] > 0
                else 0
            ),
        }
