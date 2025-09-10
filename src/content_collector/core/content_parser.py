"""
Comprehensive content parser for HTML, JavaScript-rendered pages, PDFs, and images.
Automatically detects content type and uses the most appropriate parsing method.
"""

import asyncio
import hashlib
import io
import json
import re
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Set, Union
from urllib.parse import urljoin

import aiohttp
import structlog
from selectolax.parser import HTMLParser

from ..config.settings import settings
from ..utils.validators import URLValidator

# Import intelligence system for advanced analysis
try:
    from .intelligence import ContentIntelligence

    INTELLIGENCE_AVAILABLE = True
except ImportError:
    INTELLIGENCE_AVAILABLE = False

logger = structlog.get_logger()

# Optional imports with graceful fallback
try:
    import pytesseract
    from PIL import Image

    TESSERACT_AVAILABLE = True
except ImportError:
    if TYPE_CHECKING:
        from PIL import Image
    else:
        Image = None
    TESSERACT_AVAILABLE = False

try:
    from pdf2image import convert_from_bytes, convert_from_path

    PDF2IMAGE_AVAILABLE = True
except ImportError:
    PDF2IMAGE_AVAILABLE = False

try:
    import cv2
    import numpy as np

    OPENCV_AVAILABLE = True
except ImportError:
    cv2 = None
    np = None
    OPENCV_AVAILABLE = False

try:
    import pdfplumber

    PDFPLUMBER_AVAILABLE = True
except ImportError:
    pdfplumber = None
    PDFPLUMBER_AVAILABLE = False

try:
    from playwright.async_api import async_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    async_playwright = None
    PLAYWRIGHT_AVAILABLE = False


