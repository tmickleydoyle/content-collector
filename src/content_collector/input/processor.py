"""Input processing for web scraping URLs."""

import csv
from pathlib import Path
from typing import List, Set
from urllib.parse import urlparse

import structlog
from pydantic import BaseModel, HttpUrl, field_validator

from content_collector.utils.validators import URLValidator

logger = structlog.get_logger(__name__)


class URLEntry(BaseModel):
    """Model for validated URL entries."""

    url: HttpUrl
    description: str = ""

    @field_validator("url")
    @classmethod
    def validate_url(cls, v):
        """Validate URL using URLValidator."""
        validator = URLValidator()
        url_str = str(v)
        if not validator.is_valid_url(url_str):
            raise ValueError(f"Invalid URL: {url_str}")
        return v


class InputProcessor:
    """Process input files containing URLs."""

    def __init__(self):
        self.logger = logger.bind(component="input_processor")
        self.url_validator = URLValidator()

    async def process_input_file(self, input_file: Path) -> List[URLEntry]:
        """Process input file and return list of URL entries."""
        self.logger.info("Processing input file", file=str(input_file))

        if not input_file.exists():
            raise FileNotFoundError(f"Input file not found: {input_file}")

        if input_file.suffix.lower() == ".csv":
            self.logger.debug("Processing as direct CSV file")
            urls = await self._process_csv_file(input_file)
        else:
            self.logger.debug("Processing as file containing CSV paths")
            csv_files = self._read_csv_paths(input_file)
            urls = []

            for csv_file in csv_files:
                file_urls = await self._process_csv_file(csv_file)
                urls.extend(file_urls)

        unique_urls = self._deduplicate_urls(urls)

        csv_file_count = (
            1
            if input_file.suffix.lower() == ".csv"
            else len(self._read_csv_paths(input_file))
        )

        self.logger.info(
            "Input processing completed",
            total_urls=len(unique_urls),
            csv_files=csv_file_count,
        )

        return unique_urls

    def _read_csv_paths(self, input_file: Path) -> List[Path]:
        """Read CSV file paths from input file."""
        csv_files = []

        try:
            with open(input_file, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if line and not line.startswith("#"):
                        csv_path = Path(line)
                        if not csv_path.is_absolute():
                            csv_path = input_file.parent / csv_path

                        if csv_path.exists():
                            csv_files.append(csv_path)
                        else:
                            self.logger.warning(
                                "CSV file not found", file=str(csv_path), line=line_num
                            )
        except Exception as e:
            self.logger.error("Failed to read CSV paths", error=str(e))
            raise

        return csv_files

    async def _process_csv_file(self, csv_file: Path) -> List[URLEntry]:
        """Process individual CSV file to extract URLs."""
        self.logger.debug("Processing CSV file", file=str(csv_file))

        urls = []

        try:
            with open(csv_file, "r", encoding="utf-8") as f:
                content = f.read()
                f.seek(0)

                try:
                    sniffer = csv.Sniffer()
                    delimiter = sniffer.sniff(content[:1024]).delimiter
                    has_header = sniffer.has_header(content[:1024])

                    if delimiter in [":", "/", ".", "r", "l"] or len(delimiter) > 1:
                        delimiter = ","

                except csv.Error:
                    delimiter = ","
                    first_line = content.split("\n")[0] if content else ""
                    has_header = "url" in first_line.lower()

                reader = csv.reader(f, delimiter=delimiter)

                if has_header:
                    headers = next(reader, None)
                    self.logger.debug("CSV headers detected", headers=headers)

                for row_num, row in enumerate(reader, start=(2 if has_header else 1)):
                    if not row or len(row) == 0:
                        continue

                    url_str = row[0].strip()
                    if not url_str:
                        continue

                    description = row[1].strip() if len(row) > 1 else ""

                    if self.url_validator.is_valid_url(url_str):
                        try:
                            url_entry = URLEntry(url=url_str, description=description)
                            urls.append(url_entry)
                        except Exception as e:
                            self.logger.warning(
                                "Failed to create URL entry",
                                url=url_str,
                                error=str(e),
                                row=row_num,
                            )
                    else:
                        self.logger.debug(
                            "Skipping invalid URL", url=url_str, row=row_num
                        )

        except Exception as e:
            self.logger.error(
                "Failed to process CSV file", file=str(csv_file), error=str(e)
            )
            raise

        self.logger.debug(
            "CSV file processed", file=str(csv_file), urls_found=len(urls)
        )

        return urls

    def _deduplicate_urls(self, urls: List[URLEntry]) -> List[URLEntry]:
        """Remove duplicate URLs while preserving first occurrence."""
        seen_urls: Set[str] = set()
        unique_urls = []

        for url_entry in urls:
            url_str = str(url_entry.url)
            if url_str not in seen_urls:
                seen_urls.add(url_str)
                unique_urls.append(url_entry)

        return unique_urls
