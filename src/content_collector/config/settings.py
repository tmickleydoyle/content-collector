"""Configuration management for content collector."""

import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class DatabaseSettings(BaseSettings):
    """Database configuration."""

    host: str = Field(default="localhost", env="DB_HOST")
    port: int = Field(default=5432, env="DB_PORT")
    name: str = Field(default="content_collector", env="DB_NAME")
    user: str = Field(default="postgres", env="DB_USER")
    password: str = Field(default="", env="DB_PASSWORD")
    url_override: Optional[str] = Field(default=None, env="DATABASE_URL")

    @property
    def url(self) -> str:
        """Get database URL."""
        if self.url_override:
            return self.url_override
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


class ScrapingSettings(BaseSettings):
    """Scraping configuration."""

    max_concurrent_requests: int = Field(default=10, env="MAX_CONCURRENT_REQUESTS")
    request_timeout: int = Field(default=30, env="REQUEST_TIMEOUT")
    max_retries: int = Field(default=3, env="MAX_RETRIES")
    retry_delay: float = Field(default=1.0, env="RETRY_DELAY")
    max_depth: int = Field(default=3, env="MAX_DEPTH")
    rate_limit_delay: float = Field(default=1.0, env="RATE_LIMIT_DELAY")
    user_agent: str = Field(default="ContentCollector/0.1.0", env="USER_AGENT")
    enable_loop_prevention: bool = Field(default=True, env="ENABLE_LOOP_PREVENTION")
    enable_pattern_detection: bool = Field(default=True, env="ENABLE_PATTERN_DETECTION")
    allow_cross_domain: bool = Field(default=False, env="ALLOW_CROSS_DOMAIN")


class LoggingSettings(BaseSettings):
    """Logging configuration."""

    level: str = Field(default="INFO", env="LOGGING_LEVEL")
    format: str = Field(default="json", env="LOGGING_FORMAT")


class StorageSettings(BaseSettings):
    """Storage configuration."""

    content_dir: Path = Field(default=Path("data/content"), env="CONTENT_DIR")
    reports_dir: Path = Field(default=Path("data/reports"), env="REPORTS_DIR")

    def model_post_init(self, __context) -> None:
        """Create directories if they don't exist."""
        self.content_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)


class Settings(BaseSettings):
    """Main application settings."""

    debug: bool = Field(default=False, env="DEBUG")
    environment: str = Field(default="development", env="ENVIRONMENT")
    log_level: str = Field(default="INFO", env="LOG_LEVEL")

    database: DatabaseSettings = DatabaseSettings()
    scraping: ScrapingSettings = ScrapingSettings()
    storage: StorageSettings = StorageSettings()
    logging: LoggingSettings = LoggingSettings()

    model_config = {"env_file": ".env", "env_nested_delimiter": "__"}


settings = Settings()
