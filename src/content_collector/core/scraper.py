"""Enhanced scraping engine with maximum parallelization."""

import asyncio
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

import structlog

from ..config.settings import settings
from ..core.content_parser import ContentParser
from ..core.fetcher import HighPerformanceFetcher
from ..input.processor import InputProcessor, URLEntry
from ..storage.database import db_manager
from ..storage.file_storage import file_storage
from ..storage.models import Page, ScrapingRun
from ..utils.validators import URLValidator

logger = structlog.get_logger()


class ScrapingEngine:
    """High-performance scraping engine with maximum parallelization."""

    def __init__(
        self,
        max_workers: Optional[int] = None,
        max_pages: Optional[int] = None,
        max_depth: int = 1,
        max_connections: Optional[int] = None,
        max_connections_per_host: Optional[int] = None,
        show_stats: bool = False,
        debug_links: bool = False,
    ) -> None:
        """Initialize enhanced scraping engine."""
        self.logger = logger.bind(component="hp_scraping_engine")
        self.input_processor = InputProcessor()
        self.content_parser = ContentParser(debug_links=debug_links)
        self.url_validator = URLValidator()

        # Configuration parameters
        self.max_pages = max_pages
        self.max_depth = max_depth
        self.max_connections = max_connections
        self.max_connections_per_host = max_connections_per_host
        self.show_stats = show_stats

        # Concurrency controls
        self.max_workers = max_workers or (
            settings.scraping.max_concurrent_requests * 2
        )
        self.semaphore = asyncio.Semaphore(self.max_workers)

        # State tracking
        self._global_visited_urls: Set[str] = set()
        self._processing_urls: Set[str] = set()
        self._url_queue: asyncio.Queue = asyncio.Queue()
        self._results_queue: asyncio.Queue = asyncio.Queue()

        # Max pages limit for the entire run
        self._max_pages_limit: Optional[int] = max_pages
        self._total_urls_queued: int = 0

        # Performance metrics
        self._stats = {
            "urls_processed": 0,
            "urls_failed": 0,
            "total_processing_time": 0,
            "concurrent_workers": 0,
            "queue_size": 0,
        }
        self._run_start_time: Optional[float] = None
        self._run_end_time: Optional[float] = None

        # Multiple HTTP fetchers for better connection pooling
        self._fetcher_pool_size = min(5, max(1, self.max_workers // 10))
        self._fetcher_pool: List[HighPerformanceFetcher] = []
        self._fetcher_index = 0

    async def run(
        self,
        input_file: Path,
        max_pages: Optional[int] = None,
        max_depth: Optional[int] = None,
    ) -> str:
        """
        Run high-performance scraping workflow.

        Args:
            input_file: Path to input file containing CSV paths
            max_pages: Maximum number of pages to scrape
            max_depth: Maximum depth for recursive crawling

        Returns:
            Run ID for tracking progress
        """
        # Initialize database if not already initialized
        await db_manager.initialize()

        run_id = str(uuid.uuid4())

        # Use instance variables if parameters not provided
        effective_max_pages = max_pages if max_pages is not None else self.max_pages
        effective_max_depth = max_depth if max_depth is not None else self.max_depth

        # Set max pages limit for this run
        self._max_pages_limit = effective_max_pages
        self._total_urls_queued = 0

        self.logger.info(
            "Starting high-performance scraping run",
            run_id=run_id,
            input_file=str(input_file),
            max_pages=effective_max_pages,
            max_depth=effective_max_depth,
            max_workers=self.max_workers,
            fetcher_pool_size=self._fetcher_pool_size,
        )

        await self._create_scraping_run_record(
            run_id, str(input_file), effective_max_depth
        )

        try:
            # Initialize fetcher pool
            await self._initialize_fetcher_pool()

            # Prepare initial URLs
            url_entries = await self._prepare_url_entries(
                input_file, effective_max_pages
            )

            if not url_entries:
                self.logger.warning("No URLs found in input file")
                return run_id

            await self._update_total_urls_count(run_id, len(url_entries))

            # Start timing the actual scraping work
            self._run_start_time = time.time()

            # Start parallel processing
            await self._parallel_scrape_with_depth(
                url_entries, run_id, effective_max_depth
            )

            # End timing
            self._run_end_time = time.time()

            await self._mark_run_completed(run_id)

            self.logger.info(
                "High-performance scraping run completed",
                run_id=run_id,
                stats=self._stats,
            )

        except Exception as e:
            self.logger.error("Scraping run failed", run_id=run_id, error=str(e))
            await self._mark_run_failed(run_id, str(e))
            raise
        finally:
            await self._cleanup_fetcher_pool()

        return run_id

    async def _initialize_fetcher_pool(self) -> None:
        """Initialize pool of HTTP fetchers for better connection distribution."""
        self._fetcher_pool = []
        for i in range(self._fetcher_pool_size):
            fetcher = HighPerformanceFetcher()
            await fetcher.start_session()
            self._fetcher_pool.append(fetcher)

        self.logger.info(
            f"Initialized fetcher pool with {len(self._fetcher_pool)} fetchers"
        )

    async def _cleanup_fetcher_pool(self) -> None:
        """Clean up HTTP fetcher pool."""
        for fetcher in self._fetcher_pool:
            try:
                await fetcher.close_session()
            except Exception as e:
                self.logger.warning(f"Error closing fetcher session: {e}")
        self._fetcher_pool.clear()

    def _get_next_fetcher(self) -> HighPerformanceFetcher:
        """Get next fetcher from pool using round-robin."""
        fetcher = self._fetcher_pool[self._fetcher_index]
        self._fetcher_index = (self._fetcher_index + 1) % len(self._fetcher_pool)
        return fetcher

    async def _parallel_scrape_with_depth(
        self, initial_urls: List[URLEntry], run_id: str, max_depth: int
    ) -> None:
        """
        Parallel scraping with depth control using producer-consumer pattern.
        """
        # Initialize URL queue with initial URLs
        for url_entry in initial_urls:
            self._total_urls_queued += 1
            await self._url_queue.put(
                (url_entry, 0, None)
            )  # (url_entry, depth, parent_id)

        # Start worker tasks
        workers = []
        for i in range(self.max_workers):
            worker = asyncio.create_task(self._worker(run_id, max_depth, worker_id=i))
            workers.append(worker)

        # Start result processor
        result_processor = asyncio.create_task(self._result_processor(run_id))

        # Start stats reporter
        stats_reporter = asyncio.create_task(self._stats_reporter())

        try:
            # Wait for queue to be empty and all workers to finish
            await self._url_queue.join()

            # Cancel workers
            for worker in workers:
                worker.cancel()

            # Wait for remaining results to be processed
            await self._results_queue.join()

            # Cancel result processor and stats reporter
            result_processor.cancel()
            stats_reporter.cancel()

            # Wait for cancellation to complete
            await asyncio.gather(
                *workers, result_processor, stats_reporter, return_exceptions=True
            )

        except Exception as e:
            self.logger.error("Error in parallel scraping", error=str(e))
            raise

    async def _worker(self, run_id: str, max_depth: int, worker_id: int) -> None:
        """
        Worker task that processes URLs from the queue.
        """
        worker_logger = self.logger.bind(worker_id=worker_id)

        try:
            while True:
                try:
                    # Get URL from queue with timeout
                    url_entry, depth, parent_id = await asyncio.wait_for(
                        self._url_queue.get(), timeout=5.0
                    )

                    async with self.semaphore:
                        self._stats["concurrent_workers"] += 1

                        try:
                            await self._process_single_url(
                                url_entry,
                                run_id,
                                depth,
                                max_depth,
                                worker_logger,
                                parent_id,
                            )
                        finally:
                            self._stats["concurrent_workers"] -= 1
                            self._url_queue.task_done()

                except asyncio.TimeoutError:
                    # No more URLs in queue, worker can exit
                    break
                except Exception as e:
                    worker_logger.error("Worker error", error=str(e))
                    self._url_queue.task_done()

        except asyncio.CancelledError:
            worker_logger.debug("Worker cancelled")
            raise

    async def _process_single_url(
        self,
        url_entry: URLEntry,
        run_id: str,
        depth: int,
        max_depth: int,
        worker_logger: Any,
        parent_id: Optional[str] = None,
    ) -> None:
        """Process a single URL and add discovered children to queue."""
        url = str(url_entry.url)

        # Check if already processed
        normalized_url = self.url_validator.normalize_url(url)
        if normalized_url in self._global_visited_urls:
            return

        # Check if currently being processed
        if normalized_url in self._processing_urls:
            return

        # Mark as being processed AND visited immediately to prevent duplicates
        self._processing_urls.add(normalized_url)
        self._global_visited_urls.add(normalized_url)

        try:
            start_time = time.time()

            # Check loop prevention
            if self._should_skip_url_for_loop_prevention(url, None, depth):
                worker_logger.debug("Skipping URL due to loop prevention", url=url)
                # Remove from visited since we're not actually processing it
                self._global_visited_urls.discard(normalized_url)
                return

            # Get fetcher from pool
            fetcher = self._get_next_fetcher()

            # Scrape URL
            page_id = str(uuid.uuid4())

            worker_logger.debug("Processing URL", url=url, depth=depth, page_id=page_id)

            try:
                status_code, content, headers = await fetcher.fetch(url)

                parsed_data = await self._parse_content_if_successful(
                    status_code, content, url
                )

                # Store result
                await self._results_queue.put(
                    {
                        "type": "page_result",
                        "page_id": page_id,
                        "url": url,
                        "run_id": run_id,
                        "status_code": status_code,
                        "parsed_data": parsed_data,
                        "headers": headers,
                        "depth": depth,
                        "parent_id": parent_id,
                        "content": content if status_code == 200 else None,
                    }
                )

                # Extract child URLs if successful and within depth limit
                if (
                    status_code == 200
                    and isinstance(parsed_data, dict)
                    and depth < max_depth
                    and parsed_data.get("links")
                ):

                    child_urls = self._filter_child_urls(parsed_data["links"], url)

                    # Add child URLs to queue for processing (with max pages check)
                    for child_url in child_urls:
                        # Check if we've reached the max pages limit
                        if (
                            self._max_pages_limit
                            and self._total_urls_queued >= self._max_pages_limit
                        ):
                            worker_logger.debug(
                                "Max pages limit reached, not queueing more URLs",
                                max_pages=self._max_pages_limit,
                                total_queued=self._total_urls_queued,
                            )
                            break

                        child_entry = URLEntry(
                            url=child_url, priority=1, category="discovered"
                        )
                        self._total_urls_queued += 1
                        await self._url_queue.put((child_entry, depth + 1, page_id))

                    worker_logger.debug(
                        "Added child URLs to queue",
                        url=url,
                        child_count=len(child_urls),
                        current_depth=depth,
                    )

                processing_time = time.time() - start_time
                self._stats["total_processing_time"] += processing_time
                self._stats["urls_processed"] += 1

                worker_logger.info(
                    "URL processed successfully",
                    url=url,
                    status_code=status_code,
                    processing_time=processing_time,
                    depth=depth,
                )

            except Exception as e:
                # Store failed result
                await self._results_queue.put(
                    {
                        "type": "page_result",
                        "page_id": page_id,
                        "url": url,
                        "run_id": run_id,
                        "status_code": 500,
                        "parsed_data": {},
                        "headers": {},
                        "depth": depth,
                        "error": str(e),
                        "parent_id": parent_id,
                        "content": None,
                    }
                )

                self._stats["urls_failed"] += 1
                worker_logger.error("Failed to process URL", url=url, error=str(e))

        finally:
            # Remove from processing set
            self._processing_urls.discard(normalized_url)

    def _filter_child_urls(self, links: List[str], parent_url: str) -> List[str]:
        """Filter child URLs based on domain policy and validation."""
        filtered_urls = []

        for link in links:
            if not self.url_validator.is_valid_url(link):
                continue

            # Apply cross-domain filtering
            if not settings.scraping.allow_cross_domain:
                if not self.url_validator.is_same_domain(parent_url, link):
                    continue

            # Check if already visited or being processed
            normalized_link = self.url_validator.normalize_url(link)
            if (
                normalized_link not in self._global_visited_urls
                and normalized_link not in self._processing_urls
            ):
                filtered_urls.append(link)

        return filtered_urls

    async def _result_processor(self, _run_id: str) -> None:
        """Process results from the results queue."""
        try:
            while True:
                try:
                    result = await asyncio.wait_for(
                        self._results_queue.get(), timeout=10.0
                    )

                    if result["type"] == "page_result":
                        await self._store_page_result(
                            result["page_id"],
                            result["url"],
                            result["run_id"],
                            result["status_code"],
                            result["parsed_data"],
                            result["headers"],
                            referer_url=None,
                            depth=result["depth"],
                            parent_id=result.get("parent_id"),
                            error=result.get("error"),
                            content=result.get("content"),
                        )

                        # Save content if successful
                        if result["content"] and result["status_code"] == 200:
                            await file_storage.save_content(
                                content_id=result["page_id"],
                                content=result["content"],
                                parsed_data=result["parsed_data"],
                                url=result["url"],
                            )

                    self._results_queue.task_done()

                except asyncio.TimeoutError:
                    # No more results, can exit
                    break
                except Exception as e:
                    self.logger.error("Error processing result", error=str(e))
                    self._results_queue.task_done()

        except asyncio.CancelledError:
            self.logger.debug("Result processor cancelled")
            raise

    async def _stats_reporter(self) -> None:
        """Periodically report processing statistics."""
        try:
            while True:
                await asyncio.sleep(30)  # Report every 30 seconds

                self._stats["queue_size"] = self._url_queue.qsize()

                avg_processing_time = self._stats["total_processing_time"] / max(
                    1, self._stats["urls_processed"]
                )

                self.logger.info(
                    "Processing statistics",
                    urls_processed=self._stats["urls_processed"],
                    urls_failed=self._stats["urls_failed"],
                    concurrent_workers=self._stats["concurrent_workers"],
                    queue_size=self._stats["queue_size"],
                    avg_processing_time=f"{avg_processing_time:.2f}s",
                    visited_urls=len(self._global_visited_urls),
                )

        except asyncio.CancelledError:
            self.logger.debug("Stats reporter cancelled")
            raise

    def _should_skip_url_for_loop_prevention(
        self, url: str, _referer_url: Optional[str] = None, _depth: int = 0
    ) -> bool:
        """Check if URL should be skipped for loop prevention."""
        if not settings.scraping.enable_loop_prevention:
            return False

        # Note: Don't check _global_visited_urls here as it's already checked in _process_single_url
        # This function only checks for path-based loops

        # Path-based loop detection
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

    # Reuse existing helper methods from ScrapingEngine
    async def _prepare_url_entries(
        self, input_file: Path, max_pages: Optional[int]
    ) -> List[URLEntry]:
        """Prepare URL entries from input file."""
        url_entries = await self.input_processor.process_input_file(input_file)

        if max_pages and len(url_entries) > max_pages:
            url_entries = url_entries[:max_pages]

        return url_entries

    async def _parse_content_if_successful(
        self, status_code: int, content: Union[str, bytes], url: str
    ) -> Dict:
        """Parse content if request was successful."""
        if status_code != 200 or not content:
            return {}

        try:
            return await self.content_parser.parse(content, url)
        except Exception as e:
            self.logger.error("Content parsing failed", url=url, error=str(e))
            return {}

    async def _create_scraping_run_record(
        self, run_id: str, input_file: str, max_depth: int
    ) -> None:
        """Create a scraping run record in the database."""
        async with db_manager.session() as session:
            scraping_run = ScrapingRun(
                id=run_id,
                input_file=input_file,
                max_depth=max_depth,
                total_urls=0,
                status="running",
            )
            session.add(scraping_run)
            await session.commit()

    async def _update_total_urls_count(self, run_id: str, total_urls: int) -> None:
        """Update total URLs count in scraping run."""
        async with db_manager.session() as session:
            scraping_run = await session.get(ScrapingRun, run_id)
            if scraping_run:
                scraping_run.total_urls = total_urls
                await session.commit()

    async def _mark_run_completed(self, run_id: str) -> None:
        """Mark scraping run as completed."""
        async with db_manager.session() as session:
            scraping_run = await session.get(ScrapingRun, run_id)
            if scraping_run:
                scraping_run.status = "completed"
                await session.commit()

    async def _mark_run_failed(self, run_id: str, error_message: str) -> None:
        """Mark scraping run as failed."""
        async with db_manager.session() as session:
            scraping_run = await session.get(ScrapingRun, run_id)
            if scraping_run:
                scraping_run.status = "failed"
                scraping_run.error_message = error_message
                await session.commit()

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

        try:
            from urllib.parse import urlparse

            parsed_url = urlparse(url)
            domain = parsed_url.netloc.lower()
        except Exception:
            domain = "unknown"

        page = Page(
            id=page_id,
            url=url,
            scraping_run_id=run_id,
            parent_id=parent_id,
            domain=domain,
            status_code=status_code,
            depth=depth,
            referer_url=referer_url,
            content_hash=parsed_data.get("content_hash"),
            title=parsed_data.get("title"),
            meta_description=parsed_data.get("meta_description"),
            content_type=headers.get("content-type"),
            content_length=len(content) if content else 0,
            retry_count=0,
            last_error=error,
        )

        async with db_manager.session() as session:
            session.add(page)
            await session.commit()

    def get_final_stats(self) -> Dict[str, Any]:
        """Get final performance statistics."""
        total_processed = self._stats["urls_processed"] + self._stats["urls_failed"]
        success_rate = (
            (self._stats["urls_processed"] / total_processed * 100)
            if total_processed > 0
            else 0
        )

        # Calculate wall-clock time (actual time from start to finish)
        wall_clock_time = (
            self._run_end_time - self._run_start_time
            if self._run_start_time and self._run_end_time
            else 0
        )

        # Average processing time per URL (individual processing time)
        avg_processing_time = (
            self._stats["total_processing_time"] / self._stats["urls_processed"]
            if self._stats["urls_processed"] > 0
            else 0
        )

        # Throughput based on wall-clock time
        throughput = (
            self._stats["urls_processed"] / wall_clock_time
            if wall_clock_time > 0
            else 0
        )

        return {
            "urls_processed": self._stats["urls_processed"],
            "urls_failed": self._stats["urls_failed"],
            "success_rate": success_rate,
            "total_time": wall_clock_time,
            "avg_processing_time": avg_processing_time,
            "throughput": throughput,
        }
