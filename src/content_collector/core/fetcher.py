"""HTTP fetcher for web scraping."""

import asyncio
import time
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse

import aiohttp
import structlog
from aiohttp import ClientSession, ClientTimeout, ClientError

from ..config.settings import settings

logger = structlog.get_logger()


class HTTPFetcher:
    """Handles HTTP requests with rate limiting and error handling."""
    
    def __init__(self) -> None:
        """Initialize HTTP fetcher."""
        self.logger = logger.bind(component="http_fetcher")
        self.session: Optional[ClientSession] = None
        self.domain_last_request: Dict[str, float] = {}
        
        # Configure timeout
        self.timeout = ClientTimeout(
            total=settings.scraping.request_timeout,
            connect=10,
            sock_read=settings.scraping.request_timeout
        )
    
    async def __aenter__(self) -> "HTTPFetcher":
        """Async context manager entry."""
        await self.start_session()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close_session()
    
    async def start_session(self) -> None:
        """Start HTTP session."""
        if self.session is None:
            connector = aiohttp.TCPConnector(
                limit=settings.scraping.max_concurrent_requests,
                limit_per_host=10,
                keepalive_timeout=30,
                enable_cleanup_closed=True
            )
            
            self.session = ClientSession(
                connector=connector,
                timeout=self.timeout,
                headers={
                    'User-Agent': settings.scraping.user_agent,
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate',
                    'DNT': '1',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                }
            )
    
    async def close_session(self) -> None:
        """Close HTTP session."""
        if self.session:
            await self.session.close()
            self.session = None
    
    async def fetch(self, url: str) -> Tuple[int, str, Dict[str, str]]:
        """
        Fetch content from URL with rate limiting.
        
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
            self.logger.debug("Fetching URL", url=url)
            
            async with self.session.get(url) as response:
                content = await response.text()
                headers = dict(response.headers)
                
                response_time = time.time() - start_time
                
                self.logger.info(
                    "URL fetched",
                    url=url,
                    status=response.status,
                    response_time=response_time,
                    content_length=len(content)
                )
                
                return response.status, content, headers
                
        except asyncio.TimeoutError:
            self.logger.warning("Request timeout", url=url)
            return 408, "", {}
            
        except ClientError as e:
            self.logger.warning("Client error", url=url, error=str(e))
            return 500, "", {}
            
        except Exception as e:
            self.logger.error("Unexpected error", url=url, error=str(e))
            return 500, "", {}
        
        finally:
            # Update last request time for domain
            self.domain_last_request[domain] = time.time()
    
    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        try:
            parsed = urlparse(url)
            return parsed.netloc.lower()
        except Exception:
            return "unknown"
    
    async def _rate_limit(self, domain: str) -> None:
        """Apply rate limiting per domain."""
        if domain in self.domain_last_request:
            time_since_last = time.time() - self.domain_last_request[domain]
            if time_since_last < settings.scraping.rate_limit_delay:
                sleep_time = settings.scraping.rate_limit_delay - time_since_last
                self.logger.debug(
                    "Rate limiting", 
                    domain=domain, 
                    sleep_time=sleep_time
                )
                await asyncio.sleep(sleep_time)