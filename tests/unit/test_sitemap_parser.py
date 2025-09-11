"""Unit tests for sitemap parser functionality."""

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from content_collector.core.sitemap_parser import SitemapParser, SitemapURL


@pytest.fixture
def sitemap_parser():
    """Create a sitemap parser instance."""
    return SitemapParser()


@pytest.fixture
def mock_robots_txt():
    """Sample robots.txt content with sitemap directives."""
    return """
User-agent: *
Disallow: /admin/
Crawl-delay: 1

Sitemap: https://example.com/sitemap.xml
Sitemap: https://example.com/sitemap-news.xml
"""


@pytest.fixture
def mock_sitemap_xml():
    """Sample sitemap XML content."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <url>
        <loc>https://example.com/page1</loc>
        <lastmod>2024-01-01T00:00:00Z</lastmod>
        <changefreq>daily</changefreq>
        <priority>0.8</priority>
    </url>
    <url>
        <loc>https://example.com/page2</loc>
        <lastmod>2024-01-02T00:00:00Z</lastmod>
        <changefreq>weekly</changefreq>
        <priority>0.6</priority>
    </url>
    <url>
        <loc>https://example.com/page3</loc>
        <changefreq>monthly</changefreq>
        <priority>0.4</priority>
    </url>
</urlset>
"""


@pytest.fixture
def mock_sitemap_index():
    """Sample sitemap index XML content."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <sitemap>
        <loc>https://example.com/sitemap-posts.xml</loc>
        <lastmod>2024-01-01T00:00:00Z</lastmod>
    </sitemap>
    <sitemap>
        <loc>https://example.com/sitemap-pages.xml</loc>
        <lastmod>2024-01-02T00:00:00Z</lastmod>
    </sitemap>
</sitemapindex>
"""


