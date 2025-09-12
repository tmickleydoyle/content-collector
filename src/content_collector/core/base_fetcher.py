"""Base HTTP fetcher with common functionality for all fetcher implementations."""

import asyncio
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse

import aiohttp
import structlog

logger = structlog.get_logger(__name__)


class BaseHTTPFetcher:
    """Base class for HTTP fetchers with common functionality."""

    def __init__(
        self,
        timeout: int = 30,
        max_retries: int = 3,
        rate_limit_delay: float = 0.1,
        user_agent: Optional[str] = None,
    ):
        """Initialize base fetcher.

        Args:
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
            rate_limit_delay: Delay between requests to same domain
            user_agent: Custom user agent string
        """
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.max_retries = max_retries
        self.rate_limit_delay = rate_limit_delay
        self.user_agent = user_agent or "Mozilla/5.0 (compatible; ContentCollector/1.0)"

        # Domain tracking for rate limiting
        self.domain_last_access: Dict[str, float] = {}
        self.domain_locks: Dict[str, asyncio.Lock] = {}

        # Session management
        self.session: Optional[aiohttp.ClientSession] = None

    async def initialize(self) -> None:
        """Initialize the HTTP session."""
        if not self.session:
            connector = aiohttp.TCPConnector(
                limit=100, limit_per_host=10, ttl_dns_cache=300
            )

            headers = {"User-Agent": self.user_agent}

            self.session = aiohttp.ClientSession(
                connector=connector, timeout=self.timeout, headers=headers
            )

            logger.info("HTTP session initialized", user_agent=self.user_agent)

    async def close(self) -> None:
        """Close the HTTP session."""
        if self.session:
            await self.session.close()
            self.session = None
            logger.info("HTTP session closed")

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL.

        Args:
            url: URL to extract domain from

        Returns:
            Domain name
        """
        return urlparse(url).netloc

    async def _apply_rate_limit(self, domain: str) -> None:
        """Apply rate limiting for a domain.

        Args:
            domain: Domain to rate limit
        """
        if domain not in self.domain_locks:
            self.domain_locks[domain] = asyncio.Lock()

        async with self.domain_locks[domain]:
            if domain in self.domain_last_access:
                time_since_last = (
                    asyncio.get_event_loop().time() - self.domain_last_access[domain]
                )
                if time_since_last < self.rate_limit_delay:
                    delay = self.rate_limit_delay - time_since_last
                    logger.debug("Rate limiting", domain=domain, delay=delay)
                    await asyncio.sleep(delay)

            self.domain_last_access[domain] = asyncio.get_event_loop().time()

    async def fetch(
        self, url: str, method: str = "GET", **kwargs
    ) -> Tuple[Optional[str], Optional[int], Optional[str]]:
        """Fetch content from URL with retries and rate limiting.

        Args:
            url: URL to fetch
            method: HTTP method
            **kwargs: Additional arguments for the request

        Returns:
            Tuple of (content, status_code, error_message)
        """
        if not self.session:
            await self.initialize()

        domain = self._extract_domain(url)
        await self._apply_rate_limit(domain)

        last_error = None

        for attempt in range(self.max_retries):
            try:
                async with self.session.request(method, url, **kwargs) as response:
                    content = await response.text()

                    if response.status < 400:
                        logger.debug(
                            "Successfully fetched URL",
                            url=url,
                            status=response.status,
                            attempt=attempt + 1,
                        )
                        return content, response.status, None

                    # Server error - might be worth retrying
                    if response.status >= 500 and attempt < self.max_retries - 1:
                        last_error = f"Server error: {response.status}"
                        logger.warning(
                            "Server error, will retry",
                            url=url,
                            status=response.status,
                            attempt=attempt + 1,
                        )
                        await asyncio.sleep(2**attempt)  # Exponential backoff
                        continue

                    # Client error - no point retrying
                    return None, response.status, f"HTTP {response.status}"

            except asyncio.TimeoutError:
                last_error = "Request timeout"
                logger.warning(
                    "Request timeout",
                    url=url,
                    attempt=attempt + 1,
                    timeout=self.timeout.total,
                )

            except aiohttp.ClientError as e:
                last_error = str(e)
                logger.warning(
                    "Client error", url=url, error=str(e), attempt=attempt + 1
                )

            except Exception as e:
                last_error = f"Unexpected error: {str(e)}"
                logger.error(
                    "Unexpected error during fetch",
                    url=url,
                    error=str(e),
                    attempt=attempt + 1,
                )

            # Wait before retry with exponential backoff
            if attempt < self.max_retries - 1:
                await asyncio.sleep(2**attempt)

        return None, None, last_error

    async def fetch_batch(
        self, urls: list[str], max_concurrent: int = 10
    ) -> Dict[str, Tuple[Optional[str], Optional[int], Optional[str]]]:
        """Fetch multiple URLs concurrently.

        Args:
            urls: List of URLs to fetch
            max_concurrent: Maximum concurrent requests

        Returns:
            Dictionary mapping URLs to fetch results
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def fetch_with_semaphore(url: str):
            async with semaphore:
                return await self.fetch(url)

        results = await asyncio.gather(
            *[fetch_with_semaphore(url) for url in urls], return_exceptions=True
        )

        return {
            url: (
                result
                if not isinstance(result, Exception)
                else (None, None, str(result))
            )
            for url, result in zip(urls, results)
        }
