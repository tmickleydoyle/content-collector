import pytest

from content_collector.cli.main import main
from content_collector.storage.database import Database
from content_collector.storage.file_storage import FileStorage


@pytest.fixture(scope="module")
def setup_database():
    db = Database()
    db.connect()
    yield db
    db.disconnect()


@pytest.fixture(scope="module")
def setup_file_storage():
    fs = FileStorage()
    fs.setup()
    yield fs
    fs.cleanup()


@pytest.mark.asyncio
async def test_complete_scraping_flow(setup_database, setup_file_storage):
    # Create a test input file first
    import os
    import tempfile

    from content_collector.core.scraper import ScrapingEngine
    from content_collector.storage.database import db_manager

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("url\n")
        f.write("http://httpbin.org/html\n")
        f.write("http://httpbin.org/json\n")
        test_file = f.name

    try:
        # Test the core scraping functionality directly
        from pathlib import Path

        scraper = ScrapingEngine()

        await db_manager.initialize()
        run_id = await scraper.run(Path(test_file), max_pages=None)
        await db_manager.close()

        assert run_id is not None

        # Verify the scraping was successful by checking that we have a run_id
        # This indicates the full flow completed without errors
        assert isinstance(run_id, str)
        assert len(run_id) > 0
    finally:
        # Clean up test file
        if os.path.exists(test_file):
            os.unlink(test_file)
