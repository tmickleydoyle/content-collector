"""
Pytest configuration file for content collector tests.

This file configures pytest with common settings and fixtures
for unit, integration, and end-to-end tests.
"""

import asyncio
import shutil
import tempfile
from pathlib import Path
from typing import AsyncGenerator, Generator

import pytest

TEST_DATABASE_URL = "sqlite:///test_content_collector.db"


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for test files."""
    temp_path = Path(tempfile.mkdtemp())
    yield temp_path
    shutil.rmtree(temp_path, ignore_errors=True)


@pytest.fixture
async def test_db_manager():
    """Initialize a test database manager."""
    from content_collector.storage.database import DatabaseManager

    db_manager = DatabaseManager()
    db_manager.database_url = TEST_DATABASE_URL

    try:
        await db_manager.initialize()
        await db_manager.create_tables()
        yield db_manager
    finally:
        await db_manager.close()
        db_file = Path("test_content_collector.db")
        if db_file.exists():
            db_file.unlink()


@pytest.fixture
def sample_csv_data() -> str:
    """Sample CSV data for testing."""
    return """url,priority,category
https://example.com,1,test
https://httpbin.org/html,2,sample
https://httpbin.org/json,3,api"""


@pytest.fixture
def sample_input_file(temp_dir: Path, sample_csv_data: str) -> Path:
    """Create a sample input file with CSV paths."""
    csv_file = temp_dir / "test_urls.csv"
    csv_file.write_text(sample_csv_data)

    input_file = temp_dir / "input.txt"
    input_file.write_text(str(csv_file))

    return input_file


@pytest.fixture
def mock_html_content() -> str:
    """Sample HTML content for testing."""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Test Page</title>
        <meta name="description" content="Test page description">
    </head>
    <body>
        <h1>Test Header</h1>
        <p>This is test content.</p>
        <a href="https://example.com/page1">Link 1</a>
        <a href="/relative-link">Relative Link</a>
    </body>
    </html>
    """


pytest_plugins = []

asyncio_mode = "auto"

markers = [
    "unit: Unit tests that test individual components in isolation",
    "integration: Integration tests that test component interactions",
    "e2e: End-to-end tests that test the full application workflow",
    "slow: Tests that take more than 5 seconds to run",
    "network: Tests that require network access",
]

addopts = [
    "--strict-markers",
    "--strict-config",
    "--cov=src/content_collector",
    "--cov-report=html",
    "--cov-report=term-missing",
    "--cov-fail-under=90",
    "-ra",
]

testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]

filterwarnings = [
    "ignore::DeprecationWarning",
    "ignore::PendingDeprecationWarning",
]
