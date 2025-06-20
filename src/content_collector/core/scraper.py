"""Main scraping engine that orchestrates the scraping process."""

import asyncio
import uuid
from pathlib import Path
from typing import List, Optional

import structlog

from ..config.settings import settings
from ..input.processor import InputProcessor, URLEntry
from ..core.fetcher import HTTPFetcher
from ..core.parser import ContentParser
from ..storage.database import db_manager
from ..storage.file_storage import file_storage
from ..storage.models import Page, ScrapingRun
from ..utils.validators import URLValidator

logger = structlog.get_logger()


class ScrapingEngine:
    """Main scraping engine that coordinates the scraping workflow."""
    
    def __init__(self) -> None:
        """Initialize scraping engine."""
        self.logger = logger.bind(component="scraping_engine")
        self.input_processor = InputProcessor()
        self.content_parser = ContentParser()
        self.url_validator = URLValidator()
        
    async def run(self, input_file: Path, max_pages: Optional[int] = None) -> str:
        """
        Run the complete scraping workflow.
        
        Args:
            input_file: Path to input file containing CSV paths
            max_pages: Maximum number of pages to scrape
            
        Returns:
            Run ID for tracking progress
        """
        run_id = str(uuid.uuid4())
        
        self.logger.info(
            "Starting scraping run",
            run_id=run_id,
            input_file=str(input_file),
            max_pages=max_pages
        )
        
        # Create scraping run record
        async with db_manager.session() as session:
            scraping_run = ScrapingRun(
                id=run_id,
                input_file=str(input_file),
                max_depth=settings.scraping.max_depth,
                total_urls=0,
                status="running"
            )
            session.add(scraping_run)
            await session.commit()
        
        try:
            # Process input file to get URLs
            url_entries = await self.input_processor.process_input_file(input_file)
            
            if not url_entries:
                self.logger.warning("No URLs found in input file")
                return run_id
            
            # Limit URLs if max_pages specified
            if max_pages and len(url_entries) > max_pages:
                url_entries = url_entries[:max_pages]
            
            # Update total URLs count
            async with db_manager.session() as session:
                result = await session.get(ScrapingRun, run_id)
                if result:
                    result.total_urls = len(url_entries)
                    await session.commit()
            
            # Start scraping
            await self._scrape_urls(url_entries, run_id)
            
            # Mark run as completed
            async with db_manager.session() as session:
                result = await session.get(ScrapingRun, run_id)
                if result:
                    result.status = "completed"
                    await session.commit()
            
            self.logger.info("Scraping run completed", run_id=run_id)
            
        except Exception as e:
            self.logger.error("Scraping run failed", run_id=run_id, error=str(e))
            
            # Mark run as failed
            async with db_manager.session() as session:
                result = await session.get(ScrapingRun, run_id)
                if result:
                    result.status = "failed"
                    result.error_message = str(e)
                    await session.commit()
            
            raise
        
        return run_id
    
    async def _scrape_urls(self, url_entries: List[URLEntry], run_id: str) -> None:
        """Scrape list of URLs with concurrency control."""
        semaphore = asyncio.Semaphore(settings.scraping.max_concurrent_requests)
        
        async with HTTPFetcher() as fetcher:
            tasks = []
            for url_entry in url_entries:
                task = self._scrape_single_url(
                    fetcher, url_entry, run_id, semaphore
                )
                tasks.append(task)
            
            # Execute tasks with progress tracking
            self.logger.info(f"Starting to scrape {len(tasks)} URLs")
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _scrape_single_url(
        self, 
        fetcher: HTTPFetcher, 
        url_entry: URLEntry, 
        run_id: str,
        semaphore: asyncio.Semaphore
    ) -> None:
        """Scrape a single URL and store results."""
        async with semaphore:
            page_id = str(uuid.uuid4())
            url = str(url_entry.url)
            
            self.logger.debug("Scraping URL", url=url, page_id=page_id)
            
            try:
                # Fetch content
                status_code, content, headers = await fetcher.fetch(url)
                
                # Parse content if successful
                parsed_data = {}
                if status_code == 200 and content:
                    parsed_data = self.content_parser.parse_html(content, url)
                
                # Extract domain
                domain = self.url_validator.extract_domain(url)
                
                # Store in database
                async with db_manager.session() as session:
                    page = Page(
                        id=page_id,
                        url=url,
                        domain=domain or "unknown",
                        status_code=status_code,
                        depth=0,  # TODO: Implement depth tracking for recursive crawling
                        content_hash=parsed_data.get('content_hash'),
                        title=parsed_data.get('title'),
                        meta_description=parsed_data.get('meta_description'),
                        content_type=headers.get('content-type'),
                        content_length=parsed_data.get('content_length', 0)
                    )
                    session.add(page)
                    await session.commit()
                
                # Store file content to disk
                if status_code == 200 and content:
                    await file_storage.save_content(
                        content_id=page_id,
                        content=content,
                        parsed_data=parsed_data,
                        url=url
                    )
                # TODO: Extract and queue child URLs for recursive crawling
                
                self.logger.info(
                    "URL scraped successfully",
                    url=url,
                    status_code=status_code,
                    title=parsed_data.get('title', 'No title')
                )
                
            except Exception as e:
                self.logger.error(
                    "Failed to scrape URL",
                    url=url,
                    error=str(e)
                )
                
                # Store failed attempt
                async with db_manager.session() as session:
                    page = Page(
                        id=page_id,
                        url=url,
                        domain=self.url_validator.extract_domain(url) or "unknown",
                        status_code=500,
                        depth=0,
                        last_error=str(e),
                        retry_count=1
                    )
                    session.add(page)
                    await session.commit()