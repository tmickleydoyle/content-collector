"""Enhanced HTML parser with JavaScript-aware link extraction."""

import re
from typing import Dict, List, Set
from urllib.parse import urljoin, urlparse

import structlog
from selectolax.parser import HTMLParser

from .parser import ContentParser

logger = structlog.get_logger()


class JavaScriptAwareParser(ContentParser):
    """Enhanced parser that can extract links from JavaScript and data attributes."""

    def _extract_additional_links(
        self, parser: HTMLParser, base_url: str, links: Set[str]
    ) -> None:
        """Enhanced link extraction for JavaScript-heavy sites."""
        # Call parent method first
        super()._extract_additional_links(parser, base_url, links)

        # Extract from script tags
        self._extract_from_scripts(parser, base_url, links)

        # Extract from data attributes
        self._extract_from_data_attributes(parser, base_url, links)

        # Extract from CSS selectors that might contain URLs
        self._extract_from_css_attributes(parser, base_url, links)

    def _extract_from_scripts(
        self, parser: HTMLParser, base_url: str, links: Set[str]
    ) -> None:
        """Extract URLs from JavaScript code in script tags."""
        for script in parser.css("script"):
            script_content = script.text()
            if not script_content:
                continue

            # Look for common URL patterns in JavaScript
            url_patterns = [
                r'["\']https?://[^"\']+["\']',  # Full URLs in quotes
                r'["\']\/[^"\']*["\']',  # Relative URLs starting with /
                r'href\s*:\s*["\']([^"\']+)["\']',  # href properties
                r'url\s*:\s*["\']([^"\']+)["\']',  # url properties
                r'location\.href\s*=\s*["\']([^"\']+)["\']',  # location.href assignments
                r'window\.location\s*=\s*["\']([^"\']+)["\']',  # window.location assignments
            ]

            for pattern in url_patterns:
                matches = re.findall(pattern, script_content, re.IGNORECASE)
                for match in matches:
                    # Handle both tuple and string results from regex
                    url = match[0] if isinstance(match, tuple) else match
                    # Clean quotes
                    url = url.strip("'\"")
                    if url and not url.startswith(("javascript:", "data:", "#")):
                        self._add_link(url, base_url, links)

    def _extract_from_data_attributes(
        self, parser: HTMLParser, base_url: str, links: Set[str]
    ) -> None:
        """Extract URLs from various data attributes."""
        data_attributes = [
            "data-href",
            "data-url",
            "data-link",
            "data-target",
            "data-path",
            "data-route",
            "data-navigate",
            "data-goto",
            "data-redirect",
            "data-src",
            "data-original",
            "data-lazy",
        ]

        for attr in data_attributes:
            for elem in parser.css(f"[{attr}]"):
                url = elem.attributes.get(attr, "").strip()
                if url and not url.startswith(("#", "javascript:", "data:")):
                    self._add_link(url, base_url, links)

    def _extract_from_css_attributes(
        self, parser: HTMLParser, base_url: str, links: Set[str]
    ) -> None:
        """Extract URLs from CSS-related attributes."""
        # Look for elements with CSS that might contain URLs
        for elem in parser.css("[style]"):
            style = elem.attributes.get("style", "")
            # Look for url() in CSS
            css_urls = re.findall(r'url\(["\']?([^"\')]+)["\']?\)', style)
            for url in css_urls:
                if url and not url.startswith(("data:", "#")):
                    self._add_link(url, base_url, links)

    def _extract_sitemap_and_robots_links(self, base_url: str) -> List[str]:
        """Generate common sitemap and robots.txt URLs."""
        parsed_url = urlparse(base_url)
        base = f"{parsed_url.scheme}://{parsed_url.netloc}"

        return [
            f"{base}/sitemap.xml",
            f"{base}/sitemap_index.xml",
            f"{base}/robots.txt",
            f"{base}/rss.xml",
            f"{base}/feed.xml",
            f"{base}/atom.xml",
        ]

    def parse_html_enhanced(self, content: str, base_url: str) -> Dict:
        """Enhanced parsing with additional link discovery."""
        result = self.parse_html(content, base_url)

        # Add sitemap and common URLs
        additional_links = self._extract_sitemap_and_robots_links(base_url)

        # Combine and deduplicate links
        all_links = list(set(result["links"] + additional_links))
        result["links"] = all_links
        result["link_count"] = len(all_links)

        self.logger.debug(
            "Enhanced parsing completed",
            original_links=len(result["links"]) - len(additional_links),
            additional_links=len(additional_links),
            total_links=len(all_links),
        )

        return result
