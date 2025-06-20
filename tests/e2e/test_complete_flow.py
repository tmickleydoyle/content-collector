import pytest
import asyncio
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
    # Step 1: Initialize the CLI command
    args = ["run", "--input", "test_urls.txt", "--output", "output_directory"]
    result = await main(args)

    # Step 2: Check if the command executed successfully
    assert result == 0  # Assuming 0 indicates success

    # Step 3: Verify that data has been stored in the database
    pages = setup_database.fetch_all_pages()
    assert len(pages) > 0  # Ensure at least one page was scraped

    # Step 4: Verify that files have been saved in the file storage
    for page in pages:
        assert setup_file_storage.file_exists(page.header_path)
        assert setup_file_storage.file_exists(page.body_path)
        assert setup_file_storage.file_exists(page.raw_html_path)

    # Step 5: Verify analytics report generation
    report = setup_file_storage.generate_report()
    assert report['total_pages'] == len(pages)
    assert report['success'] > 0  # Ensure there are successful scrapes

    # Step 6: Clean up any test data if necessary
    setup_database.cleanup_test_data()