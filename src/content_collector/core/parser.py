"""HTML content parser for extracting metadata and links."""

import hashlib
from typing import Dict, List, Optional, Set

import structlog
from selectolax.parser import HTMLParser

from ..utils.validators import URLValidator

logger = structlog.get_logger()


class ContentParser:
    """Parses HTML content to extract metadata and links."""

    def __init__(self, debug_links: bool = False) -> None:
        """Initialize content parser."""
        self.logger = logger.bind(component="content_parser")
        self.url_validator = URLValidator()
        self.debug_links = debug_links
        self.debug_info = {"found_links": [], "filtered_links": [], "sources": []}

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
            # Extract full <head> section HTML for header file
            head_html = ""
            head_node = parser.css_first("head")
            if head_node:
                # html is a property returning string, not a method
                head_html = head_node.html

            content_hash = self._generate_content_hash(body_text)

            parsed_data = {
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

            self.logger.debug(
                "HTML parsed",
                title=title,
                headers_count=len(headers.get("h1", [])) + len(headers.get("h2", [])),
                links_count=len(links),
                body_length=len(body_text),
            )

            if self.debug_links and self.debug_info:
                self.logger.info(
                    "Link extraction debug info",
                    found_links=len(self.debug_info["found_links"]),
                    filtered_links=len(self.debug_info["filtered_links"]),
                    final_links=len(links),
                    sources=self.debug_info["sources"],
                )
                for i, link in enumerate(
                    self.debug_info["found_links"][:10]
                ):  # Show first 10
                    self.logger.info(f"Found link {i+1}: {link}")

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

        # Extract standard <a> links
        for link in parser.css("a[href]"):
            href = link.attributes.get("href", "").strip()
            if href:
                self._add_link(href, base_url, links, "a-tag")

        # Extract links from various other sources
        self._extract_additional_links(parser, base_url, links)

        return list(links)

    def _extract_additional_links(
        self, parser: HTMLParser, base_url: str, links: Set[str]
    ) -> None:
        """Extract links from additional sources beyond standard <a> tags."""
        # 1. Navigation links (nav elements)
        for nav in parser.css("nav a[href], [role='navigation'] a[href]"):
            href = nav.attributes.get("href", "").strip()
            if href:
                self._add_link(href, base_url, links, "navigation")

        # 2. Footer links
        for footer_link in parser.css("footer a[href], [role='contentinfo'] a[href]"):
            href = footer_link.attributes.get("href", "").strip()
            if href:
                self._add_link(href, base_url, links, "footer")

        # 3. Links with data attributes (common in SPAs)
        for data_link in parser.css(
            "[data-href], [data-url], [data-link], [data-to], [data-route]"
        ):
            for attr in ["data-href", "data-url", "data-link", "data-to", "data-route"]:
                href = data_link.attributes.get(attr, "").strip()
                if href:
                    self._add_link(href, base_url, links, f"data-{attr}")

        # 4. Form actions
        for form in parser.css("form[action]"):
            action = form.attributes.get("action", "").strip()
            if action:
                self._add_link(action, base_url, links, "form-action")

        # 5. Meta refresh redirects
        for meta in parser.css('meta[http-equiv="refresh"]'):
            content = meta.attributes.get("content", "").strip()
            if "url=" in content.lower():
                url_part = content.lower().split("url=")[1].strip()
                if url_part:
                    self._add_link(url_part, base_url, links, "meta-refresh")

        # 6. Link elements in head
        for link_elem in parser.css("link[href][rel]"):
            rel = link_elem.attributes.get("rel", "").lower()
            # Only follow certain link types that might lead to pages
            if rel in ["canonical", "alternate", "next", "prev"]:
                href = link_elem.attributes.get("href", "").strip()
                if href:
                    self._add_link(href, base_url, links, f"link-{rel}")

        # 7. Onclick handlers with location.href (basic extraction)
        for onclick_elem in parser.css("[onclick]"):
            onclick = onclick_elem.attributes.get("onclick", "").strip()
            if "location.href" in onclick or "window.location" in onclick:
                # Simple regex-like extraction for URLs in onclick
                import re

                url_matches = re.findall(r'["\']([^"\']+)["\']', onclick)
                for match in url_matches:
                    if "/" in match and not match.startswith("javascript:"):
                        self._add_link(match, base_url, links, "onclick-handler")

        # 8. Extract URLs from script tags (JSON, config objects, etc.)
        self._extract_links_from_scripts(parser, base_url, links)

        # 9. Extract links from button and clickable elements
        for button in parser.css(
            "button[data-href], button[data-url], .btn[data-href], .btn[data-url]"
        ):
            for attr in ["data-href", "data-url"]:
                href = button.attributes.get(attr, "").strip()
                if href:
                    self._add_link(href, base_url, links, f"button-{attr}")

        # 10. Extract from image maps
        for area in parser.css("area[href]"):
            href = area.attributes.get("href", "").strip()
            if href:
                self._add_link(href, base_url, links, "image-map")

        # 11. Extract from iframes
        for iframe in parser.css("iframe[src]"):
            src = iframe.attributes.get("src", "").strip()
            if src and not src.startswith("data:"):
                self._add_link(src, base_url, links, "iframe")

        # 12. Extract from embed and object tags
        for embed in parser.css("embed[src], object[data]"):
            src = embed.attributes.get("src") or embed.attributes.get("data", "")
            if src and src.strip():
                self._add_link(src.strip(), base_url, links, "embed-object")

    def _extract_links_from_scripts(
        self, parser: HTMLParser, base_url: str, links: Set[str]
    ) -> None:
        """Extract URLs from JavaScript code and JSON-LD scripts."""
        import json
        import re

        for script in parser.css("script"):
            script_content = script.text()
            if not script_content:
                continue

            script_type = script.attributes.get("type", "").lower()

            # Extract from JSON-LD structured data
            if script_type == "application/ld+json":
                try:
                    json_data = json.loads(script_content)
                    self._extract_urls_from_json(json_data, base_url, links)
                except (json.JSONDecodeError, TypeError):
                    pass

            # Extract URLs from regular JavaScript
            else:
                # Look for URL patterns in JavaScript strings
                url_patterns = [
                    r'["\']([^"\']*(?:\/[^"\']*)+)["\']',  # General URL-like strings
                    r'href\s*:\s*["\']([^"\']+)["\']',  # href properties
                    r'url\s*:\s*["\']([^"\']+)["\']',  # url properties
                    r'path\s*:\s*["\']([^"\']+)["\']',  # path properties
                    r'route\s*:\s*["\']([^"\']+)["\']',  # route properties
                    r'to\s*:\s*["\']([^"\']+)["\']',  # to properties (React Router)
                ]

                for pattern in url_patterns:
                    matches = re.findall(pattern, script_content, re.IGNORECASE)
                    for match in matches:
                        # Filter out obvious non-URLs
                        if (
                            len(match) > 1
                            and "/" in match
                            and not match.startswith(
                                ("javascript:", "data:", "blob:", "#")
                            )
                            and not match.endswith(
                                (
                                    ".js",
                                    ".css",
                                    ".png",
                                    ".jpg",
                                    ".gif",
                                    ".svg",
                                    ".woff",
                                    ".ttf",
                                )
                            )
                        ):
                            self._add_link(match, base_url, links, "javascript-pattern")

    def _extract_urls_from_json(self, data, base_url: str, links: Set[str]) -> None:
        """Recursively extract URLs from JSON data structures."""
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, str):
                    # Look for URL-like values
                    if (
                        key.lower()
                        in [
                            "url",
                            "href",
                            "link",
                            "path",
                            "route",
                            "canonical",
                            "mainentity",
                        ]
                        and isinstance(value, str)
                        and "/" in value
                    ):
                        self._add_link(value, base_url, links, f"json-{key}")
                elif isinstance(value, (dict, list)):
                    self._extract_urls_from_json(value, base_url, links)
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, (dict, list)):
                    self._extract_urls_from_json(item, base_url, links)

    def _add_link(
        self, href: str, base_url: str, links: Set[str], source: str = "unknown"
    ) -> None:
        """Helper method to validate and add a link to the set."""
        if self.debug_links:
            self.debug_info["found_links"].append(f"{href} (from: {source})")

        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            if self.debug_links:
                self.debug_info["filtered_links"].append(
                    f"{href} - invalid or fragment"
                )
            return

        absolute_url = self.url_validator.resolve_relative_url(base_url, href)
        normalized_url = self.url_validator.normalize_url(absolute_url)
        if normalized_url and self.url_validator.is_valid_url(normalized_url):
            links.add(normalized_url)
            if self.debug_links and source not in self.debug_info["sources"]:
                self.debug_info["sources"].append(source)
        elif self.debug_links:
            self.debug_info["filtered_links"].append(f"{href} - failed validation")

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
