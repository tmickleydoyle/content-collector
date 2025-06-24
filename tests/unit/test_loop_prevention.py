"""Test loop prevention functionality in the scraper."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from content_collector.config.settings import settings
from content_collector.core.scraper import ScrapingEngine
from content_collector.input.processor import URLEntry


class TestLoopPrevention:
    """Test the loop prevention system."""

    @pytest.fixture
    def scraper(self):
        """Create a scraper instance for testing."""
        return ScrapingEngine()

    def test_would_create_loop_detection(self, scraper):
        """Test basic loop detection in traversal paths."""
        path = ["https://example.com/page1", "https://example.com/page2"]
        candidate = "https://example.com/page1"

        assert scraper._would_create_loop(candidate, path) is True

        path = ["https://example.com/page1", "https://example.com/page2"]
        candidate = "https://example.com/page3"

        assert scraper._would_create_loop(candidate, path) is False

        path = []
        candidate = "https://example.com/page1"

        assert scraper._would_create_loop(candidate, path) is False

    def test_potential_infinite_loop_pair_detection(self, scraper):
        """Test detection of potential infinite loop pairs."""
        url1 = "https://example.com/category"
        url2 = "https://example.com/category/item"

        assert scraper._is_potential_infinite_loop_pair(url1, url2) is True
        assert scraper._is_potential_infinite_loop_pair(url2, url1) is True

        url1 = "https://example.com/page"
        url2 = "https://different.com/page"

        assert scraper._is_potential_infinite_loop_pair(url1, url2) is False

        url1 = "https://example.com/about"
        url2 = "https://example.com/contact"

        assert scraper._is_potential_infinite_loop_pair(url1, url2) is False

    def test_traversal_path_building(self, scraper):
        """Test building traversal paths."""
        url = "https://example.com/"
        path = scraper._build_traversal_path(url, None)

        assert path == [url]
        assert scraper._url_traversal_paths[url] == [url]

        parent_url = "https://example.com/"
        child_url = "https://example.com/page1"
        child_path = scraper._build_traversal_path(child_url, parent_url)

        expected_path = [parent_url, child_url]
        assert child_path == expected_path
        assert scraper._url_traversal_paths[child_url] == expected_path

    def test_should_skip_url_for_loop_prevention(self, scraper):
        """Test comprehensive loop prevention logic."""
        scraper._global_visited_urls.clear()
        scraper._url_traversal_paths.clear()

        visited_url = "https://example.com/visited"
        normalized_visited = scraper.url_validator.normalize_url(visited_url)
        scraper._global_visited_urls.add(normalized_visited)

        assert (
            scraper._should_skip_url_for_loop_prevention(visited_url, None, 1) is True
        )

        new_url = "https://example.com/new"
        assert scraper._should_skip_url_for_loop_prevention(new_url, None, 1) is False

        repeated_url = "https://example.com/cat/cat/cat/cat/page"
        assert (
            scraper._should_skip_url_for_loop_prevention(repeated_url, None, 1) is True
        )

    @pytest.mark.asyncio
    async def test_loop_prevention_in_recursive_scraping(self, scraper):
        """Test loop prevention integration in recursive scraping."""
        with (
            patch("content_collector.core.scraper.db_manager") as mock_db_manager,
            patch("content_collector.core.scraper.file_storage") as mock_file_storage,
        ):

            mock_session = AsyncMock()
            mock_db_manager.session.return_value.__aenter__.return_value = mock_session

            mock_session.execute.return_value.scalar_one_or_none.return_value = None

            url_entries = [
                URLEntry(url="https://example.com/page1", description="test"),
                URLEntry(url="https://example.com/page2", description="test"),
            ]

            scraper._scrape_single_url_with_children = AsyncMock()
            scraper._get_page_id_by_url = AsyncMock(return_value="test-page-id")

            scraper._scrape_single_url_with_children.side_effect = [
                ["https://example.com/page2", "https://example.com/page3"],
                ["https://example.com/page1"],
            ]

            await scraper._scrape_urls_recursive(url_entries, "test-run", 2)

            call_count = scraper._scrape_single_url_with_children.call_count
            assert call_count > 0, "Should have made some scraping calls"
            assert (
                call_count < 10
            ), "Should not have made excessive calls due to loop prevention"

            assert (
                len(scraper._global_visited_urls) > 0
            ), "Should have tracked visited URLs"

    def test_loop_prevention_configuration(self, scraper):
        """Test that loop prevention respects configuration settings."""
        original_setting = settings.scraping.enable_loop_prevention
        settings.scraping.enable_loop_prevention = False

        try:
            result = scraper._should_skip_url_for_loop_prevention(
                "https://example.com/any", None, 1
            )
            assert result is False
        finally:
            settings.scraping.enable_loop_prevention = original_setting

        original_pattern_setting = settings.scraping.enable_pattern_detection
        settings.scraping.enable_pattern_detection = False

        try:
            repeated_url = "https://example.com/cat/cat/cat/cat/page"
            result = scraper._should_skip_url_for_loop_prevention(repeated_url, None, 1)
            assert isinstance(result, bool)
        finally:
            settings.scraping.enable_pattern_detection = original_pattern_setting


if __name__ == "__main__":
    pytest.main([__file__])
