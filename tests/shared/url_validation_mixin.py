"""Shared test utilities for URL validation."""

import pytest

from content_collector.utils.validators import URLValidator


class URLValidationTestMixin:
    """Shared test methods for URL validation functionality."""

    @pytest.fixture
    def validator(self):
        """Create URLValidator instance for testing."""
        return URLValidator()

    def test_valid_http_urls(self, validator):
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
            "https://site.co.uk",
        ]

        for url in valid_urls:
            assert validator.is_valid_url(url), f"URL should be valid: {url}"

    def test_invalid_urls(self, validator):
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
            "http://localhost",
            "https://127.0.0.1",
            "https://192.168.1.1",
        ]

        for url in invalid_urls:
            assert not validator.is_valid_url(url), f"URL should be invalid: {url}"

    def test_excluded_file_extensions(self, validator):
        """Test that URLs with excluded file extensions are rejected."""
        excluded_urls = [
            "https://example.com/image.jpg",
            "https://example.com/document.doc",
            "https://example.com/archive.zip",
            "https://example.com/video.mp4",
            "https://example.com/audio.mp3",
            "https://example.com/sheet.xlsx",
        ]

        for url in excluded_urls:
            assert not validator.is_valid_url(
                url
            ), f"URL with excluded extension should be invalid: {url}"

    def test_allowed_extensions(self, validator):
        """Test that URLs with allowed extensions are accepted."""
        allowed_urls = [
            "https://example.com/page.html",
            "https://example.com/page.htm",
            "https://example.com/page.php",
            "https://example.com/page.asp",
            "https://example.com/",
            "https://example.com/path",
        ]
        for url in allowed_urls:
            assert validator.is_valid_url(
                url
            ), f"URL with allowed extension should be valid: {url}"

    def test_url_normalization(self, validator):
        """Test URL normalization functionality."""
        test_cases = [
            ("https://example.com/", "https://example.com/"),
            ("https://example.com", "https://example.com/"),
            ("https://example.com/path/../other", "https://example.com/other"),
            ("https://example.com/path?a=1&b=2", "https://example.com/path?a=1&b=2"),
            (
                "https://EXAMPLE.COM",
                "https://example.com/",
            ),
            (
                "https://EXAMPLE.COM/PATH",
                "https://example.com/PATH",
            ),
            ("https://example.com//double//slash", "https://example.com/double/slash"),
        ]

        for input_url, expected in test_cases:
            result = validator.normalize_url(input_url)
            assert (
                result == expected
            ), f"Normalization failed: {input_url} -> {result}, expected {expected}"

    def test_relative_url_resolution(self, validator):
        """Test relative URL resolution."""
        base_url = "https://example.com/section/"

        test_cases = [
            ("../other.html", "https://example.com/other.html"),
            ("./page.html", "https://example.com/section/page.html"),
            ("page.html", "https://example.com/section/page.html"),
            ("/absolute.html", "https://example.com/absolute.html"),
            ("https://other.com/external.html", "https://other.com/external.html"),
        ]

        for relative_url, expected in test_cases:
            result = validator.resolve_relative_url(base_url, relative_url)
            assert (
                result == expected
            ), f"Resolution failed: {relative_url} -> {result}, expected {expected}"

    def test_domain_extraction(self, validator):
        """Test domain extraction from URLs."""
        test_cases = [
            ("https://example.com", "example.com"),
            ("https://subdomain.example.com", "subdomain.example.com"),
            ("https://EXAMPLE.COM", "example.com"),
            ("https://example.com:8080", "example.com:8080"),
            ("https://example.com/path", "example.com"),
            ("invalid_url", None),
        ]

        for url, expected in test_cases:
            result = validator.extract_domain(url)
            assert (
                result == expected
            ), f"Domain extraction failed: {url} -> {result}, expected {expected}"

    def test_edge_cases(self, validator):
        """Test edge cases and error handling."""
        edge_cases = [
            "",
            " ",
            "https://",
            "https:///path",
            "example.com",
        ]
        for url in edge_cases:
            assert not validator.is_valid_url(
                url
            ), f"Edge case should be invalid: {url}"

    def test_normalize_url_with_invalid_input(self, validator):
        """Test URL normalization with invalid input."""
        test_cases = [
            ("", "/"),
            ("not-a-url", "/not-a-url"),
        ]
        for invalid_input, expected in test_cases:
            normalized = validator.normalize_url(invalid_input)
            assert (
                normalized == expected
            ), f"Invalid input normalization failed for '{invalid_input}': got '{normalized}', expected '{expected}'"

    def test_clean_url(self, validator):
        """Test URL cleaning functionality."""
        dirty_url = "  https://example.com/path  "
        assert not validator.is_valid_url(
            dirty_url
        ), "URLs with leading/trailing whitespace should be invalid"
        clean_url = "https://example.com/path"
        assert validator.is_valid_url(clean_url), "Clean URL should be valid"

    def test_is_valid_url_with_none_input(self, validator):
        """Test URL validation with None input."""
        assert not validator.is_valid_url(None), "None input should be invalid"

    def test_is_valid_url_with_non_string_input(self, validator):
        """Test URL validation with non-string input."""
        assert not validator.is_valid_url(123), "Non-string input should be invalid"
        assert not validator.is_valid_url([]), "Non-string input should be invalid"
        assert not validator.is_valid_url({}), "Non-string input should be invalid"

    @pytest.mark.parametrize(
        "url,expected",
        [
            ("https://example.com", True),
            ("http://example.com", True),
            ("ftp://example.com", False),
            ("", False),
            ("invalid", False),
        ],
    )
    def test_parameterized_validation(self, validator, url, expected):
        """Test URL validation with parameterized inputs."""
        result = validator.is_valid_url(url)
        assert result == expected, f"URL {url} validation failed"
