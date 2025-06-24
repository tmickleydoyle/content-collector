"""Test referer URL logging functionality."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from content_collector.core.scraper import ScrapingEngine
from content_collector.storage.models import Page


class TestRefererLogging:
    """Test referer URL logging in scraped pages."""

    @pytest.mark.asyncio
    async def test_referer_url_storage(self, test_db_manager):
        """Test that referer URLs are properly stored in the database."""
        mock_file_storage = AsyncMock()

        page_id = f"test-page-{uuid.uuid4().hex[:8]}"
        parent_id = f"parent-page-{uuid.uuid4().hex[:8]}"
        run_id = f"test-run-{uuid.uuid4().hex[:8]}"

        with (
            patch("content_collector.core.scraper.db_manager", test_db_manager),
            patch("content_collector.core.scraper.file_storage", mock_file_storage),
        ):
            scraper = ScrapingEngine()

            url = "https://example.com/page"
            referer_url = "https://example.com/parent"

            await scraper._store_page_result(
                page_id=page_id,
                url=url,
                run_id=run_id,
                depth=1,
                parent_id=parent_id,
                referer_url=referer_url,
                status_code=200,
                headers={"content-type": "text/html"},
                parsed_data={"title": "Test Page"},
                content="<html><body>Test</body></html>",
            )

            async with test_db_manager.session() as session:
                query = select(Page).where(Page.id == page_id)
                result = await session.execute(query)
                page = result.scalar_one_or_none()

                assert page is not None
                assert page.url == url
                assert page.referer_url == referer_url
                assert page.parent_id == parent_id
                assert page.depth == 1
                assert page.status_code == 200

    @pytest.mark.asyncio
    async def test_referer_url_none_for_root_pages(self, test_db_manager):
        """Test that root pages have no referer URL."""
        mock_file_storage = AsyncMock()

        page_id = f"test-root-page-{uuid.uuid4().hex[:8]}"
        run_id = f"test-run-{uuid.uuid4().hex[:8]}"

        with (
            patch("content_collector.core.scraper.db_manager", test_db_manager),
            patch("content_collector.core.scraper.file_storage", mock_file_storage),
        ):
            scraper = ScrapingEngine()

            url = "https://example.com/"

            await scraper._store_page_result(
                page_id=page_id,
                url=url,
                run_id=run_id,
                depth=0,
                status_code=200,
                headers={"content-type": "text/html"},
                parsed_data={"title": "Root Page"},
                content="<html><body>Root</body></html>",
            )

            async with test_db_manager.session() as session:
                query = select(Page).where(Page.id == page_id)
                result = await session.execute(query)
                page = result.scalar_one_or_none()

                assert page is not None
                assert page.url == url
                assert page.referer_url is None
                assert page.parent_id is None
                assert page.depth == 0
                assert page.status_code == 200
