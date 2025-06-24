"""Enhanced HTTP fetcher with optimized connection pooling."""

import asyncio
import ssl
import time
from typing import Dict, Optional, Tuple, Union
from urllib.parse import urlparse

import aiohttp
import structlog
from aiohttp import ClientError, ClientSession, ClientTimeout, TCPConnector

from ..config.settings import settings

logger = structlog.get_logger()


class HighPerformanceHTTPFetcher:
    """High-performance HTTP fetcher with optimized connection pooling."""

    def __init__(
        self,
        max_connections: Optional[int] = None,
        max_connections_per_host: Optional[int] = None,
        enable_dns_cache: bool = True,
        enable_keepalive: bool = True,
    ) -> None:
        """Initialize high-performance HTTP fetcher."""
        self.logger = logger.bind(component="hp_http_fetcher")
        self.session: Optional[ClientSession] = None
        self.domain_last_request: Dict[str, float] = {}

        # Enhanced connection limits
        self.max_connections = max_connections or (
            settings.scraping.max_concurrent_requests * 3
        )
        self.max_connections_per_host = max_connections_per_host or min(
            50, self.max_connections // 2
        )
        self.enable_dns_cache = enable_dns_cache
        self.enable_keepalive = enable_keepalive

        # Performance settings
        self.timeout = ClientTimeout(
            total=settings.scraping.request_timeout,
            connect=10,
            sock_read=settings.scraping.request_timeout,
            sock_connect=10,
        )

        # SSL context for better performance
        self.ssl_context = self._create_ssl_context()

    def _create_ssl_context(self) -> ssl.SSLContext:
        """Create optimized SSL context."""
        context = ssl.create_default_context()
        context.check_hostname = (
            False  # Faster, less secure (consider for internal use)
        )
        context.verify_mode = (
            ssl.CERT_NONE
        )  # Faster, less secure (consider for internal use)

        # For production, use secure settings:
        # context.check_hostname = True
        # context.verify_mode = ssl.CERT_REQUIRED

        return context

    async def __aenter__(self) -> "HighPerformanceHTTPFetcher":
        """Async context manager entry."""
        await self.start_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close_session()

    async def start_session(self) -> None:
        """Start optimized HTTP session."""
        if self.session is None:
            # Create optimized TCP connector
            connector = TCPConnector(
                limit=self.max_connections,
                limit_per_host=self.max_connections_per_host,
                ttl_dns_cache=300 if self.enable_dns_cache else 0,
                use_dns_cache=self.enable_dns_cache,
                keepalive_timeout=30 if self.enable_keepalive else 0,
                enable_cleanup_closed=True,
                ssl=self.ssl_context,
                # Additional performance optimizations
                resolver=aiohttp.AsyncResolver() if self.enable_dns_cache else None,
                family=0,  # Allow both IPv4 and IPv6
                happy_eyeballs_delay=0.25,  # Fast dual-stack connections
                interleave=1,  # Interleave IPv4 and IPv6 addresses
            )

            # Optimized headers for better performance
            headers = {
                "User-Agent": settings.scraping.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate, br",  # Added Brotli support
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Cache-Control": "max-age=0",
            }

            self.session = ClientSession(
                connector=connector,
                timeout=self.timeout,
                headers=headers,
                # Additional session optimizations
                read_bufsize=2**16,  # 64KB read buffer
                auto_decompress=True,
                trust_env=True,
                cookie_jar=aiohttp.DummyCookieJar(),  # Disable cookies for better performance
            )

            self.logger.info(
                "High-performance HTTP session started",
                max_connections=self.max_connections,
                max_connections_per_host=self.max_connections_per_host,
                dns_cache=self.enable_dns_cache,
                keepalive=self.enable_keepalive,
            )

    async def close_session(self) -> None:
        """Close HTTP session and cleanup connections."""
        if self.session:
            await self.session.close()
            # Wait for connections to close gracefully
            await asyncio.sleep(0.1)
            self.session = None
            self.logger.debug("HTTP session closed")

    async def fetch(self, url: str) -> Tuple[int, str, Dict[str, str]]:
        """
        Fetch content from URL with optimized performance.

        Args:
            url: URL to fetch

        Returns:
            Tuple of (status_code, content, headers)
        """
        if not self.session:
            await self.start_session()

        domain = self._extract_domain(url)
        await self._rate_limit(domain)

        start_time = time.time()

        try:
            self.logger.debug("Fetching URL", url=url, domain=domain)

            # Use session.get with optimized parameters
            async with self.session.get(
                url, allow_redirects=True, max_redirects=5, compress=True
            ) as response:
                # Read content efficiently
                content = await response.text(encoding="utf-8", errors="ignore")
                headers = dict(response.headers)

                response_time = time.time() - start_time

                # Update domain tracking
                self.domain_last_request[domain] = time.time()

                self.logger.info(
                    "URL fetched",
                    url=url,
                    status=response.status,
                    response_time=response_time,
                    content_length=len(content),
                    domain=domain,
                )

                return (response.status, content, headers)

        except asyncio.TimeoutError:
            self.logger.warning("Request timeout", url=url, domain=domain)
            return (408, "", {})

        except ClientError as e:
            self.logger.warning("Client error", url=url, domain=domain, error=str(e))
            return (500, "", {})

        except Exception as e:
            self.logger.error("Unexpected error", url=url, domain=domain, error=str(e))
            return (500, "", {})

    async def fetch_batch(
        self, urls: list[str]
    ) -> list[Tuple[str, int, str, Dict[str, str]]]:
        """
        Fetch multiple URLs concurrently with optimized batching.

        Args:
            urls: List of URLs to fetch

        Returns:
            List of tuples (url, status_code, content, headers)
        """
        if not self.session:
            await self.start_session()

        # Create semaphore for batch concurrency control
        semaphore = asyncio.Semaphore(min(len(urls), self.max_connections_per_host))

        async def fetch_single(url: str) -> Tuple[str, int, str, Dict[str, str]]:
            async with semaphore:
                status_code, content, headers = await self.fetch(url)
                return (url, status_code, content, headers)

        # Execute all requests concurrently
        tasks = [fetch_single(url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out exceptions and return successful results
        successful_results = []
        for result in results:
            if isinstance(result, tuple) and len(result) == 4:
                successful_results.append(result)
            else:
                self.logger.warning("Batch fetch error", error=str(result))

        return successful_results

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL for rate limiting."""
        try:
            parsed = urlparse(url)
            return parsed.netloc.lower()
        except Exception:
            return "unknown"

    async def _rate_limit(self, domain: str) -> None:
        """Apply intelligent rate limiting per domain."""
        if domain == "unknown":
            return

        # Get the last request time for this domain
        last_request = self.domain_last_request.get(domain, 0)
        time_since_last = time.time() - last_request

        # Calculate dynamic delay based on domain and recent activity
        base_delay = settings.scraping.rate_limit_delay

        # Reduce delay for different domains to allow parallel processing
        if time_since_last < base_delay:
            sleep_time = base_delay - time_since_last

            # Add small jitter to prevent thundering herd
            import random

            jitter = random.uniform(0.01, 0.1)
            sleep_time += jitter

            self.logger.debug(
                "Rate limiting",
                domain=domain,
                sleep_time=sleep_time,
                time_since_last=time_since_last,
            )

            await asyncio.sleep(sleep_time)

    def get_connection_stats(self) -> Dict[str, Union[int, float]]:
        """Get connection pool statistics."""
        if not self.session or not self.session.connector:
            return {}

        connector = self.session.connector

        return {
            "total_connections": len(connector._conns),
            "available_connections": sum(
                len(conns) for conns in connector._conns.values()
            ),
            "max_connections": self.max_connections,
            "max_connections_per_host": self.max_connections_per_host,
            "domains_tracked": len(self.domain_last_request),
        }


# For backward compatibility, create an enhanced version of the original fetcher
class EnhancedHTTPFetcher(HighPerformanceHTTPFetcher):
    """Enhanced version of the original HTTPFetcher with better defaults."""

    def __init__(self) -> None:
        """Initialize with enhanced defaults that match the original interface."""
        super().__init__(
            max_connections=settings.scraping.max_concurrent_requests * 2,
            max_connections_per_host=20,
            enable_dns_cache=True,
            enable_keepalive=True,
        )
