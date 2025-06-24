"""
Unit tests for the ScrapingEngine class.

This module demonstrates proper testing practices including:
- Clear test structure and naming
- Use of fixtures for setup
- Mocking external dependencies
- Testing both success and failure scenarios
- Comprehensive coverage of business logic
"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from content_collector.core.scraper import ScrapingEngine
from content_collector.input.processor import URLEntry


class TestScrapingEngine:
    """Test suite for ScrapingEngine class."""

    @pytest.fixture
    def scraping_engine(self):
        """Create a ScrapingEngine instance for testing."""
        return ScrapingEngine()

    @pytest.fixture
    def mock_url_entry(self):
        """Create a mock URL entry for testing."""
        return URLEntry(url="https://example.com", priority=1, category="test")

    @pytest.fixture
    def sample_url_entries(self, mock_url_entry):
        """Create a list of sample URL entries."""
        return [mock_url_entry]

    @pytest.mark.asyncio
    async def test_create_scraping_run_record_success(self, scraping_engine):
        """Test successful creation of scraping run record."""
        run_id = "test-run-123"
        input_file = Path("test_input.txt")
        max_depth = 2

        with patch("content_collector.core.scraper.db_manager") as mock_db:
            mock_session = AsyncMock()
            mock_db.session.return_value.__aenter__.return_value = mock_session

            await scraping_engine._create_scraping_run_record(
                run_id, input_file, max_depth
            )

            mock_session.add.assert_called_once()
            mock_session.commit.assert_called_once()

            added_run = mock_session.add.call_args[0][0]
            assert added_run.id == run_id
            assert added_run.input_file == str(input_file)
            assert added_run.status == "running"

    @pytest.mark.asyncio
    async def test_prepare_url_entries_with_limit(self, scraping_engine):
        """Test URL entries preparation with max_pages limit."""
        input_file = Path("test_input.txt")
        max_pages = 2

        mock_entries = [
            URLEntry(url=f"https://example{i}.com", priority=1, category="test")
            for i in range(5)
        ]

        with patch.object(
            scraping_engine.input_processor,
            "process_input_file",
            return_value=mock_entries,
        ):
            result = await scraping_engine._prepare_url_entries(input_file, max_pages)

            assert len(result) == max_pages
            assert result == mock_entries[:max_pages]

    @pytest.mark.asyncio
    async def test_prepare_url_entries_no_urls_found(self, scraping_engine):
        """Test URL entries preparation when no URLs are found."""
        input_file = Path("empty_input.txt")

        with patch.object(
            scraping_engine.input_processor, "process_input_file", return_value=[]
        ):
            result = await scraping_engine._prepare_url_entries(input_file, None)

            assert result == []

    @pytest.mark.asyncio
    async def test_update_total_urls_count_success(self, scraping_engine):
        """Test successful update of total URLs count."""
        run_id = "test-run-123"
        total_urls = 10

        with patch("content_collector.core.scraper.db_manager") as mock_db:
            mock_session = AsyncMock()
            mock_run = MagicMock()
            mock_session.get.return_value = mock_run
            mock_db.session.return_value.__aenter__.return_value = mock_session

            await scraping_engine._update_total_urls_count(run_id, total_urls)

            assert mock_run.total_urls == total_urls
            mock_session.get.assert_called_once()
            mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_mark_run_completed_success(self, scraping_engine):
        """Test marking run as completed."""
        run_id = "test-run-123"

        with patch("content_collector.core.scraper.db_manager") as mock_db:
            mock_session = AsyncMock()
            mock_run = MagicMock()
            mock_session.get.return_value = mock_run
            mock_db.session.return_value.__aenter__.return_value = mock_session

            await scraping_engine._mark_run_completed(run_id)

            assert mock_run.status == "completed"
            mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_mark_run_failed_success(self, scraping_engine):
        """Test marking run as failed with error message."""
        run_id = "test-run-123"
        error_message = "Test error message"

        with patch("content_collector.core.scraper.db_manager") as mock_db:
            mock_session = AsyncMock()
            mock_run = MagicMock()
            mock_session.get.return_value = mock_run
            mock_db.session.return_value.__aenter__.return_value = mock_session

            await scraping_engine._mark_run_failed(run_id, error_message)

            assert mock_run.status == "failed"
            assert mock_run.error_message == error_message
            mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_parse_content_if_successful_with_content(self, scraping_engine):
        """Test content parsing when request is successful."""
        status_code = 200
        content = "<html><title>Test</title></html>"
        url = "https://example.com"
        expected_data = {"title": "Test", "content_length": 100}

        with patch.object(
            scraping_engine.content_parser, "parse_html", return_value=expected_data
        ) as mock_parse:
            result = await scraping_engine._parse_content_if_successful(
                status_code, content, url
            )

            assert result == expected_data
            mock_parse.assert_called_once_with(content, url)

    @pytest.mark.asyncio
    async def test_parse_content_if_successful_with_error(self, scraping_engine):
        """Test content parsing when request failed."""
        status_code = 404
        content = ""
        url = "https://example.com"

        result = await scraping_engine._parse_content_if_successful(
            status_code, content, url
        )

        assert result == {}

    @pytest.mark.asyncio
    async def test_store_failed_page_success(self, scraping_engine):
        """Test storing failed page attempt."""
        page_id = "page-123"
        url = "https://example.com"
        error = "Connection timeout"

        with patch("content_collector.core.scraper.db_manager") as mock_db:
            mock_session = AsyncMock()
            mock_db.session.return_value.__aenter__.return_value = mock_session

            with patch.object(
                scraping_engine.url_validator,
                "extract_domain",
                return_value="example.com",
            ):
                await scraping_engine._store_page_result(
                    page_id=page_id, url=url, run_id="test-run-id", error=error
                )

                mock_session.add.assert_called_once()
                mock_session.commit.assert_called_once()

                added_page = mock_session.add.call_args[0][0]
                assert added_page.id == page_id
                assert added_page.url == url
                assert added_page.status_code == 500
                assert added_page.last_error == error
                assert added_page.retry_count == 1

    @pytest.mark.asyncio
    async def test_scrape_urls_success(self, scraping_engine, sample_url_entries):
        """Test successful URL scraping workflow."""
        run_id = "test-run-123"

        with patch("content_collector.core.scraper.HTTPFetcher") as mock_fetcher_class:
            mock_fetcher = AsyncMock()
            mock_fetcher_class.return_value.__aenter__.return_value = mock_fetcher

            with patch("content_collector.core.scraper.db_manager") as mock_db:
                mock_session = AsyncMock()
                mock_db.session.return_value.__aenter__.return_value = mock_session

                with patch.object(
                    scraping_engine,
                    "_scrape_single_url_with_children",
                    return_value=None,
                ) as mock_scrape_single:
                    await scraping_engine._scrape_urls_recursive(
                        sample_url_entries, run_id, 1
                    )

                    assert mock_scrape_single.call_count == len(sample_url_entries)

    @pytest.mark.asyncio
    async def test_run_full_workflow_success(self, scraping_engine, sample_url_entries):
        """Test the complete run workflow."""
        input_file = Path("test_input.txt")
        max_pages = None
        max_depth = 1

        with (
            patch.object(scraping_engine, "_create_scraping_run_record") as mock_create,
            patch.object(
                scraping_engine, "_prepare_url_entries", return_value=sample_url_entries
            ) as mock_prepare,
            patch.object(scraping_engine, "_update_total_urls_count") as mock_update,
            patch.object(scraping_engine, "_scrape_urls_recursive") as mock_scrape,
            patch.object(scraping_engine, "_mark_run_completed") as mock_complete,
        ):

            run_id = await scraping_engine.run(input_file, max_pages, max_depth)

            mock_create.assert_called_once()
            mock_prepare.assert_called_once_with(input_file, max_pages)
            mock_update.assert_called_once_with(run_id, len(sample_url_entries))
            mock_scrape.assert_called_once_with(sample_url_entries, run_id, max_depth)
            mock_complete.assert_called_once_with(run_id)

            assert isinstance(run_id, str)
            assert len(run_id) > 0

    @pytest.mark.asyncio
    async def test_run_workflow_with_exception(self, scraping_engine):
        """Test run workflow when an exception occurs."""
        input_file = Path("test_input.txt")
        max_pages = None
        error_message = "Test error"

        with (
            patch.object(scraping_engine, "_create_scraping_run_record"),
            patch.object(
                scraping_engine,
                "_prepare_url_entries",
                side_effect=Exception(error_message),
            ),
            patch.object(scraping_engine, "_mark_run_failed") as mock_mark_failed,
        ):

            with pytest.raises(Exception, match=error_message):
                await scraping_engine.run(input_file, max_pages)

            mock_mark_failed.assert_called_once()
            call_args = mock_mark_failed.call_args[0]
            assert call_args[1] == error_message


class TestScrapingEngineIntegration:
    """Integration tests for ScrapingEngine with real components."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_scraping_engine_initialization(self):
        """Test that ScrapingEngine initializes with all dependencies."""
        engine = ScrapingEngine()

        assert engine.input_processor is not None
        assert engine.content_parser is not None
        assert engine.url_validator is not None
        assert engine.logger is not None

    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_end_to_end_scraping_with_real_urls(self, temp_dir):
        """End-to-end test with real URLs (requires network)."""
        pytest.skip("Network test - implement when network testing is enabled")
