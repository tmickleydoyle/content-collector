"""HTML content parser for extracting metadata and links."""

import hashlib
from typing import Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse

import structlog
from selectolax.parser import HTMLParser

from ..utils.validators import URLValidator

logger = structlog.get_logger()


class ContentParser:
    """Parses HTML content to extract metadata and links."""

    def __init__(self) -> None:
        """Initialize content parser."""
        self.logger = logger.bind(component="content_parser")
        self.url_validator = URLValidator()

    def parse_html(self, content: str, base_url: str) -> Dict:
        """
        Parse HTML content and extract structured data.

        Args:
            content: HTML content to parse
            base_url: Base URL for resolving relative links

        Returns:
            Dictionary containing parsed content and metadata
        """
        try:
            parser = HTMLParser(content)

            title = self._extract_title(parser)
            meta_description = self._extract_meta_description(parser)
            headers = self._extract_headers(parser)
            body_text = self._extract_body_text(parser)
            links = self._extract_links(parser, base_url)

            content_hash = self._generate_content_hash(body_text)

            parsed_data = {
                "title": title,
                "meta_description": meta_description,
                "headers": headers,
                "body_text": body_text,
                "links": links,
                "content_hash": content_hash,
                "content_length": len(content),
                "link_count": len(links),
            }

            self.logger.debug(
                "HTML parsed",
                title=title,
                headers_count=len(headers.get("h1", [])) + len(headers.get("h2", [])),
                links_count=len(links),
                body_length=len(body_text),
            )

            return parsed_data

        except Exception as e:
            self.logger.error(
                "HTML parsing failed", error=str(e), content_length=len(content)
            )
            return self._empty_result()

    def _extract_title(self, parser: HTMLParser) -> Optional[str]:
        """Extract page title."""
        title_node = parser.css_first("title")
        if title_node:
            title_text = title_node.text()
            if title_text:
                return title_text.strip()
        return None

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
        for tag in parser.css("script, style, nav, footer, aside"):
            tag.decompose()

        main_content = parser.css_first("main, article, .content, #content")
        if main_content:
            text = main_content.text()
        else:
            body = parser.css_first("body")
            text = body.text() if body else parser.text()

        return " ".join(text.split())

    def _extract_links(self, parser: HTMLParser, base_url: str) -> List[str]:
        """Extract and validate links from HTML."""
        links: Set[str] = set()

        for link in parser.css("a[href]"):
            href = link.attributes.get("href", "").strip()
            if not href:
                continue

            absolute_url = self.url_validator.resolve_relative_url(base_url, href)
            normalized_url = self.url_validator.normalize_url(absolute_url)
            if normalized_url and self.url_validator.is_valid_url(normalized_url):
                links.add(normalized_url)

        return list(links)

    def _generate_content_hash(self, content: str) -> str:
        """Generate SHA-256 hash of content."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _empty_result(self) -> Dict:
        """Return empty parsing result."""
        return {
            "title": None,
            "meta_description": None,
            "headers": {"h1": [], "h2": [], "h3": []},
            "body_text": "",
            "links": [],
            "content_hash": "",
            "content_length": 0,
            "link_count": 0,
        }


def parse_html(content: str) -> Dict:
    """Legacy parse_html function."""
    parser = ContentParser()
    return parser.parse_html(content, "http://example.com")
