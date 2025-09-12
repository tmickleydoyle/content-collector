"""Tests for domain tracking functionality in recursive scraping."""

import pytest
from unittest.mock import AsyncMock, patch
from content_collector.core.scraper import ScrapingEngine
from content_collector.core.enhanced_scraper import HighPerformanceScrapingEngine
from content_collector.utils.validators import URLValidator


class TestDomainTracking:
    """Test domain tracking functionality."""

    def test_domain_tracking_initialization(self):
        """Test that domain tracking is properly initialized."""
        scraper = ScrapingEngine()
        assert hasattr(scraper, '_global_visited_domains')
        assert scraper._global_visited_domains == set()

    def test_enhanced_domain_tracking_initialization(self):
        """Test that domain tracking is properly initialized in enhanced scraper."""
        scraper = HighPerformanceScrapingEngine()
        assert hasattr(scraper, '_global_visited_domains')
        assert scraper._global_visited_domains == set()

    def test_should_skip_domain_initially_false(self):
        """Test that domains are not skipped initially."""
        scraper = ScrapingEngine()
        assert not scraper._should_skip_domain("https://example.com/page1")

    def test_should_skip_domain_after_marking_visited(self):
        """Test that domains are skipped after being marked as visited."""
        scraper = ScrapingEngine()
        url = "https://example.com/page1"
        
        # Initially should not skip
        assert not scraper._should_skip_domain(url)
        
        # Mark domain as visited
        scraper._mark_domain_as_visited(url)
        
        # Now should skip different URLs from same domain
        assert scraper._should_skip_domain("https://example.com/page2")
        assert scraper._should_skip_domain("https://example.com/different/path")

    def test_different_domains_not_skipped(self):
        """Test that different domains are not skipped."""
        scraper = ScrapingEngine()
        
        # Mark one domain as visited
        scraper._mark_domain_as_visited("https://example.com/page1")
        
        # Different domain should not be skipped
        assert not scraper._should_skip_domain("https://google.com/page1")
        assert not scraper._should_skip_domain("https://github.com/repo")

    def test_enhanced_scraper_domain_tracking(self):
        """Test domain tracking in enhanced scraper."""
        scraper = HighPerformanceScrapingEngine()
        
        url1 = "https://example.com/page1"
        url2 = "https://example.com/page2"
        url3 = "https://google.com/page1"
        
        # Initially no domains should be skipped
        assert not scraper._should_skip_domain(url1)
        assert not scraper._should_skip_domain(url2)
        assert not scraper._should_skip_domain(url3)
        
        # Mark example.com as visited
        scraper._mark_domain_as_visited(url1)
        
        # Same domain should be skipped
        assert scraper._should_skip_domain(url2)
        
        # Different domain should not be skipped
        assert not scraper._should_skip_domain(url3)

    def test_domain_extraction_and_marking(self):
        """Test domain extraction and marking functionality."""
        scraper = ScrapingEngine()
        
        test_urls = [
            "https://example.com/path",
            "https://google.com/different",
            "https://github.com/page",
            "https://stackoverflow.com/test"
        ]
        
        for url in test_urls:
            # Should not be skipped initially
            assert not scraper._should_skip_domain(url)
            
            # Mark as visited
            scraper._mark_domain_as_visited(url)
            
            # Domain should be in visited set
            domain = scraper.url_validator.extract_domain(url)
            assert domain in scraper._global_visited_domains

    def test_child_url_filtering_with_domain_tracking(self):
        """Test that child URL filtering includes domain tracking."""
        scraper = HighPerformanceScrapingEngine()
        
        parent_url = "https://example.com/page1"
        child_links = [
            "https://example.com/page2",
            "https://example.com/page3", 
            "https://google.com/page1",
            "https://github.com/repo"
        ]
        
        # Initially all should be included (assuming same domain policy)
        with patch('content_collector.config.settings.settings.scraping.allow_cross_domain', True):
            filtered = scraper._filter_child_urls(child_links, parent_url)
            assert len(filtered) == 4
        
        # Mark example.com as visited
        scraper._mark_domain_as_visited(parent_url)
        
        # Now example.com URLs should be filtered out
        with patch('content_collector.config.settings.settings.scraping.allow_cross_domain', True):
            filtered = scraper._filter_child_urls(child_links, parent_url)
            expected_filtered = ["https://google.com/page1", "https://github.com/repo"]
            assert set(filtered) == set(expected_filtered)


if __name__ == "__main__":
    pytest.main([__file__])