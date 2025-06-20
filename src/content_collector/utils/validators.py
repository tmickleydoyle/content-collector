"""URL validation and processing utilities."""

from typing import List, Optional
from urllib.parse import urljoin, urlparse, urlunparse
import structlog

logger = structlog.get_logger()


class URLValidator:
    """Validates and normalizes URLs."""
    
    def __init__(self) -> None:
        """Initialize URL validator."""
        self.logger = logger.bind(component="url_validator")
        
        # Common file extensions to exclude
        self.excluded_extensions = {
            '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
            '.zip', '.rar', '.tar', '.gz', '.7z',
            '.mp3', '.wav', '.mp4', '.avi', '.mov', '.wmv',
            '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg',
            '.exe', '.msi', '.dmg', '.deb', '.rpm'
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
        
        url = url.strip()
        if not url:
            return False
        
        try:
            parsed = urlparse(url)
            
            # Must have http or https scheme
            if parsed.scheme not in ('http', 'https'):
                return False
            
            # Must have a valid netloc (domain)
            if not parsed.netloc:
                return False
            
            # Exclude localhost and IP addresses
            if self._is_local_or_ip(parsed.netloc):
                return False
            
            # Check for excluded file extensions
            if self._has_excluded_extension(url):
                return False
            
            # Check for non-HTML content patterns
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
            
            # Normalize path by resolving .. and .
            path = parsed.path
            if not path or path == "":
                path = "/"
            else:
                # Simple path normalization for .. patterns
                parts = path.split('/')
                normalized_parts = []
                for part in parts:
                    if part == '..':
                        if normalized_parts and normalized_parts[-1] != '..':
                            normalized_parts.pop()
                    elif part and part != '.':
                        normalized_parts.append(part)
                path = '/' + '/'.join(normalized_parts)
                if not path.endswith('/') and url.endswith('/'):
                    path += '/'
            
            # Rebuild URL with normalized components
            normalized = urlunparse((
                parsed.scheme.lower(),
                parsed.netloc.lower(),
                path,
                parsed.params,
                parsed.query,
                ""  # Remove fragment
            ))
            
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
    
    def _is_local_or_ip(self, netloc: str) -> bool:
        """Check if netloc is localhost or IP address."""
        netloc_lower = netloc.lower()
        
        # Check for localhost variations
        localhost_patterns = [
            'localhost', '127.0.0.1', '0.0.0.0', '::1',
            'local.', '.local'
        ]
        if any(pattern in netloc_lower for pattern in localhost_patterns):
            return True
        
        # Simple IP address pattern check
        parts = netloc.split(':')[0].split('.')
        if len(parts) == 4:
            try:
                all(0 <= int(part) <= 255 for part in parts)
                return True
            except ValueError:
                pass
        
        return False
    
    def _has_excluded_extension(self, url: str) -> bool:
        """Check if URL has excluded file extension."""
        try:
            parsed = urlparse(url)
            path = parsed.path.lower()
            
            for ext in self.excluded_extensions:
                if path.endswith(ext):
                    return True
            
        except Exception:
            pass
        
        return False
    
    def _is_non_html_resource(self, url: str) -> bool:
        """Check if URL points to non-HTML resource."""
        url_lower = url.lower()
        
        # Check for API endpoints in domain or path
        api_patterns = [
            '/api/', '/rest/', '/graphql', '/rpc/',
            '.json', '.xml', '.csv', '.rss', '.atom',
            'api.', 'rest.', 'graphql.'  # API subdomains
        ]
        if any(pattern in url_lower for pattern in api_patterns):
            return True
        
        # Check for common non-HTML patterns
        non_html_patterns = [
            'mailto:', 'tel:', 'ftp:', 'javascript:',
            '/download/', '/file/', '/asset/'
        ]
        if any(pattern in url_lower for pattern in non_html_patterns):
            return True
        
        return False
