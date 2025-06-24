"""Base classes for common functionality."""

import asyncio
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

import structlog
from structlog.typing import FilteringBoundLogger

from .config.settings import settings
from .exceptions import ContentCollectorError


class BaseComponent(ABC):
    """Base class for all application components."""

    def __init__(self, component_name: str):
        """Initialize base component with logging."""
        self.component_name = component_name
        self.logger: FilteringBoundLogger = structlog.get_logger().bind(
            component=component_name
        )

    def log_operation(self, operation: str, **kwargs: Any) -> None:
        """Log an operation with consistent formatting."""
        self.logger.info(f"{operation} started", **kwargs)

    def log_success(self, operation: str, **kwargs: Any) -> None:
        """Log successful operation."""
        self.logger.info(f"{operation} completed successfully", **kwargs)

    def log_error(self, operation: str, error: Exception, **kwargs: Any) -> None:
        """Log error with consistent formatting."""
        self.logger.error(
            f"{operation} failed",
            error=str(error),
            error_type=type(error).__name__,
            **kwargs,
        )


class BaseAsyncComponent(BaseComponent):
    """Base class for async components with lifecycle management."""

    def __init__(self, component_name: str):
        """Initialize async component."""
        super().__init__(component_name)
        self._initialized = False
        self._closed = False

    async def __aenter__(self) -> "BaseAsyncComponent":
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()

    async def initialize(self) -> None:
        """Initialize the component."""
        if self._initialized:
            return

        try:
            await self._initialize()
            self._initialized = True
            self.log_success("initialization")
        except Exception as e:
            self.log_error("initialization", e)
            raise

    async def close(self) -> None:
        """Close the component and clean up resources."""
        if self._closed or not self._initialized:
            return

        try:
            await self._close()
            self._closed = True
            self.log_success("cleanup")
        except Exception as e:
            self.log_error("cleanup", e)
            raise

    @abstractmethod
    async def _initialize(self) -> None:
        """Component-specific initialization logic."""
        pass

    @abstractmethod
    async def _close(self) -> None:
        """Component-specific cleanup logic."""
        pass


class BaseValidator(BaseComponent):
    """Base class for validators."""

    def __init__(self, component_name: str):
        """Initialize validator."""
        super().__init__(component_name)

    @abstractmethod
    def validate(self, value: Any) -> bool:
        """Validate a value."""
        pass

    def validate_with_error(self, value: Any, context: str = "") -> None:
        """Validate and raise specific error on failure."""
        if not self.validate(value):
            error_msg = f"Validation failed for {context}: {value}"
            self.log_error("validation", ContentCollectorError(error_msg))
            raise ContentCollectorError(error_msg)


class BaseProcessor(BaseComponent):
    """Base class for data processors."""

    def __init__(self, component_name: str):
        """Initialize processor."""
        super().__init__(component_name)
        self.processed_count = 0
        self.error_count = 0

    def reset_stats(self) -> None:
        """Reset processing statistics."""
        self.processed_count = 0
        self.error_count = 0

    def get_stats(self) -> Dict[str, int | float]:
        """Get processing statistics."""
        return {
            "processed": self.processed_count,
            "errors": self.error_count,
            "success_rate": (
                (self.processed_count - self.error_count) / self.processed_count * 100
                if self.processed_count > 0
                else 0
            ),
        }

    @abstractmethod
    async def process(self, data: Any) -> Any:
        """Process data."""
        pass


class BaseFetcher(BaseAsyncComponent):
    """Base class for fetchers with common functionality."""

    def __init__(self, component_name: str):
        """Initialize fetcher."""
        super().__init__(component_name)
        self.request_count = 0
        self.success_count = 0
        self.error_count = 0

    def reset_stats(self) -> None:
        """Reset request statistics."""
        self.request_count = 0
        self.success_count = 0
        self.error_count = 0

    def get_stats(self) -> Dict[str, int | float]:
        """Get request statistics."""
        return {
            "total_requests": self.request_count,
            "successful_requests": self.success_count,
            "failed_requests": self.error_count,
            "success_rate": (
                self.success_count / self.request_count * 100
                if self.request_count > 0
                else 0
            ),
        }

    async def fetch_with_retry(
        self,
        url: str,
        max_retries: Optional[int] = None,
        retry_delay: Optional[float] = None,
    ) -> Any:
        """Fetch with exponential backoff retry logic."""
        max_retries = max_retries or settings.scraping.max_retries
        retry_delay = retry_delay or settings.scraping.retry_delay

        last_exception: Exception | None = None

        for attempt in range(max_retries + 1):
            try:
                self.request_count += 1
                result = await self._fetch(url)
                self.success_count += 1

                if attempt > 0:
                    self.logger.info(
                        "Retry successful",
                        url=url,
                        attempt=attempt,
                        max_retries=max_retries,
                    )

                return result

            except Exception as e:
                last_exception = e
                self.error_count += 1

                if attempt < max_retries:
                    wait_time = retry_delay * (2**attempt)
                    self.logger.warning(
                        "Fetch failed, retrying",
                        url=url,
                        attempt=attempt,
                        max_retries=max_retries,
                        wait_time=wait_time,
                        error=str(e),
                    )
                    await asyncio.sleep(wait_time)
                else:
                    self.logger.error(
                        "All retry attempts failed",
                        url=url,
                        max_retries=max_retries,
                        error=str(e),
                    )

        if last_exception is None:
            raise RuntimeError("Unexpected state: no exception but all retries failed")

        raise last_exception

    @abstractmethod
    async def _fetch(self, url: str) -> Any:
        """Fetch implementation to be overridden."""
        pass


class BaseStorage(BaseAsyncComponent):
    """Base class for storage components."""

    def __init__(self, component_name: str):
        """Initialize storage component."""
        super().__init__(component_name)
        self.storage_stats = {
            "items_stored": 0,
            "items_retrieved": 0,
            "storage_errors": 0,
            "retrieval_errors": 0,
        }

    def get_storage_stats(self) -> Dict[str, int]:
        """Get storage statistics."""
        return self.storage_stats.copy()

    async def store_with_validation(self, key: str, data: Any) -> None:
        """Store data with validation."""
        try:
            self._validate_storage_data(data)
            await self._store(key, data)
            self.storage_stats["items_stored"] += 1
            self.log_success("storage", key=key)
        except Exception as e:
            self.storage_stats["storage_errors"] += 1
            self.log_error("storage", e, key=key)
            raise

    async def retrieve_with_validation(self, key: str) -> Any:
        """Retrieve data with validation."""
        try:
            data = await self._retrieve(key)
            self.storage_stats["items_retrieved"] += 1
            self.log_success("retrieval", key=key)
            return data
        except Exception as e:
            self.storage_stats["retrieval_errors"] += 1
            self.log_error("retrieval", e, key=key)
            raise

    def _validate_storage_data(self, data: Any) -> None:
        """Validate data before storage."""
        if data is None:
            raise ValueError("Cannot store None data")

    @abstractmethod
    async def _store(self, key: str, data: Any) -> None:
        """Storage implementation to be overridden."""
        pass

    @abstractmethod
    async def _retrieve(self, key: str) -> Any:
        """Retrieval implementation to be overridden."""
        pass
