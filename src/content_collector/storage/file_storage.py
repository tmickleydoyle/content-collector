"""File storage management for scraped content."""

import asyncio
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

    def setup(self):
        """Set up file storage - ensure directories exist."""
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.logger.info("File storage setup completed", base_path=str(self.base_path))

    def cleanup(self):
        """Clean up file storage - for test cleanup."""
        self.logger.info("File storage cleanup completed")

    async def save_content(
        self, content_id: str, content: str, parsed_data: Dict, url: str
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
            content_dir = self.base_path / content_id
            content_dir.mkdir(parents=True, exist_ok=True)

            paths = {
                "raw_html": content_dir / "raw.html",
                "body": content_dir / "body.txt",
                "headers": content_dir / "headers.txt",
                "metadata": content_dir / "metadata.txt",
            }

            await self._write_file(paths["raw_html"], content)

            body_text = parsed_data.get("body_text", "")
            await self._write_file(paths["body"], body_text)

            # Save full <head> section HTML for header analysis
            head_html = parsed_data.get("head_html", "")
            await self._write_file(paths["headers"], head_html)

            metadata_text = self._format_metadata(parsed_data, url)
            await self._write_file(paths["metadata"], metadata_text)

            self.logger.info(
                "Content saved successfully",
                content_id=content_id,
                files_saved=len(paths),
            )

            return paths

        except Exception as e:
            self.logger.error(
                "Failed to save content", content_id=content_id, error=str(e)
            )
            raise

    async def _write_file(self, file_path: Path, content: str) -> None:
        """Write content to file asynchronously."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, lambda: file_path.write_text(content, encoding="utf-8")
        )

    def _format_metadata(self, parsed_data: Dict, url: str) -> str:
        """Format metadata information."""
        lines = [
            f"URL: {url}",
            f"Content Length: {len(parsed_data.get('body_text', ''))} characters",
            f"Word Count: {len(parsed_data.get('body_text', '').split())} words",
            f"Links Found: {len(parsed_data.get('links', []))}",
            f"Images Found: {len(parsed_data.get('images', []))}",
        ]

        if content_hash := parsed_data.get("content_hash"):
            lines.append(f"Content Hash: {content_hash}")

        return "\n".join(lines)

    def get_content_paths(self, content_id: str) -> Dict[str, Path]:
        """Get file paths for stored content."""
        content_dir = self.base_path / content_id
        return {
            "raw_html": content_dir / "raw.html",
            "body": content_dir / "body.txt",
            "headers": content_dir / "headers.txt",
            "metadata": content_dir / "metadata.txt",
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


file_storage = FileStorage()
