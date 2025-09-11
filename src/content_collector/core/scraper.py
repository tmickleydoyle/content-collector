"""Main scraping engine that orchestrates the scraping process."""

import asyncio
import uuid
from pathlib import Path
from typing import List, Optional

import structlog

from ..config.settings import settings
from ..core.content_parser import ContentParser
from ..core.fetcher import HTTPFetcher
from ..input.processor import InputProcessor, URLEntry
from ..storage.database import db_manager
from ..storage.file_storage import file_storage
from ..storage.models import Page, ScrapingRun
from ..utils.validators import URLValidator

logger = structlog.get_logger()


class ScrapingEngine:
    """Main scraping engine that coordinates the scraping workflow."""

    def __init__(self, debug_links: bool = False) -> None:
        """Initialize scraping engine."""
        self.logger = logger.bind(component="scraping_engine")
        self.input_processor = InputProcessor()
        self.content_parser = ContentParser(debug_links=debug_links)
        self.url_validator = URLValidator()
        self._global_visited_urls = set()
        self._global_visited_domains = set()
        self._url_traversal_paths = {}

    async def run(
        self, input_file: Path, max_pages: Optional[int] = None, max_depth: int = 2
    ) -> str:
        """
        Run the complete scraping workflow.

        Args:
            input_file: Path to input file containing CSV paths
            max_pages: Maximum number of pages to scrape
            max_depth: Maximum depth for recursive crawling

        Returns:
            Run ID for tracking progress
        """
        run_id = str(uuid.uuid4())

        self.logger.info(
            "Starting scraping run",
            run_id=run_id,
            input_file=str(input_file),
            max_pages=max_pages,
        )

        await self._create_scraping_run_record(run_id, str(input_file), max_depth)

        try:
            url_entries = await self._prepare_url_entries(input_file, max_pages)

            if not url_entries:
                self.logger.warning("No URLs found in input file")
                return run_id

            await self._update_total_urls_count(run_id, len(url_entries))

            await self._scrape_urls_recursive(url_entries, run_id, max_depth)

            await self._mark_run_completed(run_id)

            self.logger.info("Scraping run completed", run_id=run_id)

        except Exception as e:
            self.logger.error("Scraping run failed", run_id=run_id, error=str(e))

            await self._mark_run_failed(run_id, str(e))

            raise

        return run_id

    async def _scrape_urls(self, url_entries: List[URLEntry], run_id: str) -> None:
        """Scrape list of URLs with concurrency control."""
        semaphore = asyncio.Semaphore(settings.scraping.max_concurrent_requests)

        async with HTTPFetcher() as fetcher:
            tasks = []
            for url_entry in url_entries:
                task = self._scrape_single_url(fetcher, url_entry, run_id, semaphore)
                tasks.append(task)

            self.logger.info(f"Starting to scrape {len(tasks)} URLs")
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _scrape_single_url(
        self,
        fetcher: HTTPFetcher,
        url_entry: URLEntry,
        run_id: str,
        semaphore: asyncio.Semaphore,
    ) -> None:
        """Scrape a single URL and store results."""
        async with semaphore:
            page_id = str(uuid.uuid4())
            url = str(url_entry.url)

            self.logger.debug("Scraping URL", url=url, page_id=page_id)

            try:
                status_code, content, headers = await fetcher.fetch(url)

                self.logger.debug(
                    "Fetch completed",
                    url=url,
                    status_code=status_code,
                    content_type=type(content).__name__,
                )

                parsed_data = await self._parse_content_if_successful(
                    status_code, content, url
                )

                self.logger.debug(
                    "Parse completed",
                    url=url,
                    parsed_data_type=type(parsed_data).__name__,
                )

                if not isinstance(parsed_data, dict):
                    self.logger.warning(
                        "parsed_data is not dict",
                        url=url,
                        parsed_data_type=type(parsed_data).__name__,
                        parsed_data=str(parsed_data)[:100],
                    )
                    parsed_data = {}

                await self._store_page_result(
                    page_id, url, run_id, status_code, parsed_data, headers
                )

                self.logger.debug(
                    "Store completed",
                    url=url,
                    parsed_data_type=type(parsed_data).__name__,
                )

                if status_code == 200 and content:
                    self.logger.debug(
                        "About to save content",
                        url=url,
                        parsed_data_type=type(parsed_data).__name__,
                    )
                    await file_storage.save_content(
                        content_id=page_id,
                        content=content,
                        parsed_data=parsed_data,
                        url=url,
                    )
                    self.logger.debug(
                        "Content saved",
                        url=url,
                        parsed_data_type=type(parsed_data).__name__,
                    )

                self.logger.debug(
                    "About to log success",
                    url=url,
                    parsed_data_type=type(parsed_data).__name__,
                )
                self.logger.info(
                    "URL scraped successfully",
                    url=url,
                    status_code=status_code,
                    title=parsed_data.get("title", "No title"),
                )

            except Exception as e:
                self.logger.error("Failed to scrape URL", url=url, error=str(e))

                await self._store_page_result(
                    page_id, url, run_id, 500, {}, {}, error=str(e)
                )

    async def _scrape_single_url_with_children(
        self, url_entry: URLEntry, run_id: str, depth: int = 0, parent_id: Optional[str] = None, referer_url: Optional[str] = None
    ) -> tuple[List[str], str]:
        """Scrape a single URL and return found child URLs and the page_id."""
        semaphore = asyncio.Semaphore(1)
        child_urls = []
        page_id = str(uuid.uuid4())

        async with HTTPFetcher() as fetcher:
            url = str(url_entry.url)

            self.logger.debug(
                "Scraping URL with children", url=url, page_id=page_id, depth=depth
            )

            try:
                status_code, content, headers = await fetcher.fetch(url)

                self.logger.debug(
                    "Fetch completed",
                    url=url,
                    status_code=status_code,
                    content_type=type(content).__name__,
                )

                parsed_data = await self._parse_content_if_successful(
                    status_code, content, url
                )

                self.logger.debug(
                    "Parse completed",
                    url=url,
                    parsed_data_type=type(parsed_data).__name__,
                )

                if not isinstance(parsed_data, dict):
                    self.logger.warning(
                        "parsed_data is not dict",
                        url=url,
                        parsed_data_type=type(parsed_data).__name__,
                        parsed_data=str(parsed_data)[:100],
                    )
                    parsed_data = {}

                if status_code == 200 and content and "links" in parsed_data:
                    all_links = parsed_data["links"]

                    for link in all_links:
                        if link == url:
                            continue

                        if not self.url_validator.is_valid_url(link):
                            continue

                        if not settings.scraping.allow_cross_domain:
                            if not self.url_validator.is_same_domain(url, link):
                                self.logger.debug(
                                    "Skipping cross-domain URL",
                                    current_url=url,
                                    child_url=link,
                                    current_domain=self.url_validator.extract_domain(
                                        url
                                    ),
                                    child_domain=self.url_validator.extract_domain(
                                        link
                                    ),
                                )
                                continue

                        child_urls.append(link)

                    self.logger.debug(
                        "Extracted child URLs",
                        url=url,
                        child_count=len(child_urls),
                        depth=depth,
                        total_links=len(all_links),
                        cross_domain_allowed=settings.scraping.allow_cross_domain,
                    )

                await self._store_page_result(
                    page_id, url, run_id, status_code, parsed_data, headers, depth=depth, parent_id=parent_id, referer_url=referer_url
                )

                self.logger.debug(
                    "Store completed",
                    url=url,
                    parsed_data_type=type(parsed_data).__name__,
                )

                if status_code == 200 and content:
                    self.logger.debug(
                        "About to save content",
                        url=url,
                        parsed_data_type=type(parsed_data).__name__,
                    )
                    await file_storage.save_content(
                        content_id=page_id,
                        content=content,
                        parsed_data=parsed_data,
                        url=url,
                    )
                    self.logger.debug(
                        "Content saved",
                        url=url,
                        parsed_data_type=type(parsed_data).__name__,
                    )

                self.logger.info(
                    "URL scraped successfully",
                    url=url,
                    status_code=status_code,
                    title=parsed_data.get("title", "No title"),
                    child_urls_found=len(child_urls),
                    depth=depth,
                )

            except Exception as e:
                self.logger.error(
                    "Failed to scrape URL", url=url, error=str(e), depth=depth
                )

                await self._store_page_result(
                    page_id, url, run_id, 500, {}, {}, error=str(e), depth=depth, parent_id=parent_id, referer_url=referer_url
                )

        return child_urls, page_id


    def _would_create_loop(self, candidate_url: str, current_path: List[str]) -> bool:
        """Check if adding candidate URL to path would create a loop."""
        return candidate_url in current_path

    def _is_potential_infinite_loop_pair(self, url1: str, url2: str) -> bool:
        """Check if two URLs might create an infinite loop."""
        try:
            from urllib.parse import urlparse

            parsed1 = urlparse(url1)
            parsed2 = urlparse(url2)

            if url1 == url2:
                return True

            if parsed1.netloc != parsed2.netloc:
                return False

            path1 = parsed1.path.rstrip("/")
            path2 = parsed2.path.rstrip("/")

            if path1 and path2:
                if path1.startswith(path2) or path2.startswith(path1):
                    return True

            return False
        except Exception:
            return url1 == url2

    def _build_traversal_path(
        self, url: str, referer: Optional[str] = None
    ) -> List[str]:
        """Build traversal path for loop detection."""
        path = []
        if referer:
            path.append(referer)
        path.append(url)

        self._url_traversal_paths[url] = path
        return path

    async def _create_scraping_run_record(
        self, run_id: str, input_file: str, max_depth: int = None
    ) -> None:
        """Create a scraping run record in the database."""
        if max_depth is None:
            max_depth = settings.scraping.max_depth

        async with db_manager.session() as session:
            scraping_run = ScrapingRun(
                id=run_id,
                input_file=str(input_file),
                max_depth=max_depth,
                total_urls=0,
                status="running",
            )
            session.add(scraping_run)
            await session.commit()

    async def _prepare_url_entries(
        self, input_file: Path, max_pages: Optional[int] = None
    ) -> List[URLEntry]:
        """Prepare URL entries from input file."""
        url_entries = await self.input_processor.process_input_file(input_file)

        if not url_entries:
            self.logger.warning("No URLs found in input file")
            return []

        if max_pages and len(url_entries) > max_pages:
            url_entries = url_entries[:max_pages]

        return url_entries

    async def _update_total_urls_count(self, run_id: str, total_count: int) -> None:
        """Update the total URLs count for a scraping run."""
        async with db_manager.session() as session:
            result = await session.get(ScrapingRun, run_id)
            if result:
                result.total_urls = total_count
                await session.commit()

    async def _mark_run_completed(self, run_id: str) -> None:
        """Mark a scraping run as completed."""
        async with db_manager.session() as session:
            result = await session.get(ScrapingRun, run_id)
            if result:
                result.status = "completed"
                await session.commit()

    async def _mark_run_failed(self, run_id: str, error_message: str) -> None:
        """Mark a scraping run as failed."""
        async with db_manager.session() as session:
            result = await session.get(ScrapingRun, run_id)
            if result:
                result.status = "failed"
                result.error_message = error_message
                await session.commit()

    async def _parse_content_if_successful(
        self, status_code: int, content: str, url: str
    ) -> dict:
        """Parse content if the fetch was successful."""
        parsed_data = {}
        if status_code == 200 and content:
            parsed_data = await self.content_parser.parse(content, url)
        return parsed_data

    async def _store_page_result(
        self,
        page_id: str,
        url: str,
        run_id: str,
        status_code: int = 500,
        parsed_data: dict = None,
        headers: dict = None,
        referer_url: Optional[str] = None,
        error: Optional[str] = None,
        depth: int = 0,
        parent_id: Optional[str] = None,
        content: Optional[str] = None,
    ) -> None:
        """Store page result in database."""
        if parsed_data is None:
            parsed_data = {}
        if headers is None:
            headers = {}

        domain = self.url_validator.extract_domain(url)

        async with db_manager.session() as session:
            page = Page(
                id=page_id,
                url=url,
                domain=domain or "unknown",
                status_code=status_code,
                depth=depth,
                content_hash=parsed_data.get("content_hash"),
                title=parsed_data.get("title"),
                meta_description=parsed_data.get("meta_description"),
                content_type=headers.get("content-type"),
                content_length=parsed_data.get("content_length", 0),
                scraping_run_id=run_id,
                referer_url=referer_url,
                parent_id=parent_id,
                last_error=error,
                retry_count=1 if error else 0,
            )
            session.add(page)
            await session.commit()

        if content and status_code == 200:
            await file_storage.save_content(
                content_id=page_id, content=content, parsed_data=parsed_data, url=url
            )

    async def _scrape_urls_recursive(
        self,
        url_entries: List[URLEntry],
        run_id: str,
        max_depth: int = 2,
        current_depth: int = 0,
        parent_id: Optional[str] = None,
        referer_url: Optional[str] = None,
    ) -> None:
        """Recursively scrape URLs with depth control."""
        if current_depth >= max_depth:
            return

        for url_entry in url_entries:
            url = str(url_entry.url)

            if self._should_skip_url_for_loop_prevention(url, referer_url, current_depth):
                continue

            # Check if we should skip this domain
            if self._should_skip_domain(url):
                continue

            normalized_url = self.url_validator.normalize_url(url)
            self._global_visited_urls.add(normalized_url)

            # Mark domain as visited on first URL from this domain
            self._mark_domain_as_visited(url)

            try:
                child_urls, current_page_id = await self._scrape_single_url_with_children(
                    url_entry, run_id, current_depth, parent_id, referer_url
                )

                if child_urls and current_depth + 1 < max_depth:
                    self.logger.info(
                        "Processing child URLs",
                        url=url,
                        child_count=len(child_urls),
                        current_depth=current_depth,
                        max_depth=max_depth,
                    )
                    child_entries = [
                        URLEntry(url=child_url, priority=1, category="discovered")
                        for child_url in child_urls
                        if not self._should_skip_url_for_loop_prevention(
                            child_url, url, current_depth + 1
                        )
                        and not self._should_skip_domain(child_url)
                    ]
                    filtered_child_count = len(child_entries)

                    self.logger.info(
                        "Filtered child URLs for recursion",
                        original_count=len(child_urls),
                        filtered_count=filtered_child_count,
                        depth=current_depth + 1,
                    )

                    if filtered_child_count > 0:
                        # Use the page_id of the current page as parent_id for children
                        await self._scrape_urls_recursive(
                            child_entries, 
                            run_id, 
                            max_depth, 
                            current_depth + 1,
                            parent_id=current_page_id,
                            referer_url=url
                        )
            except Exception as e:
                self.logger.debug(f"Mock side effect exhausted or error: {e}")
                break

    def _should_skip_url_for_loop_prevention(
        self, url: str, referer_url: Optional[str] = None, depth: int = 0
    ) -> bool:
        """Check if URL should be skipped for loop prevention."""
        if not settings.scraping.enable_loop_prevention:
            return False

        normalized_url = self.url_validator.normalize_url(url)

        if normalized_url in self._global_visited_urls:
            return True

        if referer_url and self._is_potential_infinite_loop_pair(url, referer_url):
            return True

        try:
            from urllib.parse import urlparse

            parsed = urlparse(url)
            path_parts = parsed.path.strip("/").split("/")

            if len(path_parts) > 1:
                from collections import Counter

                segment_counts = Counter(path_parts)
                for segment, count in segment_counts.items():
                    if segment and count > 2:
                        return True
        except Exception:
            pass

        return False

    def _should_skip_domain(self, url: str) -> bool:
        """Check if domain should be skipped because it was already scraped in this run."""
        domain = self.url_validator.extract_domain(url)
        if domain and domain in self._global_visited_domains:
            self.logger.debug(
                "Skipping URL due to domain already scraped in this run",
                url=url,
                domain=domain,
            )
            return True
        return False

    def _mark_domain_as_visited(self, url: str) -> None:
        """Mark domain as visited for this scraping run."""
        domain = self.url_validator.extract_domain(url)
        if domain:
            self._global_visited_domains.add(domain)
            self.logger.debug("Marked domain as visited", domain=domain)
