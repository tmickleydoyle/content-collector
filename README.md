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

----

## Output Example from Branch Walking Script

# Content Scraping Branch Report

**Run ID:** `402bf60b-d1cc-4fb8-ba68-1b773bf4e7e1`
**Input File:** `test_data/tech_blogs.csv`
**Branch:** 1 (Depth: 2 pages)
**Generated:** 2025-09-14 08:09:01

## Branch Overview

This report traces one complete scraping path from the root URL to the deepest discovered content.
Each section shows how content was extracted and what links were discovered to continue the crawl.

---

## Step 1: Depth 0

**URL:** https://react.dev/blog
**Status:** 200
**Domain:** react.dev
**Parent:** Root URL
**Content Length:** 93,996 bytes
**Scraped:** 2025-09-14 12:08:50

### Page Title
```
React Blog – React
```

### Meta Description
```
The library for web and native user interfaces
```

### Content Preview

```
Blog

React Blog

This blog is the official source for the updates from the React team. Anything important, including release notes or deprecation notices, will be posted here first.

You can also follow the @react.dev account on Bluesky, or @reactjs account on Twitter, but you won’t miss anything essential if you only read this blog.

React Labs: View Transitions, Activity, and more

April 23, 2025

In React Labs posts, we write about projects in active research and development. In this post, we’re sharing two new experimental features that are ready to try today, and sharing other areas we’re working on now …

Read more

React Compiler RC

April 21, 2025

We are releasing the compiler’s first Release Candidate (RC) today.

Read more

Sunsetting Create React App

February 14,... *(truncated)*
```

### Links Discovered (19 total)

- **https://react.dev/blog/2021/06/08/the-plan-for-react-18** - The Plan for React 18 – React
- **https://conf.react.dev/** - React Conf 2025 | October 7-8 | Henderson, Nevada & online | Join us!
- **https://react.dev/blog/2021/12/17/react-conf-2021-recap** - React Conf 2021 Recap – React
- **https://react.dev/blog/2023/05/03/react-canaries** - React Canaries: Enabling Incremental Feature Rollout Outside Meta – React
- **https://react.dev/blog/2022/03/08/react-18-upgrade-guide** - How to Upgrade to React 18 – React
- **https://react.dev/blog/2024/05/22/react-conf-2024-recap** - React Conf 2024 Recap – React
- **https://react.dev/blog/2024/12/05/react-19** - React v19 – React
- **https://react.dev/blog/2020/12/21/data-fetching-with-react-server-components** - Introducing Zero-Bundle-Size React Server Components – React
- **https://react.dev/blog/2024/10/21/react-compiler-beta-release** - React Compiler Beta Release – React
- **https://react.dev/blog/2023/03/22/react-labs-what-we-have-been-working-on-march-2023** - React Labs: What We've Been Working On – March 2023 – React
- *... and 9 more links*

**→ Next page discovered via link:**
- **https://react.dev/blog/2021/06/08/the-plan-for-react-18** - *The Plan for React 18 – React*

---

## Step 2: Depth 1

**URL:** https://react.dev/blog/2021/06/08/the-plan-for-react-18
**Status:** 200
**Domain:** react.dev
**Parent:** https://react.dev/blog
**Content Length:** 89,997 bytes
**Scraped:** 2025-09-14 12:08:50

### Page Title
```
The Plan for React 18 – React
```

### Meta Description
```
The library for web and native user interfaces
```

### Content Preview

```
Blog

The Plan for React 18

June 8, 2021 by Andrew Clark , Brian Vaughn , Christine Abernathy , Dan Abramov , Rachel Nabors , Rick Hanlon , Sebastian Markbåge , and Seth Webster

---

The React team is excited to share a few updates:

• We’ve started work on the React 18 release, which will be our next major version.

• We’ve created a Working Group to prepare the community for gradual adoption of new features in React 18.

• We’ve published a React 18 Alpha so that library authors can try it and provide feedback.

These updates are primarily aimed at maintainers of third-party libraries. If you’re learning, teaching, or using React to build user-facing applications, you can safely ignore this post. But you are welcome to follow the discussions in the React 18 Working Group if you’re... *(truncated)*
```

### Links Discovered (1 total)

- **[19 additional links not crawled due to limits]** - Links found but not crawled due to max-pages or depth limits

## Branch Summary

- **Total Pages:** 2
- **Maximum Depth Reached:** 1
- **Total Content:** 183,993 bytes
- **Domains Visited:** 1
- **Unique Domains:** react.dev

This branch represents one complete path through the content discovery process,
showing how the scraper follows links from page to page to build a comprehensive
content map of the target website(s).
