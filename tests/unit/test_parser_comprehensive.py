"""Comprehensive tests for ContentParser class."""

from unittest.mock import Mock, patch

import pytest

from content_collector.core.parser import ContentParser


class TestContentParser:
    """Test suite for ContentParser class."""

    @pytest.fixture
    def parser(self):
        """Create ContentParser instance for testing."""
        return ContentParser()

    @pytest.fixture
    def sample_html(self):
        """Sample HTML content for testing."""
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Test Page</title>
            <meta name="description" content="Test description">
            <meta name="keywords" content="test, keywords">
        </head>
        <body>
            <h1>Main Heading</h1>
            <h2>Sub Heading</h2>
            <p>This is a test paragraph with some text.</p>
            <a href="https://example.com">External Link</a>
            <a href="/internal">Internal Link</a>
            <a href="mailto:test@example.com">Email Link</a>
            <img src="/image.jpg" alt="Test Image">
            <script>console.log('test');</script>
            <style>body { color: red; }</style>
        </body>
        </html>
        """

    def test_parse_html_success(self, parser, sample_html):
        """Test successful HTML parsing."""
        base_url = "https://example.com"

        result = parser.parse_html(sample_html, base_url)

        assert isinstance(result, dict)
        assert result["title"] == "Test Page"
        assert result["meta_description"] == "Test description"
        assert "Main Heading" in result["body_text"]
        assert "test paragraph" in result["body_text"]
        assert len(result["links"]) > 0
        assert result["content_length"] > 0
        assert "content_hash" in result

    def test_parse_html_with_empty_content(self, parser):
        """Test parsing empty HTML."""
        result = parser.parse_html("", "https://example.com")

        assert isinstance(result, dict)
        assert result["content_length"] == 0

    def test_parse_html_with_invalid_html(self, parser):
        """Test parsing invalid HTML."""
        invalid_html = "<html><head><title>Test</title><body><p>Unclosed paragraph"

        result = parser.parse_html(invalid_html, "https://example.com")

        assert isinstance(result, dict)
        assert result["title"] == "Test"

    def test_extract_title(self, parser, sample_html):
        """Test title extraction."""
        result = parser.parse_html(sample_html, "https://example.com")
        assert result["title"] == "Test Page"

    def test_extract_title_missing(self, parser):
        """Test title extraction when missing."""
        html_no_title = "<html><body><h1>No Title</h1></body></html>"
        result = parser.parse_html(html_no_title, "https://example.com")
        assert result["title"] is None

    def test_extract_meta_description(self, parser, sample_html):
        """Test meta description extraction."""
        result = parser.parse_html(sample_html, "https://example.com")
        assert result["meta_description"] == "Test description"

    def test_extract_headers(self, parser, sample_html):
        """Test header extraction."""
        result = parser.parse_html(sample_html, "https://example.com")

        headers = result["headers"]
        assert isinstance(headers, dict)
        assert "h1" in headers
        assert "h2" in headers
        assert "Main Heading" in headers["h1"]
        assert "Sub Heading" in headers["h2"]

    def test_extract_body_text(self, parser, sample_html):
        """Test body text extraction."""
        result = parser.parse_html(sample_html, "https://example.com")

        body_text = result["body_text"]
        assert "Main Heading" in body_text
        assert "test paragraph" in body_text
        assert "console.log" not in body_text
        assert "color: red" not in body_text

    def test_extract_links(self, parser, sample_html):
        """Test link extraction and validation."""
        result = parser.parse_html(sample_html, "https://example.com")

        links = result["links"]
        assert isinstance(links, list)
        assert len(links) > 0

        link_strs = [str(link) for link in links]
        assert any("https://example.com" in link for link in link_strs)

    def test_content_hash_generation(self, parser, sample_html):
        """Test content hash generation."""
        result = parser.parse_html(sample_html, "https://example.com")

        assert "content_hash" in result
        assert isinstance(result["content_hash"], str)
        assert len(result["content_hash"]) > 0

    def test_parse_html_with_malformed_content(self, parser):
        """Test parsing with malformed HTML."""
        malformed_html = "<html><body><p>Test <b>bold <i>italic</p></body></html>"

        result = parser.parse_html(malformed_html, "https://example.com")

        assert isinstance(result, dict)
        assert "Test" in result["body_text"]

    def test_parse_html_with_no_content(self, parser):
        """Test parsing HTML with no meaningful content."""
        empty_html = "<html><head></head><body></body></html>"

        result = parser.parse_html(empty_html, "https://example.com")

        assert isinstance(result, dict)
        assert result["title"] is None
        assert result["meta_description"] is None

    def test_link_count_accuracy(self, parser, sample_html):
        """Test that link count matches actual links."""
        result = parser.parse_html(sample_html, "https://example.com")

        assert result["link_count"] == len(result["links"])

    def test_error_handling(self, parser):
        """Test error handling with None content."""
        with patch("content_collector.core.parser.HTMLParser") as mock_parser:
            mock_parser.side_effect = Exception("Parse error")

            result = parser.parse_html("test", "https://example.com")

            assert isinstance(result, dict)

    def test_empty_result_structure(self, parser):
        """Test that empty result has correct structure."""
        with patch("content_collector.core.parser.HTMLParser") as mock_parser:
            mock_parser.side_effect = Exception("Parse error")

            result = parser.parse_html("test", "https://example.com")

            expected_keys = [
                "title",
                "meta_description",
                "headers",
                "body_text",
                "links",
                "content_hash",
                "content_length",
                "link_count",
            ]
            for key in expected_keys:
                assert key in result

    def test_large_content_handling(self, parser):
        """Test parsing very large HTML content."""
        large_content = (
            "<html><body>" + "<p>Large content paragraph.</p>" * 1000 + "</body></html>"
        )

        result = parser.parse_html(large_content, "https://example.com")

        assert isinstance(result, dict)
        assert result["content_length"] > 0
        assert "Large content" in result["body_text"]
