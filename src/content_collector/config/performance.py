"""Performance optimization configurations for maximum parallelization."""

import multiprocessing
import os
from typing import Any, Dict, Optional

from .constants import DEFAULT_MAX_CONCURRENT_REQUESTS


class PerformanceConfig:
    """Performance configuration for optimizing concurrency."""

    def __init__(self):
        """Initialize performance configuration."""
        self.cpu_count = multiprocessing.cpu_count()
        self.memory_gb = self._get_available_memory_gb()

    def _get_available_memory_gb(self) -> float:
        """Get available system memory in GB."""
        try:
            import psutil

            return psutil.virtual_memory().total / (1024**3)
        except ImportError:
            # Fallback if psutil not available
            return 8.0  # Assume 8GB default

    def get_optimal_concurrency_settings(
        self, mode: str = "balanced", custom_max_workers: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get optimal concurrency settings based on system resources.

        Args:
            mode: Performance mode ("conservative", "balanced", "aggressive", "maximum")
            custom_max_workers: Override for max workers

        Returns:
            Dictionary with optimized settings
        """
        if mode == "conservative":
            return self._get_conservative_settings(custom_max_workers)
        elif mode == "balanced":
            return self._get_balanced_settings(custom_max_workers)
        elif mode == "aggressive":
            return self._get_aggressive_settings(custom_max_workers)
        elif mode == "maximum":
            return self._get_maximum_settings(custom_max_workers)
        else:
            raise ValueError(f"Unknown performance mode: {mode}")

    def _get_conservative_settings(
        self, custom_max_workers: Optional[int]
    ) -> Dict[str, Any]:
        """Conservative settings for stable operation."""
        max_workers = custom_max_workers or min(10, self.cpu_count)

        return {
            "max_workers": max_workers,
            "max_concurrent_requests": max_workers,
            "max_connections": max_workers * 2,
            "max_connections_per_host": 5,
            "fetcher_pool_size": 1,
            "request_timeout": 30,
            "rate_limit_delay": 1.0,
            "enable_dns_cache": True,
            "enable_keepalive": True,
            "batch_size": 10,
            "queue_timeout": 5.0,
            "stats_interval": 60,
        }

    def _get_balanced_settings(
        self, custom_max_workers: Optional[int]
    ) -> Dict[str, Any]:
        """Balanced settings for good performance with stability."""
        max_workers = custom_max_workers or min(20, self.cpu_count * 2)

        return {
            "max_workers": max_workers,
            "max_concurrent_requests": max_workers,
            "max_connections": max_workers * 3,
            "max_connections_per_host": 10,
            "fetcher_pool_size": max(2, max_workers // 10),
            "request_timeout": 30,
            "rate_limit_delay": 0.5,
            "enable_dns_cache": True,
            "enable_keepalive": True,
            "batch_size": 20,
            "queue_timeout": 5.0,
            "stats_interval": 30,
        }

    def _get_aggressive_settings(
        self, custom_max_workers: Optional[int]
    ) -> Dict[str, Any]:
        """Aggressive settings for high performance."""
        max_workers = custom_max_workers or min(50, self.cpu_count * 4)

        return {
            "max_workers": max_workers,
            "max_concurrent_requests": max_workers,
            "max_connections": max_workers * 4,
            "max_connections_per_host": 20,
            "fetcher_pool_size": max(3, max_workers // 8),
            "request_timeout": 20,
            "rate_limit_delay": 0.2,
            "enable_dns_cache": True,
            "enable_keepalive": True,
            "batch_size": 50,
            "queue_timeout": 3.0,
            "stats_interval": 15,
        }

    def _get_maximum_settings(
        self, custom_max_workers: Optional[int]
    ) -> Dict[str, Any]:
        """Maximum performance settings (may be unstable on some systems)."""
        max_workers = custom_max_workers or min(100, self.cpu_count * 8)

        return {
            "max_workers": max_workers,
            "max_concurrent_requests": max_workers,
            "max_connections": max_workers * 5,
            "max_connections_per_host": 50,
            "fetcher_pool_size": max(5, max_workers // 6),
            "request_timeout": 15,
            "rate_limit_delay": 0.1,
            "enable_dns_cache": True,
            "enable_keepalive": True,
            "batch_size": 100,
            "queue_timeout": 2.0,
            "stats_interval": 10,
        }

    def get_system_info(self) -> Dict[str, Any]:
        """Get system information for performance tuning."""
        return {
            "cpu_count": self.cpu_count,
            "memory_gb": self.memory_gb,
            "platform": os.name,
            "recommended_max_workers": min(50, self.cpu_count * 3),
            "recommended_connections": min(200, self.cpu_count * 10),
        }

    def validate_settings(self, settings: Dict[str, Any]) -> Dict[str, str]:
        """
        Validate performance settings and return warnings.

        Args:
            settings: Performance settings to validate

        Returns:
            Dictionary of validation warnings
        """
        warnings = {}

        max_workers = settings.get("max_workers", 0)
        max_connections = settings.get("max_connections", 0)

        # Check if settings are too aggressive for the system
        if max_workers > self.cpu_count * 10:
            warnings["max_workers"] = (
                f"Very high worker count ({max_workers}) for {self.cpu_count} CPUs"
            )

        if max_connections > 1000:
            warnings["max_connections"] = (
                f"Very high connection count ({max_connections}) may hit system limits"
            )

        if self.memory_gb < 4 and max_workers > 20:
            warnings["memory"] = (
                f"Low memory ({self.memory_gb:.1f}GB) for {max_workers} workers"
            )

        # Check rate limiting
        rate_limit = settings.get("rate_limit_delay", 1.0)
        if rate_limit < 0.05:
            warnings["rate_limit"] = (
                f"Very low rate limit ({rate_limit}s) may cause server blocking"
            )

        return warnings


# Global performance configuration instance
performance_config = PerformanceConfig()


def get_performance_settings(
    mode: str = "balanced", custom_max_workers: Optional[int] = None
) -> Dict[str, Any]:
    """
    Get performance settings for the specified mode.

    Args:
        mode: Performance mode
        custom_max_workers: Custom max workers override

    Returns:
        Performance settings dictionary
    """
    return performance_config.get_optimal_concurrency_settings(mode, custom_max_workers)


def validate_performance_settings(settings: Dict[str, Any]) -> Dict[str, str]:
    """Validate performance settings."""
    return performance_config.validate_settings(settings)


def get_system_recommendations() -> Dict[str, Any]:
    """Get system-specific performance recommendations."""
    return performance_config.get_system_info()


# Environment variable overrides
def apply_env_overrides(settings: Dict[str, Any]) -> Dict[str, Any]:
    """Apply environment variable overrides to settings."""
    env_mappings = {
        "MAX_WORKERS": "max_workers",
        "MAX_CONCURRENT_REQUESTS": "max_concurrent_requests",
        "MAX_CONNECTIONS": "max_connections",
        "MAX_CONNECTIONS_PER_HOST": "max_connections_per_host",
        "REQUEST_TIMEOUT": "request_timeout",
        "RATE_LIMIT_DELAY": "rate_limit_delay",
        "FETCHER_POOL_SIZE": "fetcher_pool_size",
    }

    for env_var, setting_key in env_mappings.items():
        env_value = os.getenv(env_var)
        if env_value is not None:
            try:
                if setting_key in ["rate_limit_delay", "request_timeout"]:
                    settings[setting_key] = float(env_value)
                else:
                    settings[setting_key] = int(env_value)
            except ValueError:
                pass  # Ignore invalid environment values

    return settings
