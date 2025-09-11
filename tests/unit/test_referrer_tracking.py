"""Tests for referrer and parent-child relationship tracking."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from content_collector.core.scraper import ScrapingEngine
from content_collector.storage.models import Page
import uuid


class TestReferrerTracking:
    """Test referrer and parent-child relationship tracking."""

    @pytest.mark.asyncio
    async def test_scrape_single_url_with_children_returns_page_id(self):
        """Test that _scrape_single_url_with_children returns both child URLs and page_id."""
        scraper = ScrapingEngine()
        
        # Mock dependencies
        with patch('content_collector.core.scraper.HTTPFetcher') as mock_fetcher_class:
            mock_fetcher = AsyncMock()
            mock_fetcher_class.return_value.__aenter__.return_value = mock_fetcher
            mock_fetcher.fetch.return_value = (200, "<html><a href='http://example.com/child'>Child</a></html>", {})
            
            with patch.object(scraper, '_parse_content_if_successful') as mock_parse:
                mock_parse.return_value = {
                    "links": ["http://example.com/child1", "http://example.com/child2"]
                }
                
                with patch.object(scraper, '_store_page_result') as mock_store:
                    with patch('content_collector.core.scraper.file_storage') as mock_file_storage:
                        mock_file_storage.save_content = AsyncMock()
                        
                        # Create a test URL entry
                        from content_collector.input.processor import URLEntry
                        url_entry = URLEntry(url="http://example.com/parent", priority=1)
                        
                        # Call method
                        child_urls, page_id = await scraper._scrape_single_url_with_children(
                            url_entry, "test-run-id", depth=0, parent_id="parent-page-id", referer_url="http://example.com/referer"
                        )
                        
                        # Verify results
                        assert isinstance(child_urls, list)
                        assert len(child_urls) == 2
                        assert "http://example.com/child1" in child_urls
                        assert "http://example.com/child2" in child_urls
                        assert isinstance(page_id, str)
                        assert len(page_id) > 0
                        
                        # Verify store was called with correct parameters
                        mock_store.assert_called_once()
                        call_args = mock_store.call_args
                        assert call_args[0][0] == page_id  # page_id
                        assert call_args[0][1] == "http://example.com/parent"  # url
                        assert call_args[0][2] == "test-run-id"  # run_id
                        assert call_args[1]['parent_id'] == "parent-page-id"
                        assert call_args[1]['referer_url'] == "http://example.com/referer"

    @pytest.mark.asyncio
    async def test_recursive_scraping_passes_parent_info(self):
        """Test that recursive scraping properly passes parent_id and referer_url."""
        scraper = ScrapingEngine()
        
        # Mock the _scrape_single_url_with_children method
        with patch.object(scraper, '_scrape_single_url_with_children') as mock_scrape_single:
            mock_scrape_single.return_value = (["http://example.com/child"], "page-id-123")
            
            with patch.object(scraper, '_should_skip_url_for_loop_prevention') as mock_skip_loop:
                mock_skip_loop.return_value = False
                
                with patch.object(scraper, '_should_skip_domain') as mock_skip_domain:
                    mock_skip_domain.return_value = False
                    
                    with patch.object(scraper, '_mark_domain_as_visited'):
                        
                        # Create test URL entries
                        from content_collector.input.processor import URLEntry
                        url_entries = [URLEntry(url="http://example.com/parent", priority=1)]
                        
                        # Call recursive method
                        await scraper._scrape_urls_recursive(
                            url_entries, 
                            "test-run-id", 
                            max_depth=2, 
                            current_depth=0,
                            parent_id="initial-parent-id",
                            referer_url="http://example.com/initial-referer"
                        )
                        
                        # Verify first call (depth 0)
                        assert mock_scrape_single.call_count >= 1
                        first_call = mock_scrape_single.call_args_list[0]
                        assert first_call[0][2] == 0  # depth
                        assert first_call[0][3] == "initial-parent-id"  # parent_id
                        assert first_call[0][4] == "http://example.com/initial-referer"  # referer_url

    def test_domain_tracking_skips_already_visited_domains(self):
        """Test that domain tracking correctly skips domains that have been visited."""
        scraper = ScrapingEngine()
        
        # Mark a domain as visited
        scraper._mark_domain_as_visited("http://example.com/page1")
        
        # Should skip other URLs from same domain
        assert scraper._should_skip_domain("http://example.com/page2")
        assert scraper._should_skip_domain("https://example.com/different/path")
        
        # Should not skip different domains
        assert not scraper._should_skip_domain("http://google.com/page")

    @pytest.mark.asyncio 
    async def test_store_page_result_includes_parent_and_referer(self):
        """Test that _store_page_result properly stores parent_id and referer_url."""
        scraper = ScrapingEngine()
        
        # Mock database session
        with patch('content_collector.core.scraper.db_manager.session') as mock_session_context:
            mock_session = AsyncMock()
            mock_session_context.return_value.__aenter__.return_value = mock_session
            
            # Call the method
            await scraper._store_page_result(
                page_id="test-page-id",
                url="http://example.com/test",
                run_id="test-run-id",
                status_code=200,
                parsed_data={"title": "Test Page"},
                headers={"content-type": "text/html"},
                referer_url="http://example.com/parent",
                depth=1,
                parent_id="parent-page-id"
            )
            
            # Verify Page object was created with correct values
            mock_session.add.assert_called_once()
            page_obj = mock_session.add.call_args[0][0]
            assert isinstance(page_obj, Page)
            assert page_obj.id == "test-page-id"
            assert page_obj.url == "http://example.com/test"
            assert page_obj.parent_id == "parent-page-id"
            assert page_obj.referer_url == "http://example.com/parent"
            assert page_obj.depth == 1
            assert page_obj.scraping_run_id == "test-run-id"

    def test_mark_domain_as_visited_adds_to_set(self):
        """Test that marking domain as visited adds it to the visited domains set."""
        scraper = ScrapingEngine()
        
        # Initially empty
        assert len(scraper._global_visited_domains) == 0
        
        # Mark domain as visited
        scraper._mark_domain_as_visited("http://example.com/page")
        
        # Should be in the set
        assert "example.com" in scraper._global_visited_domains
        assert len(scraper._global_visited_domains) == 1
        
        # Mark another URL from same domain
        scraper._mark_domain_as_visited("http://example.com/different")
        
        # Should still be just one domain
        assert len(scraper._global_visited_domains) == 1
        
        # Mark different domain
        scraper._mark_domain_as_visited("http://google.com/page")
        
        # Should now have two domains
        assert len(scraper._global_visited_domains) == 2
        assert "google.com" in scraper._global_visited_domains


if __name__ == "__main__":
    pytest.main([__file__])