# Content Collector

## Overview

Content Collector is a scalable and maintainable web scraping application designed to read URLs from CSV files, scrape content from web pages, store metadata in a PostgreSQL database, and generate analytics and reports. This project aims to provide a reliable data ingestion pipeline for engineers, DevOps, and stakeholders.

## Features

- **URL Input**: Reads lists of URLs from CSV files referenced in a `.txt` file.
- **Web Scraping**: Scrapes page headers, body content, metadata, and follows links recursively while tracking lineage.
- **Data Storage**: Stores metadata (lineage, timestamps, status codes, retry history) in PostgreSQL and saves page content in a structured file system.
- **Analytics & Reporting**: Generates analytics and reports at the end of each run, including success rates, error dashboards, and storage usage metrics.

## Project Structure

```
content-collector
├── src
│   ├── content_collector
│   │   ├── cli
│   │   ├── core
│   │   ├── storage
│   │   ├── config
│   │   ├── utils
│   │   └── analytics
├── tests
│   ├── unit
│   ├── integration
│   └── e2e
├── migrations
├── docker
├── scripts
├── .github
├── requirements.txt
├── requirements-dev.txt
├── pyproject.toml
├── .gitignore
└── README.md
```

## Installation

1. Clone the repository:
   ```
   git clone <repository-url>
   cd content-collector
   ```

2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Set up the database:
   - Configure your PostgreSQL database connection in `src/content_collector/config/settings.py`.
   - Run migrations using Alembic.

4. Run the application:
   ```
   python -m content_collector.cli.main
   ```

## Usage

- Use the command-line interface to initiate scraping, check status, and generate reports.
- Customize scraping parameters such as depth, rate limits, and input file paths through command-line flags.

## Testing

- Unit tests are located in the `tests/unit` directory.
- Integration tests can be found in `tests/integration`.
- End-to-end tests are available in `tests/e2e`.

Run tests using:
```
pytest
```

## Contributing

Contributions are welcome! Please open an issue or submit a pull request for any enhancements or bug fixes.

## License

This project is licensed under the MIT License. See the LICENSE file for details.