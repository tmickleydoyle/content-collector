## Project Overview

**Objective:** Build a scalable, maintainable web scraping application that:

* Reads lists of URLs from CSV files referenced in a `.txt` file.
* Scrapes page headers, body content, metadata, and follows links recursively while tracking lineage.
* Stores metadata (lineage, timestamps, status codes, retry history) in PostgreSQL.
* Saves page content (header.txt, body.txt, raw HTML) in a structured file system or object storage.
* Generates analytics and reports at the end of each run.

**Audience:** Engineers (junior to senior), DevOps, and stakeholders needing a reliable data ingestion pipeline.

---

## 1. Functional Components

### 1.1 Input Processing

* **Parser**: Read `.txt` for CSV paths; load and deduplicate URLs.
* **Validator**: Ensure URLs are well-formed and reachable.

### 1.2 Scraper Engine

* **Fetcher**: Async HTTP client (e.g., `aiohttp`) with concurrency control and rate-limiting per domain.
* **Parser**: Extract `<header>`, `<body>`, `<h1>`, `<h2>`, `<title>`, meta tags, and outbound links using `BeautifulSoup` or `selectolax`.
* **Lineage Tracker**: Record parent → child URL relationships to build a graph.

### 1.3 Storage Layer

* **Metadata (PostgreSQL)**:

  * Tables: `pages`, `retries`, `domains`
  * Key fields: `id (UUID)`, `url`, `parent_id`, `status_code`, `scraped_at`, `content_hash`, `header_path`, `body_path`, `raw_html_path`, `depth`, retry counts, error codes.
  * Migrations: Use Alembic for versioning.
* **Content Files**:

  * Directory structure by UUID or hash: `/data/content/{id}/header.txt`, `body.txt`, `raw.html`
  * Optional cold storage: Migrate old files to S3/MinIO based on policy.

### 1.4 Retry & Error Handling

* **Retry Policy**: Exponential backoff with jitter; configurable max attempts.
* **Circuit Breaker**: Pause scraping on repeated failures per domain.
* **Transactional Writes**: Two-phase commit or staging table for atomic metadata + file writes.

### 1.5 Concurrency & Scaling

* **Adaptive Concurrency**: Auto‑tune per‑domain worker pools based on response times and `robots.txt` crawl-delay.
* **Distributed Tasks**: Celery (Redis/RabbitMQ) or Kubernetes jobs for large-scale crawling.
* **Back‑pressure**: Bounded queues and semaphores to prevent resource exhaustion.

### 1.6 CLI & Administrative Interface

* Commands: `init`, `run`, `status`, `report`, `cleanup`
* Flags: depth, rate‑limit, max‑pages, input file path, output directory.
* Logging: Structured JSON logs with correlation IDs; log levels (INFO, WARN, ERROR).

---

## 2. Non‑Functional Requirements

| Category            | Requirements                                                    |
| ------------------- | --------------------------------------------------------------- |
| **Performance**     | ≥ 100 pages/sec (aggregate); sub‑second median fetch latency    |
| **Availability**    | 99.5% uptime; graceful degradation on third‑party downtime      |
| **Scalability**     | Horizontal scaling via containers; stateless workers            |
| **Security**        | Env‑var secrets; input sanitization; OWASP scanning             |
| **Maintainability** | Layered architecture; clear interfaces; type hints              |
| **Supportability**  | Health checks; runbooks; alerts on high error or low throughput |

---

## 3. Tech Stack & Tools

| Layer         | Technology / Library                      |
| ------------- | ----------------------------------------- |
| Language      | Python 3.10+                              |
| HTTP Client   | `aiohttp`, `httpx`                        |
| HTML Parsing  | `selectolax`, `BeautifulSoup`, `lxml`     |
| Async Queue   | `asyncio`, Celery + Redis/RabbitMQ        |
| DB + ORM      | PostgreSQL, SQLAlchemy, Alembic           |
| File Storage  | Local FS, optionally S3/MinIO             |
| CLI Framework | Typer or Click                            |
| CI/CD         | GitHub Actions / GitLab CI + Docker       |
| Testing       | pytest, responses, Docker Compose for E2E |
| Monitoring    | Prometheus + Grafana or equivalent        |
| Lint & Format | Black, isort, Flake8                      |

---

## 4. Database Schema (Draft)

```sql
CREATE TABLE pages (
  id UUID PRIMARY KEY,
  url TEXT UNIQUE NOT NULL,
  parent_id UUID REFERENCES pages(id),
  domain TEXT NOT NULL,
  status_code INT,
  scraped_at TIMESTAMPTZ NOT NULL,
  depth INT NOT NULL,
  content_hash TEXT,
  header_path TEXT,
  body_path TEXT,
  raw_html_path TEXT,
  retry_count INT DEFAULT 0,
  last_error TEXT
);

CREATE INDEX idx_pages_scraped_at ON pages(scraped_at);
CREATE INDEX idx_pages_parent_id ON pages(parent_id);
```

---

## 5. Testing & QA

* **Unit Tests**: Parser, extractor, URL normalizer, storage utilities.
* **Integration Tests**: Local HTTP server with varied page scenarios; verify DB + FS state.
* **E2E Tests**: Docker Compose stack → assert full workflow and analytics output.
* **Coverage**: ≥ 90% on core modules; enforce in CI.

---

## 6. Analytics & Reporting

At each run completion:

1. **Summary Report (JSON/CSV)**:

   * Total pages scraped, success vs. failures
   * Pages/sec, avg response time
   * Domains crawled, depth distribution
2. **Error Dashboard**:

   * Top failed URLs/domains, error types, retry outcomes
3. **Storage Usage**:

   * Total bytes in file system, rows in DB
4. **Performance Metrics**:

   * CPU/memory trends (if instrumented)

Optionally push metrics to Prometheus or generate a human‑readable HTML report.

---

## 7. Project Roadmap & Milestones

| Sprint | Deliverables                                            | Duration |
| ------ | ------------------------------------------------------- | -------- |
| 1      | Repo setup, CI/CD, basic CLI, input parser              | 1 week   |
| 2      | Core scraper engine, single‑page fetch, metadata writes | 2 weeks  |
| 3      | Recursive linking, lineage graph, file storage          | 2 weeks  |
| 4      | Retry logic, adaptive concurrency, circuit breaker      | 2 weeks  |
| 5      | Testing suite (unit, integration, E2E)                  | 2 weeks  |
| 6      | Analytics/reporting, monitoring integration             | 1 week   |
| 7      | Documentation, runbooks, security hardening, production | 1 week   |

---

## 8. Checklist Against Best Practices

* **Readability & Simplicity:** Small functions, clear names, DRY.
* **Testing:** Automated unit, integration, E2E; > 90% coverage.
* **Tooling:** Pre‑commit hooks, linters, CI gates.
* **Structure & Dependencies:** Standard layout (`src/`, `tests/`), pinned deps.
* **Documentation:** README, docstrings, changelog.
* **Version Control:** Protected `main`, feature branches, PR reviews.
* **Architecture:** Layered, stateless workers, explicit interfaces.
* **Error & Logging:** Structured logs, graceful degradation.
* **Security:** Env‑var secrets, input validation, regular scans.
* **Support:** Health checks, runbooks, on‑call guides.

---

**Next:** Review and adjust priorities or drill into any section for detailed design or code templates.
