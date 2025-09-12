# Content Collector

A high-performance web scraping framework with intelligent content processing and concurrent execution.

## Features

- **Content Processing**: Handles HTML, JavaScript, PDFs, and images automatically
- **High Performance**: Concurrent scraping with configurable worker pools
- **Sitemap Discovery**: Automatically finds and processes XML sitemaps
- **Recursive Crawling**: Follows links with depth and domain controls
- **Data Storage**: PostgreSQL/SQLite with structured file output
- **Analytics**: Built-in reporting and performance monitoring

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Initialize database
python -m content_collector init

# Basic scraping
python -m content_collector run urls.csv

# High-performance mode
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
# Basic commands
python -m content_collector run urls.csv          # Standard scraping
python -m content_collector turbo urls.csv        # High-performance mode
python -m content_collector status                # Check run status
python -m content_collector report --run-id ID    # Generate reports

# Content analysis
python -m content_collector intelligence URL      # Analyze single page
python -m content_collector sitemap DOMAIN        # Discover URLs from sitemap
python -m content_collector test-parsing          # Test parsing capabilities
```

## Options

**Run command options:**
- `--max-pages N` - Limit total pages scraped
- `--depth N` - Maximum crawl depth (default: 1)
- `--allow-cross-domain` - Enable cross-domain crawling
- `--high-performance` - Use high-performance engine
- `--max-workers N` - Concurrent workers (high-performance mode)

**Turbo command options:**
- `--max-pages N` - Limit total pages scraped
- `--depth N` - Maximum crawl depth (default: 2)
- `--performance MODE` - Performance mode: conservative, balanced, aggressive, maximum (default: balanced)
- `--allow-cross-domain` - Enable cross-domain crawling
- `--show-stats` - Display real-time statistics (default: enabled)
