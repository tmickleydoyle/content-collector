"""Tests for the comprehensive content parser."""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.content_collector.core.content_parser import ContentParser


class TestContentParser:
    """Test comprehensive content parser."""

    @pytest.fixture
    def parser(self):
        """Create content parser instance."""
        return ContentParser()

    def test_analyze_content_html_string(self, parser):
        """Test content analysis for HTML strings."""
        html = "<html><body>Test</body></html>"
        info = parser._analyze_content(html)

        assert info["type"] == "html_string"
        assert info["strategy"] == "html"

    def test_analyze_content_url_js_heavy(self, parser):
        """Test content analysis for JavaScript-heavy URLs."""
        url = "https://vercel.com/dashboard"
        info = parser._analyze_content(url)

        assert info["type"] == "url"
        assert info["strategy"] == "javascript"

    def test_analyze_content_url_regular(self, parser):
        """Test content analysis for regular URLs."""
        url = "https://example.com"
        info = parser._analyze_content(url)

        assert info["type"] == "url"
        assert info["strategy"] == "html"

    def test_analyze_content_pdf_bytes(self, parser):
        """Test content analysis for PDF bytes."""
        pdf_bytes = b"%PDF-1.4 test content"
        info = parser._analyze_content(pdf_bytes)

        assert info["type"] == "pdf_bytes"
        assert info["strategy"] == "hybrid_pdf"

    def test_analyze_content_image_bytes(self, parser):
        """Test content analysis for image bytes."""
        png_bytes = b"\x89PNG test content"
        info = parser._analyze_content(png_bytes)

        assert info["type"] == "image_bytes"
        assert info["strategy"] == "ocr"

    def test_parse_html_content(self, parser):
        """Test HTML content parsing."""
        html = """
        <html>
            <head>
                <title>Test Page</title>
                <meta name="description" content="Test description">
            </head>
            <body>
                <h1>Main Header</h1>
                <p>Content here</p>
                <a href="https://example.com">Link</a>
            </body>
        </html>
        """

        result = parser._parse_html_content(html, "https://test.com")

        assert result["title"] == "Test Page"
        assert result["meta_description"] == "Test description"
        assert "Main Header" in result["headers"]["h1"]
        assert "Content here" in result["body_text"]
        assert "https://example.com" in result["links"]

    @pytest.mark.asyncio
    async def test_parse_html_url(self, parser):
        """Test parsing HTML from URL."""
        with patch("aiohttp.ClientSession") as mock_session:
            mock_response = AsyncMock()
            mock_response.text.return_value = (
                "<html><title>Test</title><body>Content</body></html>"
            )

            mock_session.return_value.__aenter__.return_value.get.return_value.__aenter__.return_value = (
                mock_response
            )

            result = await parser._parse_html(
                "https://example.com", "https://example.com"
            )

            assert result["title"] == "Test"
            assert "Content" in result["body_text"]

    def test_normalize_and_validate_url(self, parser):
        """Test URL normalization and validation."""
        # Valid relative URL
        result = parser._normalize_and_validate_url("about", "https://example.com")
        assert result == "https://example.com/about"

        # Valid absolute URL
        result = parser._normalize_and_validate_url(
            "https://test.com", "https://example.com"
        )
        assert result == "https://test.com"

        # Invalid URLs
        assert (
            parser._normalize_and_validate_url("#fragment", "https://example.com")
            is None
        )
        assert (
            parser._normalize_and_validate_url(
                "javascript:void(0)", "https://example.com"
            )
            is None
        )

    def test_extract_headers_from_text(self, parser):
        """Test header extraction from plain text."""
        text = """MAIN TITLE

        Subtitle:
        Some regular text
        Another Section:
        More text
        """

        headers = parser._extract_headers_from_text(text)

        assert "MAIN TITLE" in headers["h1"]
        assert "Subtitle" in headers["h2"]
        assert "Another Section" in headers["h2"]

    @patch("src.content_collector.core.content_parser.TESSERACT_AVAILABLE", True)
    @patch("pytesseract.image_to_string")
    def test_ocr_image(self, mock_ocr, parser):
        """Test OCR functionality."""
        from PIL import Image

        mock_ocr.return_value = "Extracted text from image"

        image = Image.new("RGB", (100, 100), color="white")
        result = parser._ocr_image(image)

        assert result == "Extracted text from image"
        mock_ocr.assert_called_once()

    @patch("src.content_collector.core.content_parser.TESSERACT_AVAILABLE", False)
    def test_ocr_image_unavailable(self, parser):
        """Test OCR when Tesseract unavailable."""
        from PIL import Image

        image = Image.new("RGB", (100, 100), color="white")
        result = parser._ocr_image(image)

        assert result == ""

    @patch("src.content_collector.core.content_parser.PDFPLUMBER_AVAILABLE", True)
    @patch("pdfplumber.open")
    def test_extract_digital_pdf_text(self, mock_pdfplumber, parser):
        """Test digital PDF text extraction."""
        mock_page = Mock()
        mock_page.extract_text.return_value = "Digital text content"

        mock_pdf = Mock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = Mock(return_value=mock_pdf)
        mock_pdf.__exit__ = Mock()

        mock_pdfplumber.return_value = mock_pdf

        result = parser._extract_digital_pdf_text(Path("/fake/path.pdf"))

        assert result == "Digital text content"

    def test_create_ocr_result(self, parser):
        """Test OCR result creation."""
        text = "TITLE\n\nSome content with https://example.com link"

        with patch.object(parser, "_normalize_and_validate_url") as mock_normalize:
            mock_normalize.return_value = "https://example.com"

            result = parser._create_ocr_result(text, "https://source.com", "pdf")

            assert result["title"] == "TITLE"
            assert result["body_text"] == text
            assert result["content_type"] == "pdf"
            assert result["ocr_performed"] is True
            assert "https://example.com" in result["links"]

    @pytest.mark.asyncio
    async def test_parse_javascript_fallback(self, parser):
        """Test JavaScript parsing fallback to HTML when Playwright unavailable."""
        with patch(
            "src.content_collector.core.content_parser.PLAYWRIGHT_AVAILABLE", False
        ):
            with patch.object(parser, "_parse_html") as mock_parse_html:
                mock_parse_html.return_value = {"title": "Test", "body_text": "Content"}

                result = await parser._parse_with_javascript(
                    "https://vercel.com", "https://vercel.com"
                )

                mock_parse_html.assert_called_once_with(
                    "https://vercel.com", "https://vercel.com"
                )
                assert result["title"] == "Test"

    @pytest.mark.asyncio
    async def test_parse_comprehensive(self, parser):
        """Test comprehensive parsing workflow."""
        # Test HTML string parsing
        html = "<html><title>Test</title><body>Content</body></html>"
        result = await parser.parse(html, "https://example.com")

        assert result["title"] == "Test"
        assert "Content" in result["body_text"]

    def test_file_detection(self, parser):
        """Test file path detection."""
        # Create temporary files for testing
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as pdf_file:
            pdf_file.write(b"%PDF-1.4 test")
            pdf_path = Path(pdf_file.name)

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as img_file:
            img_file.write(b"\x89PNG test")
            img_path = Path(img_file.name)

        try:
            # Test PDF detection
            pdf_info = parser._analyze_content(pdf_path)
            assert pdf_info["type"] == "pdf_file"
            assert pdf_info["strategy"] == "hybrid_pdf"

            # Test image detection
            img_info = parser._analyze_content(img_path)
            assert img_info["type"] == "image_file"
            assert img_info["strategy"] == "ocr"

        finally:
            pdf_path.unlink()
            img_path.unlink()

    @pytest.mark.asyncio
    async def test_cleanup(self, parser):
        """Test resource cleanup."""
        # Should not raise any exceptions
        await parser.close()


