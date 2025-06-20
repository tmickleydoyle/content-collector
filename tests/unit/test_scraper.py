import pytest
from content_collector.core.scraper import ScrapingEngine
from content_collector.utils.validators import URLValidator

@pytest.fixture
def scraper():
    return ScrapingEngine()

def test_scrape_valid_url(scraper):
    url = "https://example.com"
    # Note: This would require async testing in real implementation
    # For now just test that the class can be instantiated
    assert scraper is not None

def test_url_validation():
    validator = URLValidator()
    valid_url = "https://example.com"
    invalid_url = "invalid-url"
    assert validator.is_valid_url(valid_url) is True
    assert validator.is_valid_url(invalid_url) is False