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
        # Create temporary files
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create CSV file
            csv_file = temp_path / "test_urls.csv"
            csv_file.write_text("url,description\nhttps://example.com,Test site\nhttps://test.com,Another site\n")
            
            # Create input file
            input_file = temp_path / "input.txt"
            input_file.write_text(str(csv_file))
            
            # Process input
            url_entries = await self.processor.process_input_file(input_file)
                 # Verify results
        assert len(url_entries) == 2
        assert str(url_entries[0].url) == "https://example.com/"  # Pydantic adds trailing slash
        assert str(url_entries[1].url) == "https://test.com/"
    
    @pytest.mark.asyncio 
    async def test_deduplicate_urls(self):
        """Test URL deduplication."""
        # Create temporary files with duplicate URLs
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create CSV file with duplicates
            csv_file = temp_path / "test_urls.csv"
            csv_file.write_text("url\nhttps://example.com\nhttps://test.com\nhttps://example.com\n")
            
            # Create input file
            input_file = temp_path / "input.txt"
            input_file.write_text(str(csv_file))
            
            # Process input
            url_entries = await self.processor.process_input_file(input_file)
                 # Verify deduplication
        assert len(url_entries) == 2
        urls = [str(entry.url) for entry in url_entries]
        assert "https://example.com/" in urls  # Pydantic adds trailing slash
        assert "https://test.com/" in urls
    
    @pytest.mark.asyncio
    async def test_invalid_urls_skipped(self):
        """Test that invalid URLs are skipped."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create CSV file with invalid URLs
            csv_file = temp_path / "test_urls.csv"
            csv_file.write_text("url\nhttps://example.com\ninvalid_url\nftp://ftp.example.com\n")
            
            # Create input file
            input_file = temp_path / "input.txt"
            input_file.write_text(str(csv_file))
            
            # Process input
            url_entries = await self.processor.process_input_file(input_file)
                 # Verify only valid URLs remain
        assert len(url_entries) == 1
        assert str(url_entries[0].url) == "https://example.com/"  # Pydantic adds trailing slash
