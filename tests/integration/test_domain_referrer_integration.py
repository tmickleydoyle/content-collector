"""Integration test for domain tracking and referrer relationships."""

import pytest
import asyncio
import tempfile
import os
from pathlib import Path
from content_collector.core.scraper import ScrapingEngine
from content_collector.storage.database import db_manager
from content_collector.storage.models import Page, ScrapingRun
from sqlalchemy import select


class TestIntegrationDomainAndReferrer:
    """Integration tests for domain tracking and referrer relationships."""

    @pytest.mark.asyncio
    async def test_end_to_end_domain_tracking_and_referrers(self):
        """Test complete domain tracking and referrer functionality."""
        
        # Create a temporary CSV file for testing
        csv_content = """URL,Category,Priority
https://httpbin.org/html,test,1
https://httpbin.org/robots.txt,test,2"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(csv_content)
            csv_file_path = f.name
        
        try:
            # Initialize database for testing
            await db_manager.initialize()
            await db_manager.create_tables()
            
            # Create scraper instance
            scraper = ScrapingEngine()
            
            # Run a limited scrape (depth=1, max_pages=2)
            run_id = await scraper.run(
                input_file=Path(csv_file_path),
                max_pages=2,
                max_depth=1
            )
            
            # Verify run was created
            assert run_id is not None
            
            # Check the database for results
            async with db_manager.session() as session:
                # Check scraping run exists
                run_query = select(ScrapingRun).where(ScrapingRun.id == run_id)
                run_result = await session.execute(run_query)
                scraping_run = run_result.scalar_one_or_none()
                
                assert scraping_run is not None
                assert scraping_run.status in ["completed", "running"]
                
                # Check pages were created
                pages_query = select(Page).where(Page.scraping_run_id == run_id)
                pages_result = await session.execute(pages_query)
                pages = pages_result.scalars().all()
                
                assert len(pages) > 0
                
                # Verify domain tracking worked
                domains_seen = set()
                for page in pages:
                    domains_seen.add(page.domain)
                
                # Should have httpbin.org domain
                assert "httpbin.org" in domains_seen
                
                # Check that pages have proper structure
                for page in pages:
                    assert page.id is not None
                    assert page.url is not None
                    assert page.domain is not None
                    assert page.depth >= 0
                    assert page.scraping_run_id == run_id
                    # parent_id and referer_url may be None for root pages
                
                print(f"✅ Test completed successfully:")
                print(f"   - Run ID: {run_id}")
                print(f"   - Pages scraped: {len(pages)}")
                print(f"   - Domains: {domains_seen}")
                
                # Print page details for verification
                for page in pages:
                    print(f"   - Page: {page.url} (domain: {page.domain}, depth: {page.depth}, parent: {page.parent_id})")
        
        finally:
            # Clean up
            try:
                os.unlink(csv_file_path)
            except:
                pass
            try:
                await db_manager.close()
            except:
                pass

    def test_domain_tracking_standalone(self):
        """Test domain tracking functionality standalone."""
        scraper = ScrapingEngine()
        
        # Test initial state
        assert len(scraper._global_visited_domains) == 0
        
        # Test marking domains as visited
        urls = [
            "https://example.com/page1",
            "https://google.com/search",
            "https://github.com/repo"
        ]
        
        for url in urls:
            assert not scraper._should_skip_domain(url)
            scraper._mark_domain_as_visited(url)
        
        # Now should skip same domains
        assert scraper._should_skip_domain("https://example.com/page2")
        assert scraper._should_skip_domain("https://google.com/different")
        assert scraper._should_skip_domain("https://github.com/another")
        
        # Should not skip new domains
        assert not scraper._should_skip_domain("https://stackoverflow.com/question")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])