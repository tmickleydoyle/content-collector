"""
Comprehensive tests for HTTPFetcher with proper async mocking.
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from content_collector.core.fetcher import HTTPFetcher


class MockAsyncContextManager:
    """Custom async context manager for mocking aiohttp responses."""

    def __init__(self, mock_response):
        self.mock_response = mock_response

    async def __aenter__(self):
        return self.mock_response

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return None


class TestFetcherTupleInterface:
    """Test fetcher tuple return interface."""

    def test_successful_tuple_format(self):
        """Test successful fetch result tuple format."""
        # Test tuple format: (status_code, content, headers)
        status_code, content, headers = (
            200,
            "<html>test</html>",
            {"content-type": "text/html"},
        )

        assert status_code == 200
        assert content == "<html>test</html>"
        assert headers == {"content-type": "text/html"}

    def test_failed_tuple_format(self):
        """Test failed fetch result tuple format."""
        # Test tuple format for failures: (status_code, content, headers)
        status_code, content, headers = (500, "", {})

        assert status_code == 500
        assert content == ""
        assert headers == {}


class TestHTTPFetcher:
    """Test HTTPFetcher functionality."""

    @pytest.fixture
    async def fetcher(self):
        """Create HTTPFetcher instance for testing."""
        fetcher = HTTPFetcher()
        yield fetcher
        if fetcher.session:
            if hasattr(fetcher.session, "close") and callable(fetcher.session.close):
                try:
                    await fetcher.close_session()
                except (TypeError, AttributeError):
                    fetcher.session = None
            else:
                fetcher.session = None

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test HTTPFetcher as async context manager."""
        async with HTTPFetcher() as fetcher:
            assert fetcher.session is not None
        assert fetcher.session is None

    @pytest.mark.asyncio
    async def test_start_session(self, fetcher):
        """Test session initialization."""
        assert fetcher.session is None
        await fetcher.start_session()
        assert fetcher.session is not None
        assert isinstance(fetcher.session, aiohttp.ClientSession)

    @pytest.mark.asyncio
    async def test_close_session(self, fetcher):
        """Test session cleanup."""
        await fetcher.start_session()
        assert fetcher.session is not None
        await fetcher.close_session()
        assert fetcher.session is None

    @pytest.mark.asyncio
    async def test_successful_fetch(self, fetcher):
        """Test successful HTTP fetch with proper mocking."""
        url = "https://example.com"
        expected_content = "<html><body>Test content</body></html>"

        await fetcher.start_session()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text.return_value = expected_content
        mock_response.headers = {"content-type": "text/html"}

        fetcher.session.get = MagicMock(
            return_value=MockAsyncContextManager(mock_response)
        )

        result = await fetcher.fetch(url)

        # Unpack tuple result: (status_code, content, headers)
        status_code, content, headers = result
        assert status_code == 200
        assert content == expected_content
        assert headers == {"content-type": "text/html"}

    @pytest.mark.asyncio
    async def test_fetch_with_error(self, fetcher):
        """Test fetch with HTTP error."""
        url = "https://example.com/404"

        await fetcher.start_session()

        mock_response = AsyncMock()
        mock_response.status = 404
        mock_response.text.return_value = "Not Found"
        mock_response.headers = {"content-type": "text/html"}

        fetcher.session.get = MagicMock(
            return_value=MockAsyncContextManager(mock_response)
        )

        result = await fetcher.fetch(url)

        # Unpack tuple result: (status_code, content, headers)
        status_code, content, headers = result
        assert status_code == 404
        assert content == "Not Found"
        assert headers == {"content-type": "text/html"}

    @pytest.mark.asyncio
    async def test_fetch_with_timeout(self, fetcher):
        """Test fetch with timeout exception."""
        url = "https://slow.example.com"

        await fetcher.start_session()

        fetcher.session.get = MagicMock(
            side_effect=asyncio.TimeoutError("Request timeout")
        )

        result = await fetcher.fetch(url)

        # Unpack tuple result: (status_code, content, headers)
        status_code, content, headers = result
        assert status_code == 408  # Timeout status
        assert content == ""
        assert headers == {}

    @pytest.mark.asyncio
    async def test_fetch_with_client_error(self, fetcher):
        """Test fetch with client error."""
        url = "https://bad.example.com"

        await fetcher.start_session()

        fetcher.session.get = MagicMock(
            side_effect=aiohttp.ClientError("Connection failed")
        )

        result = await fetcher.fetch(url)

        # Unpack tuple result: (status_code, content, headers)
        status_code, content, headers = result
        assert status_code == 500  # Client error status
        assert content == ""
        assert headers == {}

    @pytest.mark.asyncio
    async def test_fetch_without_session(self, fetcher):
        """Test fetch automatically starts session if not started."""
        url = "https://example.com"
        expected_content = "Test"

        assert fetcher.session is None

        with patch.object(fetcher, "start_session") as mock_start:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.text.return_value = expected_content
            mock_response.headers = {}

            def setup_mock_session():
                fetcher.session = MagicMock()
                fetcher.session.get = MagicMock(
                    return_value=MockAsyncContextManager(mock_response)
                )

            mock_start.side_effect = setup_mock_session

            result = await fetcher.fetch(url)

            mock_start.assert_called_once()
            # Unpack tuple result: (status_code, content, headers)
            status_code, content, headers = result
            assert status_code == 200
            assert content == expected_content

    def test_extract_domain(self, fetcher):
        """Test domain extraction from URLs."""
        assert fetcher._extract_domain("https://example.com/path") == "example.com"
        assert (
            fetcher._extract_domain("http://subdomain.example.com")
            == "subdomain.example.com"
        )
        assert fetcher._extract_domain("https://EXAMPLE.COM") == "example.com"
        assert fetcher._extract_domain("invalid-url") == "unknown"
        assert fetcher._extract_domain("") == "unknown"

    @pytest.mark.asyncio
    async def test_rate_limiting(self, fetcher):
        """Test rate limiting functionality."""
        domain = "example.com"

        with patch("asyncio.sleep") as mock_sleep:
            await fetcher._rate_limit(domain)
            mock_sleep.assert_not_called()

            fetcher.domain_last_request[domain] = time.time()

            await fetcher._rate_limit(domain)
            mock_sleep.assert_called_once()

            sleep_time = mock_sleep.call_args[0][0]
            assert 0 < sleep_time <= 1.0

    @pytest.mark.asyncio
    async def test_fetch_updates_domain_tracking(self, fetcher):
        """Test that fetch updates domain last request time."""
        url = "https://example.com"
        domain = "example.com"

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text.return_value = "test"
        mock_response.headers = {}

        mock_session = AsyncMock()
        mock_session.get.return_value.__aenter__.return_value = mock_response
        mock_session.get.return_value.__aexit__.return_value = None

        fetcher.session = mock_session

        assert domain not in fetcher.domain_last_request

        await fetcher.fetch(url)

        assert domain in fetcher.domain_last_request
        assert isinstance(fetcher.domain_last_request[domain], float)
