"""Test input processor functionality."""

import asyncio
import tempfile
from pathlib import Path

import pytest

from content_collector.input.processor import InputProcessor, URLEntry


class TestInputProcessor:
    """Test input processing functionality."""

    def setup_method(self):
        """Setup test fixtures."""
        self.processor = InputProcessor()

    @pytest.mark.asyncio
    async def test_process_simple_csv(self):
        """Test processing a simple CSV file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            csv_file = temp_path / "test_urls.csv"
            csv_file.write_text(
                "url,description\nhttps://example.com,Test site\nhttps://test.com,Another site\n"
            )

            input_file = temp_path / "input.txt"
            input_file.write_text(str(csv_file))

            url_entries = await self.processor.process_input_file(input_file)
        assert len(url_entries) == 2
        assert str(url_entries[0].url) == "https://example.com/"
        assert str(url_entries[1].url) == "https://test.com/"

    @pytest.mark.asyncio
    async def test_deduplicate_urls(self):
        """Test URL deduplication."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            csv_file = temp_path / "test_urls.csv"
            csv_file.write_text(
                "url\nhttps://example.com\nhttps://test.com\nhttps://example.com\n"
            )

            input_file = temp_path / "input.txt"
            input_file.write_text(str(csv_file))

            url_entries = await self.processor.process_input_file(input_file)
        assert len(url_entries) == 2
        urls = [str(entry.url) for entry in url_entries]
        assert "https://example.com/" in urls
        assert "https://test.com/" in urls

    @pytest.mark.asyncio
    async def test_invalid_urls_skipped(self):
        """Test that invalid URLs are skipped."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            csv_file = temp_path / "test_urls.csv"
            csv_file.write_text(
                "url\nhttps://example.com\ninvalid_url\nftp://ftp.example.com\n"
            )

            input_file = temp_path / "input.txt"
            input_file.write_text(str(csv_file))

            url_entries = await self.processor.process_input_file(input_file)
        assert len(url_entries) == 1
        assert str(url_entries[0].url) == "https://example.com/"
