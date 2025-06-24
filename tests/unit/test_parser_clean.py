"""Unit tests for URL parsing and validation."""

from unittest.mock import Mock, patch

import pytest

from content_collector.utils.validators import URLValidator


class TestURLValidator:
    """Test URL validation functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.validator = URLValidator()

    def test_valid_http_urls(self):
        """Test validation of valid HTTP/HTTPS URLs."""
        valid_urls = [
            "https://example.com",
            "http://example.com",
            "https://subdomain.example.com",
            "https://example.com/path",
            "https://example.com/path?query=value",
            "https://example.com:8080",
            "https://example-site.com",
            "https://example.org/path/to/page.html",
        ]

        for url in valid_urls:
            assert self.validator.is_valid_url(url), f"URL should be valid: {url}"

    def test_invalid_urls(self):
        """Test validation of invalid URLs."""
        invalid_urls = [
            "",
            "not_a_url",
            "ftp://example.com",
            "mailto:test@example.com",
            "javascript:alert('test')",
            "//example.com",
            "http://",
            "https://",
            " https://example.com ",
            "https://",
            "http://localhost",
            "https://192.168.1.1",
        ]

        for url in invalid_urls:
            assert not self.validator.is_valid_url(url), f"URL should be invalid: {url}"

    def test_excluded_file_extensions(self):
        """Test that URLs with excluded file extensions are rejected."""
        excluded_urls = [
            "https://example.com/file.pdf",
            "https://example.com/image.jpg",
            "https://example.com/document.doc",
            "https://example.com/archive.zip",
            "https://example.com/video.mp4",
            "https://example.com/audio.mp3",
        ]

        for url in excluded_urls:
            assert not self.validator.is_valid_url(
                url
            ), f"URL with excluded extension should be invalid: {url}"

    def test_non_html_resources(self):
        """Test that non-HTML resources are rejected."""
        non_html_urls = [
            "https://api.example.com/data",
            "https://example.com/api/users",
            "https://example.com/download/file",
            "mailto:test@example.com",
            "tel:+1234567890",
            "ftp://files.example.com",
            "javascript:void(0)",
        ]

        for url in non_html_urls:
            assert not self.validator.is_valid_url(
                url
            ), f"Non-HTML URL should be invalid: {url}"

    def test_url_normalization(self):
        """Test URL normalization functionality."""
        test_cases = [
            ("https://example.com/", "https://example.com/"),
            ("https://example.com", "https://example.com/"),
            ("https://example.com/path/../other", "https://example.com/other"),
            ("https://example.com/path?a=1&b=2", "https://example.com/path?a=1&b=2"),
        ]

        for input_url, expected in test_cases:
            result = self.validator.normalize_url(input_url)
            assert result == expected, f"Normalization failed: {input_url} -> {result}"

    def test_relative_url_resolution(self):
        """Test relative URL resolution."""
        base_url = "https://example.com/section/"

        test_cases = [
            ("../other.html", "https://example.com/other.html"),
            ("./page.html", "https://example.com/section/page.html"),
            ("page.html", "https://example.com/section/page.html"),
            ("/absolute.html", "https://example.com/absolute.html"),
        ]

        for relative_url, expected in test_cases:
            result = self.validator.resolve_relative_url(base_url, relative_url)
            assert result == expected, f"Resolution failed: {relative_url} -> {result}"

    def test_domain_extraction(self):
        """Test domain extraction from URLs."""
        test_cases = [
            ("https://example.com", "example.com"),
            ("https://subdomain.example.com", "subdomain.example.com"),
            ("https://EXAMPLE.COM", "example.com"),
            ("https://example.com:8080", "example.com:8080"),
            ("invalid_url", None),
        ]

        for url, expected in test_cases:
            result = self.validator.extract_domain(url)
            assert result == expected, f"Domain extraction failed: {url} -> {result}"
