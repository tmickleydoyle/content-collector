# Content Collector

A high-performance web scraping framework with intelligent content processing and concurrent execution.

## Features

- **Content Processing**: Handles HTML, JavaScript, PDFs, and images automatically
- **High Performance**: Concurrent scraping with configurable worker pools
- **Content Intelligence**: Automatic content type detection and optimal parsing
- **Recursive Crawling**: Follows links with depth and domain controls
- **Data Storage**: PostgreSQL/SQLite with structured file output
- **Analytics**: Built-in reporting and performance monitoring

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Initialize database
python -m content_collector init

# High-performance scraping with automatic content processing
python -m content_collector turbo urls.csv --performance aggressive
```

## Input Format

CSV file with URLs:
```csv
url,description
https://example.com,Example site
https://docs.python.org,Documentation
```

## Commands

```bash
# Core commands
python -m content_collector turbo urls.csv        # High-performance scraping
python -m content_collector status                # Check run status
python -m content_collector report --run-id ID    # Generate reports

# Testing and diagnostics
python -m content_collector test-parsing          # Test parsing capabilities
python -m content_collector benchmark             # Run performance benchmarks
```

## Turbo Command Options

- `--max-pages N` - Limit total pages scraped
- `--depth N` - Maximum crawl depth (default: 1)
- `--performance MODE` - Performance mode: conservative, balanced, aggressive, maximum (default: balanced)
- `--max-workers N` - Override number of concurrent workers
- `--allow-cross-domain` - Enable cross-domain crawling
- `--show-stats` - Display real-time performance statistics