class TestSitemapParser:
    """Test cases for SitemapParser class."""

    @pytest.mark.asyncio
    async def test_parse_robots_txt(self, sitemap_parser, mock_robots_txt):
        """Test parsing robots.txt for sitemap URLs."""
        with patch.object(sitemap_parser, "session") as mock_session:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.text = AsyncMock(return_value=mock_robots_txt)

            mock_session.get = AsyncMock(return_value=mock_response)
            mock_session.get.return_value.__aenter__ = AsyncMock(
                return_value=mock_response
            )
            mock_session.get.return_value.__aexit__ = AsyncMock()

            sitemap_parser.session = mock_session

            sitemaps = await sitemap_parser._parse_robots_txt("https://example.com")

            assert len(sitemaps) == 2
            assert "https://example.com/sitemap.xml" in sitemaps
            assert "https://example.com/sitemap-news.xml" in sitemaps

    @pytest.mark.asyncio
    async def test_parse_sitemap_xml(self, sitemap_parser, mock_sitemap_xml):
        """Test parsing standard sitemap XML."""
        urls = sitemap_parser._parse_sitemap_xml(mock_sitemap_xml)

        assert len(urls) == 3

        # Check first URL details
        assert str(urls[0].loc) == "https://example.com/page1"
        assert urls[0].lastmod.year == 2024
        assert urls[0].changefreq == "daily"
        assert urls[0].priority == 0.8

        # Check second URL
        assert str(urls[1].loc) == "https://example.com/page2"
        assert urls[1].changefreq == "weekly"
        assert urls[1].priority == 0.6

        # Check third URL (no lastmod)
        assert str(urls[2].loc) == "https://example.com/page3"
        assert urls[2].lastmod is None
        assert urls[2].changefreq == "monthly"
        assert urls[2].priority == 0.4

    def test_is_sitemap_index(
        self, sitemap_parser, mock_sitemap_xml, mock_sitemap_index
    ):
        """Test detection of sitemap index files."""
        assert not sitemap_parser._is_sitemap_index(mock_sitemap_xml)
        assert sitemap_parser._is_sitemap_index(mock_sitemap_index)

    @pytest.mark.asyncio
    async def test_process_sitemap_index(
        self, sitemap_parser, mock_sitemap_index, mock_sitemap_xml
    ):
        """Test processing sitemap index files."""
        with patch.object(sitemap_parser, "_process_sitemap") as mock_process:
            mock_process.return_value = sitemap_parser._parse_sitemap_xml(
                mock_sitemap_xml
            )

            urls = await sitemap_parser._process_sitemap_index(
                mock_sitemap_index, "https://example.com"
            )

            # Should have processed both sitemaps in the index
            assert mock_process.call_count == 2

            # Should have 6 total URLs (3 from each sitemap)
            assert len(urls) == 6

    def test_deduplicate_urls(self, sitemap_parser):
        """Test URL deduplication."""
        urls = [
            SitemapURL(loc="https://example.com/page1", priority=0.5),
            SitemapURL(loc="https://example.com/page2", priority=0.8),
            SitemapURL(
                loc="https://example.com/page1", priority=0.9
            ),  # Duplicate with higher priority
            SitemapURL(loc="https://example.com/page3"),
        ]

        deduped = sitemap_parser._deduplicate_urls(urls)

        assert len(deduped) == 3

        # Should keep the duplicate with better metadata (higher priority)
        page1_url = next(
            u for u in deduped if str(u.loc) == "https://example.com/page1"
        )
        assert page1_url.priority == 0.9

    @pytest.mark.asyncio
    async def test_filter_by_pattern(self, sitemap_parser):
        """Test URL filtering by regex patterns."""
        urls = [
            SitemapURL(loc="https://example.com/blog/post1"),
            SitemapURL(loc="https://example.com/blog/post2"),
            SitemapURL(loc="https://example.com/products/item1"),
            SitemapURL(loc="https://example.com/about"),
        ]

        # Include only blog URLs
        filtered = await sitemap_parser.filter_by_pattern(
            urls, [r"/blog/"], exclude=False
        )
        assert len(filtered) == 2
        assert all("/blog/" in str(u.loc) for u in filtered)

        # Exclude blog URLs
        filtered = await sitemap_parser.filter_by_pattern(
            urls, [r"/blog/"], exclude=True
        )
        assert len(filtered) == 2
        assert all("/blog/" not in str(u.loc) for u in filtered)

    def test_sort_by_priority(self, sitemap_parser):
        """Test sorting URLs by priority."""
        urls = [
            SitemapURL(loc="https://example.com/page1", priority=0.5),
            SitemapURL(loc="https://example.com/page2", priority=0.8),
            SitemapURL(loc="https://example.com/page3", priority=0.3),
            SitemapURL(loc="https://example.com/page4"),  # No priority
        ]

        sorted_urls = sitemap_parser.sort_by_priority(urls)

        # Should be sorted by priority (highest first)
        assert sorted_urls[0].priority == 0.8
        assert sorted_urls[1].priority == 0.5
        assert (
            sorted_urls[2].priority == 0.5 or sorted_urls[2].priority is None
        )  # Default 0.5
        assert sorted_urls[3].priority == 0.3

    def test_sort_by_lastmod(self, sitemap_parser):
        """Test sorting URLs by last modification date."""
        urls = [
            SitemapURL(loc="https://example.com/page1", lastmod=datetime(2024, 1, 1)),
            SitemapURL(loc="https://example.com/page2", lastmod=datetime(2024, 1, 3)),
            SitemapURL(loc="https://example.com/page3", lastmod=datetime(2024, 1, 2)),
            SitemapURL(loc="https://example.com/page4"),  # No lastmod
        ]

        sorted_urls = sitemap_parser.sort_by_lastmod(urls)

        # Should be sorted by date (newest first)
        assert sorted_urls[0].lastmod == datetime(2024, 1, 3)
        assert sorted_urls[1].lastmod == datetime(2024, 1, 2)
        assert sorted_urls[2].lastmod == datetime(2024, 1, 1)
        assert sorted_urls[3].lastmod is None

    def test_parse_datetime(self, sitemap_parser):
        """Test parsing various datetime formats."""
        # Test different formats
        assert sitemap_parser._parse_datetime("2024-01-01") == datetime(2024, 1, 1)
        assert sitemap_parser._parse_datetime("2024-01-01T12:00:00Z") == datetime(
            2024, 1, 1, 12, 0, 0
        )
        assert sitemap_parser._parse_datetime("2024-01-01T12:00:00+00:00") == datetime(
            2024, 1, 1, 12, 0, 0
        )

        # Test with microseconds
        dt = sitemap_parser._parse_datetime("2024-01-01T12:00:00.123456Z")
        assert dt.microsecond == 123456

    @pytest.mark.asyncio
    async def test_discover_urls_with_robots(
        self, sitemap_parser, mock_robots_txt, mock_sitemap_xml
    ):
        """Test full URL discovery with robots.txt checking."""
        with patch.object(sitemap_parser, "_parse_robots_txt") as mock_parse_robots:
            mock_parse_robots.return_value = {"https://example.com/sitemap.xml"}

            with patch.object(sitemap_parser, "_fetch_sitemap") as mock_fetch:
                mock_fetch.return_value = mock_sitemap_xml

                with patch.object(sitemap_parser, "session", create=True):
                    urls = await sitemap_parser.discover_urls(
                        "https://example.com", use_robots=True
                    )

                    assert len(urls) == 3
                    assert mock_parse_robots.called

    @pytest.mark.asyncio
    async def test_discover_urls_fallback(self, sitemap_parser, mock_sitemap_xml):
        """Test URL discovery with fallback to common locations."""
        with patch.object(sitemap_parser, "_parse_robots_txt") as mock_parse_robots:
            mock_parse_robots.return_value = set()  # No sitemaps in robots.txt

            with patch.object(sitemap_parser, "_fetch_sitemap") as mock_fetch:
                # First few attempts fail, then succeed on common location
                mock_fetch.side_effect = [
                    Exception("Not found"),
                    Exception("Not found"),
                    mock_sitemap_xml,
                ]

                with patch.object(sitemap_parser, "session", create=True):
                    urls = await sitemap_parser.discover_urls(
                        "https://example.com", use_robots=False
                    )

                    # Should still find URLs from fallback locations
                    assert len(urls) > 0

    @pytest.mark.asyncio
    async def test_max_urls_limit(self, sitemap_parser, mock_sitemap_xml):
        """Test that max_urls parameter limits returned URLs."""
        with patch.object(sitemap_parser, "_parse_robots_txt") as mock_parse_robots:
            mock_parse_robots.return_value = {"https://example.com/sitemap.xml"}

            with patch.object(sitemap_parser, "_fetch_sitemap") as mock_fetch:
                mock_fetch.return_value = mock_sitemap_xml

                with patch.object(sitemap_parser, "session", create=True):
                    urls = await sitemap_parser.discover_urls(
                        "https://example.com", max_urls=2, use_robots=True
                    )

                    assert len(urls) == 2

    @pytest.mark.asyncio
    async def test_gzip_handling(self, sitemap_parser):
        """Test handling of gzipped sitemap files."""
        import gzip

        # Create gzipped content
        xml_content = b"<?xml version='1.0'?><urlset></urlset>"
        gzipped_content = gzip.compress(xml_content)

        with patch.object(sitemap_parser, "session") as mock_session:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.read = AsyncMock(return_value=gzipped_content)
            mock_response.headers = {"Content-Encoding": "gzip"}

            mock_session.get = AsyncMock(return_value=mock_response)
            mock_session.get.return_value.__aenter__ = AsyncMock(
                return_value=mock_response
            )
            mock_session.get.return_value.__aexit__ = AsyncMock()

            sitemap_parser.session = mock_session

            content = await sitemap_parser._fetch_sitemap(
                "https://example.com/sitemap.xml.gz"
            )

            assert "urlset" in content

    def test_extract_crawl_delay(self, sitemap_parser, mock_robots_txt):
        """Test extraction of crawl-delay from robots.txt."""
        delay = sitemap_parser._extract_crawl_delay(mock_robots_txt)
        assert delay == 1.0

        # Test with no crawl-delay
        no_delay_robots = "User-agent: *\nDisallow: /admin/"
        delay = sitemap_parser._extract_crawl_delay(no_delay_robots)
        assert delay is None
