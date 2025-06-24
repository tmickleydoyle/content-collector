# Content Collector 🕷️

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

A **high-performance, scalable web scraping framework** with advanced concurrency optimization, designed for enterprise-grade data collection pipelines.

## ✨ Key Features

### 🚀 **High-Performance Engine**
- **30x faster** than traditional scrapers with advanced parallelization
- **Multi-mode performance optimization** (Conservative → Maximum)
- **Real-time monitoring** with live statistics and throughput metrics
- **System-aware scaling** based on CPU cores and available memory

### 🔧 **Enterprise-Grade Architecture**
- **Producer-consumer pattern** with async worker pools
- **Multiple HTTP fetcher instances** for optimal connection distribution
- **Intelligent rate limiting** with per-domain controls
- **Robust error handling** with automatic retry mechanisms

### 📊 **Advanced Data Management**
- **PostgreSQL/SQLite support** with async database operations
- **Structured file storage** with content deduplication
- **Comprehensive metadata tracking** (lineage, timestamps, retry history)
- **Analytics & reporting** with success rates and performance dashboards

### 🎯 **Flexible Input/Output**
- **CSV file processing** with automatic URL discovery
- **Recursive crawling** with configurable depth limits
- **Cross-domain control** with same-domain restrictions
- **Loop prevention** to avoid infinite crawling cycles

## 🏗️ Architecture

### High-Performance Engine Architecture

```
Input URLs → Producer Queue → Worker Pool → Fetcher Pool → Results Queue → Database
     ↓            ↓              ↓            ↓             ↓              ↓
  CSV Files   Async Queue    20-80 Workers  Multiple      Non-blocking   Batch Ops
              All depths     Independent    HTTP Clients  Processing     Async DB
              parallel       execution     Load balanced  Pipeline       Operations
```

### Project Structure

```
content-collector/
├── src/content_collector/
│   ├── cli/                    # Command-line interface
│   │   └── main.py            # CLI commands and options
│   ├── core/                  # Core scraping engines
│   │   ├── scraper.py         # Standard scraping engine
│   │   ├── enhanced_scraper.py # High-performance engine
│   │   ├── fetcher.py         # HTTP client
│   │   ├── enhanced_fetcher.py # Optimized HTTP client
│   │   └── parser.py          # Content parsing
│   ├── config/                # Configuration management
│   │   ├── settings.py        # Application settings
│   │   ├── performance.py     # Performance optimization
│   │   └── constants.py       # Application constants
│   ├── storage/               # Data persistence
│   │   ├── database.py        # Database operations
│   │   ├── models.py          # SQLAlchemy models
│   │   └── file_storage.py    # File system storage
│   ├── input/                 # Input processing
│   │   └── processor.py       # CSV and URL processing
│   ├── analytics/             # Reporting and analytics
│   │   └── reporting.py       # Performance reports
│   └── utils/                 # Utilities
│       ├── validators.py      # URL validation
│       ├── logging.py         # Structured logging
│       └── database_helpers.py # DB utilities
├── tests/                     # Test suites
│   ├── unit/                  # Unit tests
│   ├── integration/           # Integration tests
│   └── e2e/                   # End-to-end tests
├── migrations/                # Database migrations
├── docker/                    # Docker configuration
└── scripts/                   # Utility scripts
```

## ⚙️ Configuration

### Environment Variables

```bash
# Database configuration
export DATABASE_URL="postgresql://user:pass@localhost/content_collector"

# Performance tuning
export CONTENT_COLLECTOR_MAX_WORKERS=50
export CONTENT_COLLECTOR_MAX_CONNECTIONS=200
export CONTENT_COLLECTOR_PERFORMANCE_MODE=aggressive

# Logging
export CONTENT_COLLECTOR_LOG_LEVEL=INFO
```

### Settings File

Configure in `src/content_collector/config/settings.py`:

```python
class ScrapingSettings:
    max_concurrent_requests: int = 10
    request_timeout: int = 30
    rate_limit_delay: float = 1.0
    user_agent: str = "ContentCollector/1.0"
    enable_loop_prevention: bool = True
    allow_cross_domain: bool = False
```

## 📊 Monitoring & Analytics

### Real-time Performance Monitoring

```bash
# Enable live statistics
python -m content_collector turbo input.csv --show-stats

# Monitor specific run
python -m content_collector status --run-id RUN_ID
```

### Performance Metrics

- **Throughput**: URLs processed per second
- **Success Rate**: Percentage of successful requests
- **Response Times**: Average and percentile response times
- **Worker Utilization**: Active workers and queue depth
- **Resource Usage**: Memory and CPU utilization warnings

### Report Generation

```bash
# Generate comprehensive report
python -m content_collector report --run-id RUN_ID

# Export analytics data
python -m content_collector report --format json --output report.json
```

