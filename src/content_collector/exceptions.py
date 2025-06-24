"""Custom exceptions for the content collector."""


class ContentCollectorError(Exception):
    """Base exception for all content collector errors."""

    pass


class ConfigurationError(ContentCollectorError):
    """Raised when there's a configuration problem."""

    pass


class DatabaseError(ContentCollectorError):
    """Raised when there's a database-related error."""

    pass


class DatabaseConnectionError(DatabaseError):
    """Raised when database connection fails."""

    pass


class DatabaseMigrationError(DatabaseError):
    """Raised when database migration fails."""

    pass


class FetchError(ContentCollectorError):
    """Base class for fetching errors."""

    def __init__(self, url: str, message: str, status_code: int | None = None):
        """Initialize fetch error with URL context."""
        self.url = url
        self.status_code = status_code
        super().__init__(f"Error fetching {url}: {message}")


class NetworkError(FetchError):
    """Raised when network request fails."""

    pass


class HTTPError(FetchError):
    """Raised when HTTP request returns an error status."""

    pass


class TimeoutError(FetchError):
    """Raised when request times out."""

    pass


class ParsingError(ContentCollectorError):
    """Raised when content parsing fails."""

    def __init__(self, url: str, message: str):
        """Initialize parsing error with URL context."""
        self.url = url
        super().__init__(f"Error parsing content from {url}: {message}")


class ValidationError(ContentCollectorError):
    """Raised when input validation fails."""

    pass


class URLValidationError(ValidationError):
    """Raised when URL validation fails."""

    def __init__(self, url: str, reason: str):
        """Initialize URL validation error."""
        self.url = url
        self.reason = reason
        super().__init__(f"Invalid URL '{url}': {reason}")


class InputProcessingError(ContentCollectorError):
    """Raised when input file processing fails."""

    pass


class FileNotFoundError(InputProcessingError):
    """Raised when input file is not found."""

    pass


class InvalidInputFormatError(InputProcessingError):
    """Raised when input file format is invalid."""

    pass


class StorageError(ContentCollectorError):
    """Raised when file storage operations fail."""

    pass


class InsufficientSpaceError(StorageError):
    """Raised when there's insufficient disk space."""

    pass


class PermissionError(StorageError):
    """Raised when file permissions are insufficient."""

    pass


class ScrapingError(ContentCollectorError):
    """Base class for scraping-related errors."""

    pass


class RateLimitError(ScrapingError):
    """Raised when rate limit is exceeded."""

    def __init__(
        self,
        domain: str,
        retry_after: int | None = None,
        status_code: int | None = None,
    ):
        """Initialize rate limit error."""
        self.domain = domain
        self.retry_after = retry_after
        self.status_code = status_code
        message = f"Rate limit exceeded for domain {domain}"
        if retry_after:
            message += f", retry after {retry_after} seconds"
        if status_code:
            message += f" (HTTP {status_code})"
        super().__init__(message)


class RobotsBlockedError(ScrapingError):
    """Raised when robots.txt blocks scraping."""

    def __init__(self, url: str):
        """Initialize robots blocked error."""
        self.url = url
        super().__init__(f"URL blocked by robots.txt: {url}")


class MaxDepthExceededError(ScrapingError):
    """Raised when maximum crawling depth is exceeded."""

    def __init__(self, current_depth: int, max_depth: int):
        """Initialize max depth error."""
        self.current_depth = current_depth
        self.max_depth = max_depth
        super().__init__(
            f"Maximum depth {max_depth} exceeded (current: {current_depth})"
        )
