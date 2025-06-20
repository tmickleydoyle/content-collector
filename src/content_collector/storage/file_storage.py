"""File storage management for scraped content."""

import asyncio
import hashlib
from pathlib import Path
from typing import Dict, Optional
import structlog

from content_collector.config.settings import settings

logger = structlog.get_logger(__name__)


class FileStorage:
    """Async file storage for scraped content."""
    
    def __init__(self, base_path: Optional[Path] = None):
        """Initialize file storage."""
        self.base_path = base_path or settings.storage.content_dir
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.logger = logger.bind(component="file_storage")
        
    async def save_content(
        self, 
        content_id: str, 
        content: str,
        parsed_data: Dict,
        url: str
    ) -> Dict[str, Path]:
        """
        Save scraped content to organized file structure.
        
        Args:
            content_id: Unique identifier for the content
            content: Raw HTML content
            parsed_data: Parsed data containing title, headers, body, etc.
            url: Source URL
            
        Returns:
            Dictionary of saved file paths
        """
        try:
            # Create content directory
            content_dir = self.base_path / content_id
            content_dir.mkdir(parents=True, exist_ok=True)
            
            # File paths
            paths = {
                "raw_html": content_dir / "raw.html",
                "body": content_dir / "body.txt", 
                "headers": content_dir / "headers.txt",
                "metadata": content_dir / "metadata.txt"
            }
            
            # Save raw HTML
            await self._write_file(paths["raw_html"], content)
            
            # Save body text
            body_text = parsed_data.get('body_text', '')
            await self._write_file(paths["body"], body_text)
            
            # Save headers/structure
            headers_text = self._format_headers(parsed_data)
            await self._write_file(paths["headers"], headers_text)
            
            # Save metadata
            metadata_text = self._format_metadata(parsed_data, url)
            await self._write_file(paths["metadata"], metadata_text)
            
            self.logger.info(
                "Content saved successfully",
                content_id=content_id,
                files_saved=len(paths)
            )
            
            return paths
            
        except Exception as e:
            self.logger.error(
                "Failed to save content",
                content_id=content_id,
                error=str(e)
            )
            raise
    
    async def _write_file(self, file_path: Path, content: str) -> None:
        """Write content to file asynchronously."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: file_path.write_text(content, encoding='utf-8')
        )
    
    def _format_headers(self, parsed_data: Dict) -> str:
        """Format headers and title information."""
        lines = []
        
        if title := parsed_data.get('title'):
            lines.append(f"TITLE: {title}")
            lines.append("")
        
        if meta_desc := parsed_data.get('meta_description'):
            lines.append(f"META DESCRIPTION: {meta_desc}")
            lines.append("")
        
        # Add headers
        for level in range(1, 7):  # H1-H6
            headers = parsed_data.get(f'h{level}', [])
            if headers:
                lines.append(f"H{level} HEADERS:")
                for header in headers:
                    lines.append(f"  - {header}")
                lines.append("")
        
        return "\n".join(lines)
    
    def _format_metadata(self, parsed_data: Dict, url: str) -> str:
        """Format metadata information."""
        lines = [
            f"URL: {url}",
            f"Content Length: {len(parsed_data.get('body_text', ''))} characters",
            f"Word Count: {len(parsed_data.get('body_text', '').split())} words",
            f"Links Found: {len(parsed_data.get('links', []))}",
            f"Images Found: {len(parsed_data.get('images', []))}",
        ]
        
        if content_hash := parsed_data.get('content_hash'):
            lines.append(f"Content Hash: {content_hash}")
            
        return "\n".join(lines)
    
    def get_content_paths(self, content_id: str) -> Dict[str, Path]:
        """Get file paths for stored content."""
        content_dir = self.base_path / content_id
        return {
            "raw_html": content_dir / "raw.html",
            "body": content_dir / "body.txt",
            "headers": content_dir / "headers.txt", 
            "metadata": content_dir / "metadata.txt"
        }
    
    def content_exists(self, content_id: str) -> bool:
        """Check if content already exists."""
        content_dir = self.base_path / content_id
        return content_dir.exists() and (content_dir / "raw.html").exists()
    
    async def cleanup_old_content(self, days: int = 30) -> int:
        """Remove content older than specified days."""
        import time
        cutoff_time = time.time() - (days * 24 * 60 * 60)
        removed_count = 0
        
        try:
            for content_dir in self.base_path.iterdir():
                if content_dir.is_dir():
                    # Check if directory is old enough
                    if content_dir.stat().st_mtime < cutoff_time:
                        import shutil
                        await asyncio.get_event_loop().run_in_executor(
                            None, shutil.rmtree, content_dir
                        )
                        removed_count += 1
                        
            self.logger.info(f"Cleaned up {removed_count} old content directories")
            return removed_count
            
        except Exception as e:
            self.logger.error("Failed to cleanup old content", error=str(e))
            raise


# Global file storage instance
file_storage = FileStorage()