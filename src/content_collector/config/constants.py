"""Application constants and configuration values."""

from enum import Enum
from typing import Final

APP_NAME: Final[str] = "content-collector"
APP_VERSION: Final[str] = "0.1.0"
APP_DESCRIPTION: Final[str] = "Scalable web scraping application with lineage tracking"

DEFAULT_USER_AGENT: Final[str] = f"{APP_NAME}/{APP_VERSION}"
DEFAULT_REQUEST_TIMEOUT: Final[int] = 30
DEFAULT_MAX_RETRIES: Final[int] = 3
DEFAULT_RETRY_DELAY: Final[float] = 1.0
DEFAULT_MAX_DEPTH: Final[int] = 3
DEFAULT_MAX_PAGES: Final[int] = 100
DEFAULT_RATE_LIMIT_DELAY: Final[float] = 1.0
DEFAULT_MAX_CONCURRENT_REQUESTS: Final[int] = 10

DEFAULT_BURST_REQUESTS: Final[int] = 5
DEFAULT_ADAPTIVE_RATE_LIMIT: Final[bool] = True
DEFAULT_MIN_RATE_LIMIT_DELAY: Final[float] = 0.5
DEFAULT_MAX_RATE_LIMIT_DELAY: Final[float] = 5.0
DEFAULT_RATE_LIMIT_BACKOFF_FACTOR: Final[float] = 1.5

DEFAULT_ENABLE_LOOP_PREVENTION: Final[bool] = True
DEFAULT_MAX_PATH_LENGTH: Final[int] = 50
DEFAULT_MAX_REPEATED_SEGMENTS: Final[int] = 2
DEFAULT_ENABLE_PATTERN_DETECTION: Final[bool] = True

CLI_DEFAULTS: Final[dict] = {
    "max_depth": DEFAULT_MAX_DEPTH,
    "max_pages": DEFAULT_MAX_PAGES,
    "create_db": True,
    "verbose": False,
    "allow_cross_domain": False,
}

ALLOWED_EXTENSIONS: Final[tuple] = (".html", ".htm", ".php", ".asp", ".aspx", ".jsp")
EXCLUDED_EXTENSIONS: Final[tuple] = (
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
    ".gz",
    ".7z",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".bmp",
    ".svg",
    ".webp",
    ".mp3",
    ".mp4",
    ".avi",
    ".mov",
    ".wmv",
    ".flv",
    ".css",
    ".js",
    ".json",
    ".xml",
    ".rss",
)


class HTTPStatus(Enum):
    """HTTP status code constants."""

    SUCCESS_START = 200
    SUCCESS_END = 299
    REDIRECT_START = 300
    REDIRECT_END = 399
    CLIENT_ERROR_START = 400
    CLIENT_ERROR_END = 499
    SERVER_ERROR_START = 500
    SERVER_ERROR_END = 599


DB_POOL_SIZE: Final[int] = 20
DB_MAX_OVERFLOW: Final[int] = 0
DB_TIMEOUT: Final[int] = 30


class LogLevel(Enum):
    """Log level constants."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


MAX_CONTENT_SIZE: Final[int] = 10 * 1024 * 1024
MAX_URL_LENGTH: Final[int] = 2048
MAX_TITLE_LENGTH: Final[int] = 500
MAX_DESCRIPTION_LENGTH: Final[int] = 1000

CONTENT_FILE_TYPES: Final[tuple] = ("html", "text", "json", "markdown")
CLEANUP_DAYS_DEFAULT: Final[int] = 30
