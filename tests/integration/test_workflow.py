"""Integration test for end-to-end workflow."""

import asyncio
import tempfile
from pathlib import Path
import pytest

from content_collector.input.processor import InputProcessor
from content_collector.core.scraper import ScrapingEngine
from content_collector.storage.database import db_manager


@pytest.mark.asyncio
async def test_complete_workflow():
    """Test the complete scraping workflow with httpbin.org endpoints."""
    
    # Create a temporary CSV file with test URLs
    test_urls = [
        "https://httpbin.org/html",
        "https://httpbin.org/json", 
        "https://httpbin.org/xml",
        "https://httpbin.org/robots.txt",
        "https://httpbin.org/status/200"
    ]
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        f.write("url\n")
        for url in test_urls:
            f.write(f"{url}\n")
        csv_path = Path(f.name)
    
    try:
        # Test input processing
        processor = InputProcessor()
        url_entries = await processor.process_input_file(csv_path)
        
        assert len(url_entries) >= 2  # Some might be filtered out
        assert any("httpbin.org/html" in str(entry.url) for entry in url_entries)
        
        # Initialize database
        await db_manager.initialize()
        await db_manager.create_tables()
        
        # Test scraping engine
        scraper = ScrapingEngine()
        run_id = await scraper.run(csv_path, max_pages=3)
        
        assert run_id is not None
        assert len(run_id) > 0
        
        # Verify data was stored
        async with db_manager.session() as session:
            from content_collector.storage.models import ScrapingRun, Page
            from sqlalchemy import select
            
            # Check run was created
            run = await session.get(ScrapingRun, run_id)
            assert run is not None
            assert run.status in ["completed", "failed"]
            
            # Check pages were created
            pages_query = select(Page).where(Page.scraping_run_id == run_id)
            pages_result = await session.execute(pages_query)
            pages = pages_result.scalars().all()
            
            assert len(pages) > 0
            
            # Check at least some pages were successful
            successful_pages = [p for p in pages if p.status_code == 200]
            assert len(successful_pages) > 0
            
        print(f"✅ Integration test passed! Run ID: {run_id}")
        print(f"   - Processed {len(url_entries)} URLs")
        print(f"   - Scraped {len(pages)} pages")
        print(f"   - {len(successful_pages)} successful")
        
    finally:
        # Cleanup
        csv_path.unlink()
        await db_manager.close()


if __name__ == "__main__":
    asyncio.run(test_complete_workflow())
    urls = ["http://example.com", "http://example.org"]
    
    # Run the CLI command to start the scraping process
    result = main(["run", "--input", "test_urls.csv"])
    
    assert result.exit_code == 0
    
    # Check if the URLs were scraped and stored correctly
    for url in urls:
        assert setup_database.get_url_status(url) == "success"
        assert setup_file_storage.file_exists(url)

    # Validate analytics report generation
    report = setup_database.generate_report()
    assert report['total_scraped'] == len(urls)
    assert report['success_count'] == len(urls)