class ContentParser:
    """
    Comprehensive content parser that automatically handles all content types:
    - HTML pages (standard and JavaScript-rendered)
    - PDF documents (digital text extraction + OCR for scanned content)
    - Images (OCR text extraction)
    - Various document formats
    """

    def __init__(
        self, debug_links: bool = False, enable_intelligence: bool = True
    ) -> None:
        """Initialize comprehensive content parser."""
        self.logger = logger.bind(component="content_parser")
        self.url_validator = URLValidator()
        self.debug_links = debug_links
        self.debug_info = {"found_links": [], "filtered_links": [], "sources": []}

        # Browser instance for JavaScript rendering
        self.browser = None
        self.playwright = None

        # AI-powered content intelligence
        self.enable_intelligence = enable_intelligence and INTELLIGENCE_AVAILABLE
        if self.enable_intelligence:
            self.intelligence = ContentIntelligence()
        else:
            self.intelligence = None

        # JavaScript-heavy domains that should use browser rendering
        self.js_domains = {
            "vercel.com",
            "react.dev",
            "angular.io",
            "vuejs.org",
            "nextjs.org",
            "twitter.com",
            "x.com",
            "instagram.com",
            "facebook.com",
            "linkedin.com",
            "medium.com",
            "dev.to",
            "github.com",
            "gitlab.com",
            "notion.so",
            "airbnb.com",
            "uber.com",
            "netflix.com",
            "spotify.com",
        }

        # Initialize parsing capabilities
        if TESSERACT_AVAILABLE and settings.parsing.tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = settings.parsing.tesseract_cmd

    async def parse(self, content: Union[str, bytes, Path], source_url: str) -> Dict:
        """
        Parse any content type automatically.

        Args:
            content: URL, HTML string, file path, or raw bytes
            source_url: Source URL for context and link resolution

        Returns:
            Dictionary containing parsed content and metadata
        """
        try:
            # Detect content type and choose parsing strategy
            content_info = self._analyze_content(content)

            self.logger.info(
                "Parsing content",
                content_type=content_info["type"],
                strategy=content_info["strategy"],
                source_url=source_url,
            )

            # Parse based on detected strategy
            if content_info["strategy"] == "javascript":
                result = await self._parse_with_javascript(content, source_url)
            elif content_info["strategy"] == "ocr":
                result = self._parse_with_ocr(content, source_url, content_info["type"])
            elif content_info["strategy"] == "hybrid_pdf":
                result = self._parse_hybrid_pdf(content, source_url)
            else:  # html
                result = await self._parse_html(content, source_url)

            # Add intelligent analysis if enabled
            if self.enable_intelligence and result.get("body_text"):
                intelligence_result = self.intelligence.analyze_content(result)
                result["intelligence"] = intelligence_result

            return result

        except Exception as e:
            self.logger.error(f"Content parsing failed: {e}", source_url=source_url)
            return self._empty_result()

    def _analyze_content(self, content: Union[str, bytes, Path]) -> Dict:
        """Analyze content to determine the best parsing strategy."""
        # File path analysis
        if isinstance(content, (str, Path)):
            try:
                path = Path(content) if isinstance(content, str) else content
                if path.exists() and path.is_file():
                    suffix = path.suffix.lower()
                    if suffix == ".pdf":
                        return {"type": "pdf_file", "strategy": "hybrid_pdf"}
                    elif suffix in [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff"]:
                        return {"type": "image_file", "strategy": "ocr"}
                    elif suffix in [".html", ".htm"]:
                        return {"type": "html_file", "strategy": "html"}
            except:
                pass

        # Bytes analysis
        if isinstance(content, bytes):
            if content.startswith(b"%PDF"):
                return {"type": "pdf_bytes", "strategy": "hybrid_pdf"}
            elif content.startswith((b"\xff\xd8\xff", b"\x89PNG", b"GIF8")):
                return {"type": "image_bytes", "strategy": "ocr"}
            else:
                return {"type": "html_bytes", "strategy": "html"}

        # URL analysis
        if isinstance(content, str) and content.startswith(("http://", "https://")):
            # Check if this domain typically uses heavy JavaScript
            if any(domain in content for domain in self.js_domains):
                return {"type": "url", "strategy": "javascript"}
            return {"type": "url", "strategy": "html"}

        # Default to HTML string
        return {"type": "html_string", "strategy": "html"}

    async def _parse_html(self, content: Union[str, bytes], source_url: str) -> Dict:
        """Parse HTML content (including fetching from URLs)."""
        html_content = content

        # Fetch URL content if needed
        if isinstance(content, str) and content.startswith(("http://", "https://")):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        content, timeout=aiohttp.ClientTimeout(total=30)
                    ) as response:
                        html_content = await response.text()
            except Exception as e:
                self.logger.error(f"Failed to fetch URL: {e}", url=content)
                return self._empty_result()
        elif isinstance(content, bytes):
            html_content = content.decode("utf-8", errors="ignore")

        # Parse HTML
        return self._parse_html_content(html_content, source_url)

    async def _parse_with_javascript(self, url: str, source_url: str) -> Dict:
        """Parse JavaScript-rendered content using browser."""
        if not PLAYWRIGHT_AVAILABLE:
            self.logger.warning(
                "Playwright not available, falling back to HTML parsing"
            )
            return await self._parse_html(url, source_url)

        try:
            await self._init_browser()

            page = await self.browser.new_page()
            await page.goto(
                url, wait_until="networkidle", timeout=settings.parsing.js_timeout
            )

            # Wait for dynamic content
            await self._wait_for_dynamic_content(page)

            # Extract rendered HTML
            content = await page.content()

            # Extract JavaScript-specific data
            js_data = await self._extract_javascript_data(page)

            await page.close()

            # Parse the rendered HTML
            result = self._parse_html_content(content, source_url)
            result["rendering_method"] = "playwright"

            if js_data:
                result["js_data"] = js_data
                # Merge additional links found via JavaScript
                if js_data.get("js_links"):
                    additional_links = []
                    for link in js_data["js_links"]:
                        normalized = self._normalize_and_validate_url(link, source_url)
                        if normalized and normalized not in result["links"]:
                            additional_links.append(normalized)

                    result["links"].extend(additional_links)
                    result["link_count"] = len(result["links"])

            return result

        except Exception as e:
            self.logger.error(f"JavaScript parsing failed: {e}", url=url)
            return await self._parse_html(url, source_url)

    def _parse_with_ocr(
        self, content: Union[bytes, str, Path], source_url: str, content_type: str
    ) -> Dict:
        """Parse content using OCR."""
        if not TESSERACT_AVAILABLE:
            self.logger.warning("Tesseract not available for OCR")
            return self._empty_result()

        try:
            if content_type.startswith("image"):
                if not TESSERACT_AVAILABLE or Image is None:
                    self.logger.warning("PIL not available for image processing")
                    return self._empty_result()

                if isinstance(content, (str, Path)):
                    image = Image.open(content)
                else:  # bytes
                    image = Image.open(io.BytesIO(content))

                text = self._ocr_image(image)
                return self._create_ocr_result(text, source_url, "image")

        except Exception as e:
            self.logger.error(f"OCR parsing failed: {e}")
            return self._empty_result()

    def _parse_hybrid_pdf(
        self, content: Union[bytes, str, Path], source_url: str
    ) -> Dict:
        """Parse PDF using both digital text extraction and OCR."""
        all_text = []

        # Try digital text extraction first
        if PDFPLUMBER_AVAILABLE:
            try:
                if isinstance(content, (str, Path)):
                    digital_text = self._extract_digital_pdf_text(Path(content))
                else:
                    with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
                        tmp.write(content)
                        tmp.flush()
                        digital_text = self._extract_digital_pdf_text(Path(tmp.name))

                if digital_text:
                    all_text.append(digital_text)
                    self.logger.info("Extracted digital text from PDF")
            except Exception as e:
                self.logger.warning(f"Digital PDF extraction failed: {e}")

        # OCR for scanned content if no digital text or as supplement
        if not all_text and PDF2IMAGE_AVAILABLE and TESSERACT_AVAILABLE:
            try:
                if isinstance(content, (str, Path)):
                    pages = convert_from_path(str(content))
                else:
                    pages = convert_from_bytes(content)

                for i, page_image in enumerate(pages):
                    ocr_text = self._ocr_image(page_image)
                    if ocr_text:
                        all_text.append(f"--- Page {i+1} ---\n{ocr_text}")

                if pages:
                    self.logger.info(f"OCR completed for {len(pages)} pages")

            except Exception as e:
                self.logger.warning(f"PDF OCR failed: {e}")

        final_text = "\n\n".join(all_text)
        return self._create_ocr_result(final_text, source_url, "pdf")

    def _parse_html_content(self, content: str, base_url: str) -> Dict:
        """Parse HTML content and extract all information."""
        try:
            parser = HTMLParser(content)

            # Extract standard elements
            title = self._extract_title(parser)
            meta_description = self._extract_meta_description(parser)
            headers = self._extract_headers(parser)
            body_text = self._extract_body_text(parser)
            links = self._extract_links(parser, base_url)

            # Extract head HTML
            head_html = ""
            head_node = parser.css_first("head")
            if head_node:
                head_html = head_node.html

            content_hash = self._generate_content_hash(body_text)

            result = {
                "title": title,
                "meta_description": meta_description,
                "headers": headers,
                "head_html": head_html,
                "body_text": body_text,
                "links": links,
                "content_hash": content_hash,
                "content_length": len(content),
                "link_count": len(links),
            }

            self._log_parsing_stats(result)

            return result

        except Exception as e:
            self.logger.error(f"HTML content parsing failed: {e}")
            return self._empty_result()

    async def _init_browser(self):
        """Initialize Playwright browser if needed."""
        if not self.playwright:
            self.playwright = await async_playwright().start()

        if not self.browser:
            self.browser = await self.playwright.chromium.launch(
                headless=settings.parsing.js_headless,
                args=["--no-sandbox", "--disable-setuid-sandbox"],
            )

    async def _wait_for_dynamic_content(self, page):
        """Wait for JavaScript-rendered content to load."""
        try:
            # Wait for common SPA indicators
            selectors = ["[data-reactroot]", "[ng-app]", "#app", ".content-loaded"]

            for selector in selectors:
                try:
                    await page.wait_for_selector(selector, timeout=2000)
                    break
                except:
                    continue

        except Exception:
            pass  # Continue even if no indicators found

    async def _extract_javascript_data(self, page) -> Dict:
        """Extract data from JavaScript context."""
        try:
            # Extract JavaScript-added links
            js_links = await page.evaluate(
                """
                () => {
                    const links = new Set();

                    // All anchor tags
                    document.querySelectorAll('a[href]').forEach(a => links.add(a.href));

                    // React Router links
                    document.querySelectorAll('[to]').forEach(el => {
                        const to = el.getAttribute('to');
                        if (to) links.add(to);
                    });

                    // Data attributes
                    document.querySelectorAll('[data-href]').forEach(el => {
                        links.add(el.getAttribute('data-href'));
                    });

                    return Array.from(links);
                }
            """
            )

            return {"js_links": js_links} if js_links else {}

        except Exception as e:
            self.logger.warning(f"JavaScript data extraction failed: {e}")
            return {}

    def _ocr_image(self, image) -> str:
        """Perform OCR on image."""
        try:
            # Preprocess if OpenCV available
            if OPENCV_AVAILABLE and settings.parsing.enable_preprocessing:
                image = self._preprocess_image(image)

            config = f"--psm {settings.parsing.ocr_psm}"
            text = pytesseract.image_to_string(
                image, lang=settings.parsing.ocr_lang, config=config
            )
            return text.strip()

        except Exception as e:
            self.logger.error(f"OCR failed: {e}")
            return ""

    def _preprocess_image(self, image):
        """Preprocess image for better OCR."""
        try:
            # Convert to grayscale and apply thresholding
            img_array = np.array(image)

            if len(img_array.shape) == 3:
                gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
            else:
                gray = img_array

            _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
            processed = cv2.medianBlur(thresh, 3)

            if Image is not None:
                return Image.fromarray(processed)
            else:
                return image

        except Exception:
            return image

    def _extract_digital_pdf_text(self, pdf_path: Path) -> Optional[str]:
        """Extract text from digital PDF."""
        try:
            all_text = []
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        all_text.append(text)

            return "\n\n".join(all_text) if all_text else None

        except Exception as e:
            self.logger.warning(f"Digital PDF extraction failed: {e}")
            return None

    # HTML extraction methods (consolidated from original parser.py)
    def _extract_title(self, parser: HTMLParser) -> Optional[str]:
        """Extract page title."""
        title_node = parser.css_first("title")
        return title_node.text().strip() if title_node and title_node.text() else None

    def _extract_meta_description(self, parser: HTMLParser) -> Optional[str]:
        """Extract meta description."""
        meta_desc = parser.css_first('meta[name="description"]')
        if meta_desc:
            return meta_desc.attributes.get("content", "").strip()

        og_desc = parser.css_first('meta[property="og:description"]')
        if og_desc:
            return og_desc.attributes.get("content", "").strip()

        return None

    def _extract_headers(self, parser: HTMLParser) -> Dict[str, List[str]]:
        """Extract heading tags."""
        headers = {"h1": [], "h2": [], "h3": []}

        for level in ["h1", "h2", "h3"]:
            for header in parser.css(level):
                text = header.text().strip()
                if text:
                    headers[level].append(text)

        return headers

    def _extract_body_text(self, parser: HTMLParser) -> str:
        """Extract clean body text."""
        # Remove non-content elements
        for tag in parser.css("script, style, nav, footer, aside, noscript"):
            tag.decompose()

        # Find main content
        main_content = parser.css_first(
            "main, article, [role='main'], .content, #content"
        )
        if main_content:
            text = main_content.text()
        else:
            body = parser.css_first("body")
            text = body.text() if body else parser.text()

        return " ".join(text.split())

    def _extract_links(self, parser: HTMLParser, base_url: str) -> List[str]:
        """Extract and validate all links from HTML."""
        links: Set[str] = set()

        # Standard links
        for link in parser.css("a[href]"):
            href = link.attributes.get("href", "").strip()
            if href:
                self._add_link(href, base_url, links, "a-tag")

        # Additional link sources (forms, meta, etc.)
        self._extract_additional_links(parser, base_url, links)

        return list(links)

    def _extract_additional_links(
        self, parser: HTMLParser, base_url: str, links: Set[str]
    ):
        """Extract links from additional sources."""
        # Navigation, footer, forms, etc.
        selectors = [
            ("nav a[href], [role='navigation'] a[href]", "navigation"),
            ("footer a[href]", "footer"),
            ("form[action]", "form"),
            ("[data-href], [data-url]", "data-attr"),
        ]

        for selector, source in selectors:
            for element in parser.css(selector):
                href = (
                    element.attributes.get("href")
                    or element.attributes.get("action")
                    or element.attributes.get("data-href")
                    or element.attributes.get("data-url")
                )
                if href and href.strip():
                    self._add_link(href.strip(), base_url, links, source)

    def _add_link(
        self, href: str, base_url: str, links: Set[str], source: str = "unknown"
    ):
        """Validate and add link to set."""
        if self.debug_links:
            self.debug_info["found_links"].append(f"{href} (from: {source})")

        normalized = self._normalize_and_validate_url(href, base_url)
        if normalized:
            links.add(normalized)
            if self.debug_links and source not in self.debug_info["sources"]:
                self.debug_info["sources"].append(source)
        elif self.debug_links:
            self.debug_info["filtered_links"].append(f"{href} - failed validation")

    def _normalize_and_validate_url(self, href: str, base_url: str) -> Optional[str]:
        """Normalize and validate URL."""
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            return None

        absolute_url = self.url_validator.resolve_relative_url(base_url, href)
        normalized_url = self.url_validator.normalize_url(absolute_url)

        if normalized_url and self.url_validator.is_valid_url(normalized_url):
            return normalized_url
        return None

    def _create_ocr_result(self, text: str, source_url: str, content_type: str) -> Dict:
        """Create OCR result with extracted structure."""
        # Simple title extraction (first non-empty line)
        title = None
        lines = text.split("\n")
        for line in lines:
            if line.strip():
                title = line.strip()[:100]
                break

        # Extract URLs from text
        urls = re.findall(r'https?://[^\s<>"{}|\\^`\[\]]+', text)
        links = []
        for url in urls:
            normalized = self._normalize_and_validate_url(url, "")
            if normalized:
                links.append(normalized)

        # Basic header extraction
        headers = self._extract_headers_from_text(text)

        return {
            "title": title,
            "meta_description": None,
            "headers": headers,
            "head_html": "",
            "body_text": text,
            "links": links,
            "content_hash": self._generate_content_hash(text),
            "content_length": len(text),
            "link_count": len(links),
            "ocr_performed": True,
            "content_type": content_type,
            "source_url": source_url,
        }

    def _extract_headers_from_text(self, text: str) -> Dict[str, List[str]]:
        """Extract potential headers from plain text."""
        headers = {"h1": [], "h2": [], "h3": []}

        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue

            # Heuristics for headers
            if line.isupper() and len(line) < 100:
                headers["h1"].append(line)
            elif line.endswith(":") and len(line) < 80:
                headers["h2"].append(line[:-1])
            elif line.istitle() and len(line) < 60:
                headers["h3"].append(line)

        return headers

    def _generate_content_hash(self, content: str) -> str:
        """Generate content hash."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _empty_result(self) -> Dict:
        """Return empty parsing result."""
        return {
            "title": None,
            "meta_description": None,
            "headers": {"h1": [], "h2": [], "h3": []},
            "head_html": "",
            "body_text": "",
            "links": [],
            "content_hash": "",
            "content_length": 0,
            "link_count": 0,
        }

    def _log_parsing_stats(self, result: Dict):
        """Log parsing statistics."""
        self.logger.debug(
            "Content parsed",
            title=result.get("title"),
            headers_count=sum(len(h) for h in result.get("headers", {}).values()),
            links_count=result.get("link_count", 0),
            body_length=len(result.get("body_text", "")),
        )

        if self.debug_links and self.debug_info:
            self.logger.info(
                "Link extraction debug info",
                found_links=len(self.debug_info["found_links"]),
                filtered_links=len(self.debug_info["filtered_links"]),
                final_links=result.get("link_count", 0),
                sources=self.debug_info["sources"],
            )

    async def close(self):
        """Clean up resources."""
        if self.browser:
            await self.browser.close()
            self.browser = None

        if self.playwright:
            await self.playwright.stop()
            self.playwright = None


# Legacy function for backward compatibility
async def parse_content(
    content: Union[str, bytes, Path], source_url: str, enable_intelligence: bool = True
) -> Dict:
    """Parse content using comprehensive parser with optional intelligence analysis."""
    parser = ContentParser(enable_intelligence=enable_intelligence)
    try:
        return await parser.parse(content, source_url)
    finally:
        await parser.close()


def parse_html(content: str, base_url: str = "http://example.com") -> Dict:
    """Legacy synchronous HTML parsing function."""
    parser = ContentParser()
    return parser._parse_html_content(content, base_url)
