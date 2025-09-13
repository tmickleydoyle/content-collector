"""URL validation and processing utilities."""

from typing import Optional
from urllib.parse import urljoin, urlparse, urlunparse

import structlog

logger = structlog.get_logger()


class URLValidator:
    """Validates and normalizes URLs."""

    def __init__(self) -> None:
        """Initialize URL validator."""
        self.logger = logger.bind(component="url_validator")

        self.excluded_extensions = {
            ".pdf",
            ".doc",
            ".docx",
            ".xls",
            ".xlsx",
            ".ppt",
            ".pptx",
            ".zip",
            ".rar",
            ".tar",
            ".tar.gz",
            ".tar.xz",
            ".tar.bz2",
            ".tgz",
            ".txz",
            ".tbz2",
            ".gz",
            ".xz",
            ".bz2",
            ".7z",
            ".mp3",
            ".wav",
            ".mp4",
            ".avi",
            ".mov",
            ".wmv",
            ".jpg",
            ".jpeg",
            ".png",
            ".gif",
            ".bmp",
            ".svg",
            ".exe",
            ".msi",
            ".dmg",
            ".deb",
            ".rpm",
            ".pkg",
        }

    def is_valid_url(self, url: str) -> bool:
        """
        Validate if URL is suitable for content extraction.

        Args:
            url: URL to validate

        Returns:
            True if URL is valid for scraping
        """
        if not url or not isinstance(url, str):
            return False

        if url != url.strip():
            return False

        if not url:
            return False

        try:
            parsed = urlparse(url)

            if parsed.scheme not in ("http", "https"):
                return False

            if not parsed.netloc:
                return False

            if self._is_local_or_ip_address(parsed.netloc):
                return False

            if self._has_excluded_extension(url):
                return False

            if self._is_non_html_resource(url):
                return False

            return True

        except Exception as e:
            self.logger.debug("URL validation error", url=url, error=str(e))
            return False

    def normalize_url(self, url: str) -> str:
        """
        Normalize URL for consistent processing.

        Args:
            url: URL to normalize

        Returns:
            Normalized URL
        """
        try:
            parsed = urlparse(url.strip())

            path = parsed.path
            if not path or path == "":
                path = "/"
            else:
                parts = path.split("/")
                normalized_parts = []
                for part in parts:
                    if part == "..":
                        if normalized_parts and normalized_parts[-1] != "..":
                            normalized_parts.pop()
                    elif part and part != ".":
                        normalized_parts.append(part)
                path = "/" + "/".join(normalized_parts)
                if not path.endswith("/") and url.endswith("/"):
                    path += "/"

            normalized = urlunparse(
                (
                    parsed.scheme.lower(),
                    parsed.netloc.lower(),
                    path,
                    parsed.params,
                    parsed.query,
                    "",
                )
            )

            return normalized

        except Exception:
            return url

    def resolve_relative_url(self, base_url: str, relative_url: str) -> str:
        """
        Resolve relative URL against base URL.

        Args:
            base_url: Base URL for resolution
            relative_url: Relative URL to resolve

        Returns:
            Absolute URL
        """
        try:
            return urljoin(base_url, relative_url)
        except Exception:
            return relative_url

    def extract_domain(self, url: str) -> Optional[str]:
        """
        Extract domain from URL.

        Args:
            url: URL to extract domain from

        Returns:
            Domain name or None if invalid
        """
        try:
            parsed = urlparse(url)
            return parsed.netloc.lower() if parsed.netloc else None
        except Exception:
            return None

    def is_same_domain(self, url1: str, url2: str) -> bool:
        """
        Check if two URLs are from the same domain.

        Args:
            url1: First URL
            url2: Second URL

        Returns:
            True if both URLs are from the same domain, False otherwise
        """
        domain1 = self.extract_domain(url1)
        domain2 = self.extract_domain(url2)

        if not domain1 or not domain2:
            return False

        # Treat exact domain or subdomain relationships as same domain
        if domain1 == domain2:
            return True
        # Allow subdomains (e.g., api.example.com vs example.com)
        if domain2.endswith(f".{domain1}") or domain1.endswith(f".{domain2}"):
            return True
        return False

    def _is_local_or_ip_address(self, url_or_netloc: str) -> bool:
        """Check if URL or netloc is localhost or IP address."""
        if url_or_netloc.startswith(("http://", "https://")):
            try:
                parsed = urlparse(url_or_netloc)
                netloc = parsed.netloc
            except Exception:
                return False
        else:
            netloc = url_or_netloc

        netloc_lower = netloc.lower()

        localhost_patterns = [
            "localhost",
            "127.0.0.1",
            "0.0.0.0",
            "::1",
            "local.",
            ".local",
        ]
        if any(pattern in netloc_lower for pattern in localhost_patterns):
            return True

        parts = netloc.split(":")[0].split(".")
        if len(parts) == 4:
            try:
                ip_parts = [int(part) for part in parts]
                if all(0 <= part <= 255 for part in ip_parts):
                    if (
                        ip_parts[0] == 10
                        or (ip_parts[0] == 172 and 16 <= ip_parts[1] <= 31)
                        or (ip_parts[0] == 192 and ip_parts[1] == 168)
                        or ip_parts[0] == 127
                    ):
                        return True
            except ValueError:
                pass

        return False

    def _has_excluded_extension(self, url: str) -> bool:
        """Check if URL has excluded file extension."""
        try:
            parsed = urlparse(url)
            path = parsed.path.lower()

            # Sort extensions by length (longest first) to match compound extensions first
            sorted_extensions = sorted(self.excluded_extensions, key=len, reverse=True)

            for ext in sorted_extensions:
                if path.endswith(ext):
                    self.logger.debug(
                        "URL excluded due to extension", url=url, extension=ext
                    )
                    return True

        except Exception:
            pass

        return False

    def _is_non_html_resource(self, url: str) -> bool:
        """Check if URL points to non-HTML resource."""
        url_lower = url.lower()

        api_patterns = [
            "/api/",
            "/rest/",
            "/graphql",
            "/rpc/",
            ".json",
            ".xml",
            ".csv",
            ".rss",
            ".atom",
            "api.",
            "rest.",
            "graphql.",
        ]
        if any(pattern in url_lower for pattern in api_patterns):
            return True

        non_html_patterns = [
            "mailto:",
            "tel:",
            "ftp:",
            "javascript:",
            "/download/",
            "/file/",
            "/asset/",
        ]
        if any(pattern in url_lower for pattern in non_html_patterns):
            return True

        return False
