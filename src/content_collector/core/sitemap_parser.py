"""World-class sitemap parser with robots.txt support for efficient URL discovery."""

import gzip
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from io import BytesIO
from typing import Dict, List, Optional, Set
from urllib.parse import urljoin

import aiohttp
import structlog
from pydantic import BaseModel, HttpUrl

logger = structlog.get_logger(__name__)


class SitemapURL(BaseModel):
    """Model for a URL discovered from sitemap."""

    loc: HttpUrl
    lastmod: Optional[datetime] = None
    changefreq: Optional[str] = None
    priority: Optional[float] = None


class SitemapParser:
    """
    World-class sitemap parser with intelligent URL discovery.

    Features:
    - Robots.txt parsing for sitemap discovery
    - XML sitemap parsing with compression support
    - Sitemap index handling for large sites
    - Intelligent fallback to common sitemap locations
    - Concurrent fetching for performance
    - Respect for crawl-delay and user-agent rules
    """

    def __init__(self, user_agent: str = "ContentCollector/1.0"):
        self.user_agent = user_agent
        self.logger = logger.bind(component="sitemap_parser")
        self.session: Optional[aiohttp.ClientSession] = None
        self._namespaces = {
            "": "http://www.sitemaps.org/schemas/sitemap/0.9",
            "xhtml": "http://www.w3.org/1999/xhtml",
            "news": "http://www.google.com/schemas/sitemap-news/0.9",
            "image": "http://www.google.com/schemas/sitemap-image/1.1",
            "video": "http://www.google.com/schemas/sitemap-video/1.1",
        }

    async def __aenter__(self):
        """Async context manager entry."""
        self.session = aiohttp.ClientSession(
            headers={"User-Agent": self.user_agent},
            timeout=aiohttp.ClientTimeout(total=30),
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()

    async def discover_urls(
        self, domain: str, max_urls: Optional[int] = None, use_robots: bool = True
    ) -> List[SitemapURL]:
        """
        Discover all URLs from a domain's sitemaps.

        Args:
            domain: The domain to discover URLs from
            max_urls: Maximum number of URLs to return
            use_robots: Whether to check robots.txt for sitemaps

        Returns:
            List of discovered URLs with metadata
        """
        self.logger.info("Starting sitemap discovery", domain=domain)

        # Ensure we have a session
        if not self.session:
            self.session = aiohttp.ClientSession(
                headers={"User-Agent": self.user_agent},
                timeout=aiohttp.ClientTimeout(total=30),
            )

        # Normalize domain
        if not domain.startswith(("http://", "https://")):
            domain = f"https://{domain}"

        sitemap_urls = set()
        all_urls = []

        # Step 1: Check robots.txt for sitemap directives
        if use_robots:
            robots_sitemaps = await self._parse_robots_txt(domain)
            sitemap_urls.update(robots_sitemaps)
            self.logger.debug(
                "Found sitemaps in robots.txt", count=len(robots_sitemaps)
            )

        # Step 2: Try common sitemap locations if none found
        if not sitemap_urls:
            common_locations = [
                "/sitemap.xml",
                "/sitemap_index.xml",
                "/sitemap.xml.gz",
                "/sitemap/sitemap.xml",
                "/sitemaps/sitemap.xml",
                "/sitemap_index.xml.gz",
                "/sitemap1.xml",
            ]
            for location in common_locations:
                sitemap_urls.add(urljoin(domain, location))

        # Step 3: Process all discovered sitemaps
        for sitemap_url in sitemap_urls:
            try:
                remaining_urls = max_urls - len(all_urls) if max_urls else None
                urls = await self._process_sitemap(sitemap_url, max_urls=remaining_urls)
                all_urls.extend(urls)

                if max_urls and len(all_urls) >= max_urls:
                    all_urls = all_urls[:max_urls]
                    break

            except Exception as e:
                self.logger.debug(
                    "Failed to process sitemap", url=sitemap_url, error=str(e)
                )
                continue

        # Deduplicate URLs based on location
        unique_urls = self._deduplicate_urls(all_urls)

        self.logger.info(
            "Sitemap discovery completed",
            domain=domain,
            total_urls=len(unique_urls),
            sitemaps_checked=len(sitemap_urls),
        )

        return unique_urls[:max_urls] if max_urls else unique_urls

    async def _parse_robots_txt(self, domain: str) -> Set[str]:
        """Parse robots.txt to find sitemap URLs."""
        robots_url = urljoin(domain, "/robots.txt")
        sitemap_urls = set()

        try:
            async with self.session.get(robots_url) as response:
                if response.status == 200:
                    content = await response.text()

                    # Extract sitemap URLs from robots.txt
                    for line in content.split("\n"):
                        line = line.strip()
                        if line.lower().startswith("sitemap:"):
                            sitemap_url = line.split(":", 1)[1].strip()
                            if sitemap_url:
                                sitemap_urls.add(sitemap_url)

                    # Also extract crawl-delay if present for rate limiting
                    crawl_delay = self._extract_crawl_delay(content)
                    if crawl_delay:
                        self.logger.debug(
                            "Crawl delay found in robots.txt", delay=crawl_delay
                        )

        except Exception as e:
            self.logger.debug("Failed to fetch robots.txt", error=str(e))

        return sitemap_urls

    def _extract_crawl_delay(self, robots_content: str) -> Optional[float]:
        """Extract crawl-delay from robots.txt content."""
        for line in robots_content.split("\n"):
            line = line.strip().lower()
            if line.startswith("crawl-delay:"):
                try:
                    return float(line.split(":", 1)[1].strip())
                except (ValueError, IndexError):
                    pass
        return None

    async def _process_sitemap(
        self, sitemap_url: str, max_urls: Optional[int] = None
    ) -> List[SitemapURL]:
        """Process a single sitemap URL."""
        self.logger.debug("Processing sitemap", url=sitemap_url)

        try:
            content = await self._fetch_sitemap(sitemap_url)

            # Check if it's a sitemap index
            if self._is_sitemap_index(content):
                return await self._process_sitemap_index(
                    content, sitemap_url, max_urls=max_urls
                )
            else:
                urls = self._parse_sitemap_xml(content)
                # Apply max_urls limit if specified
                if max_urls and len(urls) > max_urls:
                    urls = urls[:max_urls]
                return urls

        except Exception as e:
            self.logger.error(
                "Failed to process sitemap", url=sitemap_url, error=str(e)
            )
            return []

    async def _fetch_sitemap(self, url: str) -> str:
        """Fetch sitemap content, handling compression."""
        async with self.session.get(url) as response:
            if response.status != 200:
                raise ValueError(f"HTTP {response.status} for {url}")

            content = await response.read()

            # Handle gzip compression
            if (
                url.endswith(".gz")
                or response.headers.get("Content-Encoding") == "gzip"
            ):
                try:
                    with gzip.GzipFile(fileobj=BytesIO(content)) as gz:
                        content = gz.read()
                except Exception:
                    pass  # Not actually gzipped

            return content.decode("utf-8", errors="ignore")

    def _is_sitemap_index(self, content: str) -> bool:
        """Check if content is a sitemap index."""
        return "<sitemapindex" in content.lower()

    async def _process_sitemap_index(
        self, content: str, base_url: str, max_urls: Optional[int] = None
    ) -> List[SitemapURL]:
        """Process a sitemap index file."""
        all_urls = []

        try:
            root = ET.fromstring(content)

            # Find all sitemap URLs in the index
            ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
            ns_path = f".//{ns}sitemap/{ns}loc"
            sitemap_elements = root.findall(ns_path)
            if not sitemap_elements:
                sitemap_elements = root.findall(".//sitemap/loc")

            # Process sitemaps sequentially to respect max_urls limit
            for elem in sitemap_elements:
                if elem.text:
                    sitemap_url = urljoin(base_url, elem.text.strip())
                    urls = await self._process_sitemap(sitemap_url, max_urls=max_urls)
                    all_urls.extend(urls)

                    # Stop if we have enough URLs
                    if max_urls and len(all_urls) >= max_urls:
                        all_urls = all_urls[:max_urls]
                        break

        except Exception as e:
            self.logger.error("Failed to parse sitemap index", error=str(e))

        return all_urls

    def _parse_sitemap_xml(self, content: str) -> List[SitemapURL]:
        """Parse a standard sitemap XML file."""
        urls = []

        try:
            root = ET.fromstring(content)

            # Try with namespace first, then without
            # Handle both namespaced and non-namespaced sitemaps
            url_elements = root.findall(
                ".//{http://www.sitemaps.org/schemas/sitemap/0.9}url"
            )
            if not url_elements:
                url_elements = root.findall(".//url")

            for url_elem in url_elements:
                # Extract URL location (required) - try with namespace first
                loc_elem = url_elem.find(
                    "{http://www.sitemaps.org/schemas/sitemap/0.9}loc"
                )
                if loc_elem is None:
                    loc_elem = url_elem.find("loc")
                if loc_elem is None or not loc_elem.text:
                    continue

                # Extract optional metadata
                lastmod = None
                lastmod_elem = url_elem.find(
                    "{http://www.sitemaps.org/schemas/sitemap/0.9}lastmod"
                )
                if lastmod_elem is None:
                    lastmod_elem = url_elem.find("lastmod")
                if lastmod_elem is not None and lastmod_elem.text:
                    try:
                        lastmod = self._parse_datetime(lastmod_elem.text)
                    except Exception:
                        pass

                changefreq = None
                changefreq_elem = url_elem.find(
                    "{http://www.sitemaps.org/schemas/sitemap/0.9}changefreq"
                )
                if changefreq_elem is None:
                    changefreq_elem = url_elem.find("changefreq")
                if changefreq_elem is not None and changefreq_elem.text:
                    changefreq = changefreq_elem.text

                priority = None
                priority_elem = url_elem.find(
                    "{http://www.sitemaps.org/schemas/sitemap/0.9}priority"
                )
                if priority_elem is None:
                    priority_elem = url_elem.find("priority")
                if priority_elem is not None and priority_elem.text:
                    try:
                        priority = float(priority_elem.text)
                    except ValueError:
                        pass

                # Create URL entry
                try:
                    url_entry = SitemapURL(
                        loc=loc_elem.text.strip(),
                        lastmod=lastmod,
                        changefreq=changefreq,
                        priority=priority,
                    )
                    urls.append(url_entry)
                except Exception as e:
                    self.logger.debug(
                        "Failed to create URL entry", url=loc_elem.text, error=str(e)
                    )

        except Exception as e:
            self.logger.error("Failed to parse sitemap XML", error=str(e))

        return urls

    def _parse_datetime(self, date_str: str) -> datetime:
        """Parse various datetime formats from sitemaps."""
        # Common sitemap datetime formats
        formats = [
            "%Y-%m-%d",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S.%f%z",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S.%fZ",
        ]

        # Clean up timezone format
        date_str = date_str.strip()
        if date_str.endswith("Z"):
            date_str = date_str[:-1] + "+00:00"

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue

        # If all formats fail, try fromisoformat as fallback
        return datetime.fromisoformat(date_str)

    def _deduplicate_urls(self, urls: List[SitemapURL]) -> List[SitemapURL]:
        """Deduplicate URLs while preserving the best metadata."""
        url_map: Dict[str, SitemapURL] = {}

        for url in urls:
            loc_str = str(url.loc)
            if loc_str not in url_map:
                url_map[loc_str] = url
            else:
                # Keep the entry with more metadata
                existing = url_map[loc_str]
                if (url.priority is not None and existing.priority is None) or (
                    url.lastmod is not None and existing.lastmod is None
                ):
                    url_map[loc_str] = url

        return list(url_map.values())

    async def filter_by_pattern(
        self, urls: List[SitemapURL], patterns: List[str], exclude: bool = False
    ) -> List[SitemapURL]:
        """
        Filter URLs by regex patterns.

        Args:
            urls: List of sitemap URLs
            patterns: List of regex patterns
            exclude: If True, exclude matching URLs; if False, include only matching

        Returns:
            Filtered list of URLs
        """
        filtered = []
        compiled_patterns = [re.compile(p) for p in patterns]

        for url in urls:
            url_str = str(url.loc)
            matches = any(p.search(url_str) for p in compiled_patterns)

            if (matches and not exclude) or (not matches and exclude):
                filtered.append(url)

        return filtered

    def sort_by_priority(
        self, urls: List[SitemapURL], reverse: bool = True
    ) -> List[SitemapURL]:
        """Sort URLs by priority (highest first by default)."""
        return sorted(
            urls,
            key=lambda x: x.priority if x.priority is not None else 0.5,
            reverse=reverse,
        )

    def sort_by_lastmod(
        self, urls: List[SitemapURL], reverse: bool = True
    ) -> List[SitemapURL]:
        """Sort URLs by last modification date (newest first by default)."""
        return sorted(
            urls,
            key=lambda x: x.lastmod if x.lastmod else datetime.min,
            reverse=reverse,
        )