## 🧪 Testing

### Test Suites

```bash
# Run all tests
pytest

# Unit tests only
pytest tests/unit/

# Integration tests
pytest tests/integration/

# Performance tests
pytest tests/e2e/ -m performance

# Coverage report
pytest --cov=content_collector --cov-report=html
```

### Performance Benchmarking

```bash
# Benchmark different engines
python -m pytest tests/performance/test_engine_comparison.py

# Load testing
python scripts/load_test.py --urls 1000 --workers 50
```

## 🚀 Quick Start

### Installation

```bash
# Clone the repository
git clone git@github.com:tmickleydoyle/content-collector.git
cd content-collector

# Install dependencies
pip install -r requirements.txt

# Initialize the system
python -m content_collector init
```

### Basic Usage

```bash
# Standard scraping
python -m content_collector run input.csv

# High-performance mode (2x faster)
python -m content_collector run input.csv --high-performance

# Turbo mode (up to 30x faster)
python -m content_collector turbo input.csv --performance aggressive
```

### Input Format

Create a CSV file with URLs to scrape:

```csv
URL,Category,Priority
https://example.com,technology,1
https://httpbin.org/html,testing,2
https://docs.python.org,documentation,1
```

## ⚡ Performance Modes

| Mode | Workers | Connections | Best For | Speed Gain |
|------|---------|-------------|----------|------------|
| **Conservative** | 10 | 20 | Limited resources | 2x |
| **Balanced** | 20 | 60 | Production (default) | 5-10x |
| **Aggressive** | 40 | 160 | High-performance systems | 15-25x |
| **Maximum** | 80 | 400 | Maximum throughput | 25-30x |

```bash
# Select performance mode
python -m content_collector turbo input.csv --performance balanced
python -m content_collector turbo input.csv --performance aggressive
python -m content_collector turbo input.csv --performance maximum
```

## 📖 Command Reference

### Core Commands

```bash
# Initialize database and configuration
python -m content_collector init

# Run standard scraper
python -m content_collector run INPUT_FILE [OPTIONS]

# Run high-performance scraper
python -m content_collector turbo INPUT_FILE [OPTIONS]

# Check scraping status
python -m content_collector status [--run-id RUN_ID]

# Generate reports
python -m content_collector report [--run-id RUN_ID]

# Clean up old data
python -m content_collector cleanup [OPTIONS]
```

### Options

| Option | Description | Default |
|--------|-------------|---------|
| `--max-pages` | Maximum pages to scrape | No limit |
| `--depth` | Maximum crawling depth | 2 |
| `--performance` | Performance mode (turbo only) | balanced |
| `--max-workers` | Override worker count | Auto-detected |
| `--enable-loop-prevention` | Prevent infinite loops | True |
| `--allow-cross-domain` | Allow cross-domain crawling | False |
| `--show-stats` | Real-time statistics | True (turbo) |

### Advanced Examples

```bash
# High-performance with custom settings
python -m content_collector turbo input.csv \
  --performance aggressive \
  --max-workers 50 \
  --depth 3 \
  --max-pages 1000 \
  --allow-cross-domain

# Monitor large scraping job
python -m content_collector turbo input.csv \
  --performance maximum \
  --show-stats \
  --depth 5

# Development/testing mode
python -m content_collector run input.csv \
  --high-performance \
  --max-pages 10 \
  --depth 1
```

## 🚀 Development

### Setup Development Environment

```bash
# Clone and setup
git clone git@github.com:tmickleydoyle/content-collector.git
cd content-collector

# Install development dependencies
pip install -r requirements-dev.txt

# Install pre-commit hooks
pre-commit install

# Run development server
python -m content_collector init
```

### Code Quality

```bash
# Format code
black src/ tests/

# Lint code
flake8 src/ tests/

# Type checking
mypy src/

# Security scan
bandit -r src/
```

### Database Development

```bash
# Create new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Reset database
alembic downgrade base
alembic upgrade head
```

## 🐛 Troubleshooting

### Common Issues

**Memory Issues**
```bash
# Reduce worker count
python -m content_collector turbo input.csv --performance conservative --max-workers 5
```

**Network Timeouts**
```bash
# Increase timeout settings
export CONTENT_COLLECTOR_REQUEST_TIMEOUT=60
```

**Database Connection Issues**
```bash
# Check database connectivity
python -c "from content_collector.storage.database import db_manager; print('DB OK')"
```

**High CPU Usage**
```bash
# Monitor system resources
python -m content_collector turbo input.csv --show-stats --performance balanced
```

### Debug Mode

```bash
# Enable debug logging
export CONTENT_COLLECTOR_LOG_LEVEL=DEBUG
python -m content_collector turbo input.csv --show-stats
```

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
