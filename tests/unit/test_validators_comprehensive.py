"""Comprehensive tests for URL validation utilities."""

from content_collector.utils.validators import URLValidator
from tests.shared.url_validation_mixin import URLValidationTestMixin


class TestURLValidator(URLValidationTestMixin):
    """Test suite for URLValidator class using shared test mixin."""

    def test_is_local_or_ip_address(self, validator):
        """Test detection of local/IP addresses."""
        local_urls = [
            "https://localhost",
            "https://127.0.0.1",
            "https://192.168.1.1",
            "https://10.0.0.1",
        ]
        for url in local_urls:
            assert validator._is_local_or_ip_address(
                url
            ), f"Should detect local/IP address: {url}"

        remote_urls = [
            "https://example.com",
            "https://google.com",
        ]
        for url in remote_urls:
            assert not validator._is_local_or_ip_address(
                url
            ), f"Should not detect local/IP address: {url}"

    def test_has_excluded_extension(self, validator):
        """Test file extension exclusion logic."""
        excluded_urls = [
            "https://example.com/file.pdf",
            "https://example.com/image.JPG",
            "https://example.com/video.mp4",
            "https://example.com/archive.ZIP",
        ]
        for url in excluded_urls:
            assert validator._has_excluded_extension(
                url
            ), f"Should detect excluded extension in {url}"

        allowed_urls = [
            "https://example.com/page.html",
            "https://example.com/page",
            "https://example.com/",
            "https://example.com/page.php",
        ]
        for url in allowed_urls:
            assert not validator._has_excluded_extension(
                url
            ), f"Should not detect excluded extension in {url}"

    def test_url_validation_performance(self, validator):
        """Test URL validation performance with many URLs."""
        import time

        urls = ["https://example.com/page{}".format(i) for i in range(100)]

        start_time = time.time()
        for url in urls:
            validator.is_valid_url(url)
        end_time = time.time()

        assert end_time - start_time < 1.0, "URL validation should be performant"

    def test_validator_initialization(self, validator):
        """Test URLValidator initialization."""
        assert validator is not None
        assert hasattr(validator, "is_valid_url")
        assert hasattr(validator, "normalize_url")
        assert hasattr(validator, "extract_domain")