@pytest.mark.integration
class TestContentParserIntegration:
    """Integration tests for content parser."""

    @pytest.mark.asyncio
    async def test_real_html_parsing(self):
        """Test parsing with actual HTML content."""
        parser = ContentParser()

        html_content = """
        <html>
            <head>
                <title>Integration Test</title>
                <meta name="description" content="Test description">
            </head>
            <body>
                <h1>Main Header</h1>
                <h2>Sub Header</h2>
                <p>This is test content with <a href="https://example.com">a link</a>.</p>
                <nav>
                    <a href="/page1">Page 1</a>
                    <a href="/page2">Page 2</a>
                </nav>
            </body>
        </html>
        """

        try:
            result = await parser.parse(html_content, "https://test.com")

            # Verify title and description
            assert result["title"] == "Integration Test"
            assert result["meta_description"] == "Test description"

            # Verify headers
            assert "Main Header" in result["headers"]["h1"]
            assert "Sub Header" in result["headers"]["h2"]

            # Verify content
            assert "This is test content" in result["body_text"]

            # Verify links (should be resolved to absolute)
            links = result["links"]
            assert "https://example.com" in links
            assert "https://test.com/page1" in links
            assert "https://test.com/page2" in links

            # Verify metadata
            assert result["link_count"] == len(links)
            assert result["content_hash"]
            assert result["content_length"] > 0

        finally:
            await parser.close()


@pytest.mark.skipif(
    not pytest.importorskip("playwright", reason="Playwright not available"),
    reason="Requires Playwright for JavaScript testing",
)
class TestJavaScriptParsing:
    """Tests for JavaScript parsing capabilities."""

    @pytest.mark.asyncio
    async def test_javascript_parsing_placeholder(self):
        """Placeholder for JavaScript parsing tests."""
        # These tests would require actual Playwright setup
        # and would be more suitable for end-to-end testing
        pass
