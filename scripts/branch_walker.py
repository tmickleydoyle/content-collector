#!/usr/bin/env python3
"""
Branch Walker - Visualize Scraping Content Lineage

This script walks through one complete branch of a scraping run, showing the
hierarchical story of how content was discovered and scraped. It creates a
markdown report that traces the path from root URL to deepest leaf, displaying
the actual content that was extracted at each step.

Usage:
    python scripts/branch_walker.py <run_id>
    python scripts/branch_walker.py <run_id> --output report.md
    python scripts/branch_walker.py <run_id> --branch-index 2
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import asyncpg

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from content_collector.config.settings import settings
from content_collector.storage.database import DatabaseManager
from content_collector.storage.models import Page, ScrapingRun


class BranchWalker:
    """Walks through scraping branches to show content lineage."""

    def __init__(self):
        self.db_manager = DatabaseManager()
        self.content_dir = Path("test_data/content")

    async def initialize(self):
        """Initialize database connection."""
        await self.db_manager.initialize()

    async def get_scraping_run(self, run_id: str) -> Optional[ScrapingRun]:
        """Get scraping run by ID."""
        async with self.db_manager.session() as session:
            from sqlalchemy import select

            result = await session.execute(
                select(ScrapingRun).where(ScrapingRun.id == run_id)
            )
            return result.scalar_one_or_none()

    async def get_all_pages(self, run_id: str) -> List[Page]:
        """Get all pages for a scraping run."""
        async with self.db_manager.session() as session:
            from sqlalchemy import select

            result = await session.execute(
                select(Page)
                .where(Page.scraping_run_id == run_id)
                .order_by(Page.depth, Page.created_at)
            )
            return result.scalars().all()

    def build_tree(self, pages: List[Page]) -> Dict:
        """Build hierarchical tree from pages."""
        pages_by_id = {page.id: page for page in pages}
        tree = {}
        roots = []

        for page in pages:
            if page.parent_id is None:
                roots.append(page)
            else:
                parent = pages_by_id.get(page.parent_id)
                if parent:
                    if not hasattr(parent, "_children"):
                        parent._children = []
                    parent._children.append(page)

        return roots

    def find_deepest_branches(self, roots: List[Page]) -> List[List[Page]]:
        """Find all branches that go to the maximum depth."""
        all_branches = []

        def traverse(page: Page, current_path: List[Page]):
            current_path = current_path + [page]

            if not hasattr(page, "_children") or not page._children:
                # This is a leaf node
                all_branches.append(current_path)
            else:
                # Continue traversing children
                for child in page._children:
                    traverse(child, current_path)

        for root in roots:
            traverse(root, [])

        # Find maximum depth
        if not all_branches:
            return []

        max_depth = max(len(branch) for branch in all_branches)
        deepest_branches = [
            branch for branch in all_branches if len(branch) == max_depth
        ]

        return deepest_branches

    async def load_page_content(self, page: Page, all_pages: List[Page]) -> Dict:
        """Load saved content for a page."""
        content_dir = self.content_dir / page.id

        if not content_dir.exists():
            return {
                "error": "Content directory not found",
                "title": page.title or "No title",
                "body": "Content not available",
                "links": [],
                "headers": {},
            }

        try:
            # Load body content
            body_file = content_dir / "body.txt"
            body = ""
            if body_file.exists():
                with open(body_file, "r", encoding="utf-8") as f:
                    body = f.read()

            # Load headers
            headers_file = content_dir / "headers.txt"
            headers = {}
            if headers_file.exists():
                with open(headers_file, "r", encoding="utf-8") as f:
                    for line in f:
                        if ":" in line:
                            key, value = line.strip().split(":", 1)
                            headers[key.strip()] = value.strip()

            # Reconstruct links from database relationships
            # Find all child pages of this page to represent discovered links
            links = []
            child_pages = [p for p in all_pages if p.parent_id == page.id]

            for child in child_pages:
                links.append(
                    {
                        "url": child.url,
                        "text": child.title or "Link discovered",
                        "was_crawled": True,
                    }
                )

            # Parse metadata for link count information
            metadata_file = content_dir / "metadata.txt"
            total_links_found = 0
            if metadata_file.exists():
                with open(metadata_file, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.startswith("Links Found:"):
                            try:
                                total_links_found = int(line.split(":")[1].strip())
                            except:
                                pass
                            break

            # If we found more links than children, add placeholder for undiscovered links
            if total_links_found > len(child_pages):
                remaining = total_links_found - len(child_pages)
                links.append(
                    {
                        "url": f"[{remaining} additional links not crawled due to limits]",
                        "text": f"Links found but not crawled due to max-pages or depth limits",
                        "was_crawled": False,
                    }
                )

            return {
                "title": page.title or "No title",
                "meta_description": page.meta_description,
                "body": body,
                "links": links,
                "headers": headers,
                "total_links_discovered": total_links_found,
            }

        except Exception as e:
            return {
                "error": f"Failed to load content: {str(e)}",
                "title": page.title or "No title",
                "body": "Content not available",
                "links": [],
                "headers": {},
            }

    def format_content_preview(self, content: str, max_length: int = 500) -> str:
        """Format content for preview with truncation."""
        if not content:
            return "*No content*"

        # Clean up content
        cleaned = content.strip()
        if not cleaned:
            return "*Empty content*"

        # Truncate if too long
        if len(cleaned) > max_length:
            truncated = cleaned[:max_length].rsplit(" ", 1)[0]
            return f"{truncated}... *(truncated)*"

        return cleaned

    async def generate_branch_markdown(
        self,
        run: ScrapingRun,
        branch: List[Page],
        branch_index: int,
        all_pages: List[Page],
    ) -> str:
        """Generate markdown report for a single branch."""

        markdown_lines = [
            f"# Content Scraping Branch Report",
            f"",
            f"**Run ID:** `{run.id}`",
            f"**Input File:** `{run.input_file}`",
            f"**Branch:** {branch_index + 1} (Depth: {len(branch)} pages)",
            f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"",
            f"## Branch Overview",
            f"",
            f"This report traces one complete scraping path from the root URL to the deepest discovered content.",
            f"Each section shows how content was extracted and what links were discovered to continue the crawl.",
            f"",
            f"---",
            f"",
        ]

        for i, page in enumerate(branch):
            content_data = await self.load_page_content(page, all_pages)

            # Page header
            markdown_lines.extend(
                [
                    f"## Step {i + 1}: Depth {page.depth}",
                    f"",
                    f"**URL:** {page.url}",
                    f"**Status:** {page.status_code}",
                    f"**Domain:** {page.domain}",
                    f"**Parent:** {branch[i-1].url if i > 0 else 'Root URL'}",
                    (
                        f"**Content Length:** {page.content_length:,} bytes"
                        if page.content_length
                        else "**Content Length:** Unknown"
                    ),
                    f"**Scraped:** {page.created_at.strftime('%Y-%m-%d %H:%M:%S')}",
                    f"",
                ]
            )

            # Page title and meta
            if content_data.get("title"):
                markdown_lines.extend(
                    [f"### Page Title", f"```", f"{content_data['title']}", f"```", f""]
                )

            if content_data.get("meta_description"):
                markdown_lines.extend(
                    [
                        f"### Meta Description",
                        f"```",
                        f"{content_data['meta_description']}",
                        f"```",
                        f"",
                    ]
                )

            # Content preview
            body_content = content_data.get("body", "")
            markdown_lines.extend(
                [
                    f"### Content Preview",
                    f"",
                    f"```",
                    f"{self.format_content_preview(body_content, 800)}",
                    f"```",
                    f"",
                ]
            )

            # Links discovered
            links = content_data.get("links", [])
            if links:
                markdown_lines.extend(
                    [f"### Links Discovered ({len(links)} total)", f""]
                )

                # Show first 10 links
                for j, link in enumerate(links[:10]):
                    link_url = link.get("url", "No URL")
                    link_text = link.get("text", "No text").strip()[:100]
                    markdown_lines.append(f"- **{link_url}** - {link_text}")

                if len(links) > 10:
                    markdown_lines.append(f"- *... and {len(links) - 10} more links*")

                markdown_lines.append("")

                # Show which link led to the next page
                if i < len(branch) - 1:
                    next_url = branch[i + 1].url
                    leading_link = next(
                        (link for link in links if link.get("url") == next_url), None
                    )
                    if leading_link:
                        markdown_lines.extend(
                            [
                                f"**→ Next page discovered via link:**",
                                f"- **{leading_link.get('url')}** - *{leading_link.get('text', 'No text').strip()[:200]}*",
                                f"",
                            ]
                        )
            else:
                markdown_lines.extend(
                    [f"### Links Discovered", f"*No links found on this page*", f""]
                )

            # Headers (show key ones)
            headers = content_data.get("headers", {})
            if headers:
                key_headers = {
                    k: v
                    for k, v in headers.items()
                    if k.lower()
                    in ["content-type", "content-length", "server", "x-powered-by"]
                }
                if key_headers:
                    markdown_lines.extend([f"### Key Response Headers", f""])
                    for header, value in key_headers.items():
                        markdown_lines.append(f"- **{header}:** {value}")
                    markdown_lines.append("")

            # Error information if any
            if page.last_error:
                markdown_lines.extend(
                    [f"### Errors", f"```", f"{page.last_error}", f"```", f""]
                )

            if i < len(branch) - 1:
                markdown_lines.extend([f"---", f""])

        # Branch summary
        markdown_lines.extend(
            [
                f"## Branch Summary",
                f"",
                f"- **Total Pages:** {len(branch)}",
                f"- **Maximum Depth Reached:** {branch[-1].depth}",
                f"- **Total Content:** {sum(p.content_length or 0 for p in branch):,} bytes",
                f"- **Domains Visited:** {len(set(p.domain for p in branch))}",
                f"- **Unique Domains:** {', '.join(sorted(set(p.domain for p in branch)))}",
                f"",
                f"This branch represents one complete path through the content discovery process,",
                f"showing how the scraper follows links from page to page to build a comprehensive",
                f"content map of the target website(s).",
            ]
        )

        return "\n".join(markdown_lines)

    async def generate_report(
        self, run_id: str, branch_index: int = 0, output_file: Optional[str] = None
    ) -> str:
        """Generate branch walker report."""

        # Get run information
        run = await self.get_scraping_run(run_id)
        if not run:
            raise ValueError(f"Scraping run {run_id} not found")

        # Get all pages
        pages = await self.get_all_pages(run_id)
        if not pages:
            raise ValueError(f"No pages found for run {run_id}")

        # Build tree and find deepest branches
        roots = self.build_tree(pages)
        branches = self.find_deepest_branches(roots)

        if not branches:
            raise ValueError(f"No branches found for run {run_id}")

        if branch_index >= len(branches):
            raise ValueError(
                f"Branch index {branch_index} not found. Available branches: 0-{len(branches)-1}"
            )

        # Generate report
        selected_branch = branches[branch_index]
        markdown_content = await self.generate_branch_markdown(
            run, selected_branch, branch_index, pages
        )

        # Output to file or stdout
        if output_file:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(markdown_content)
            return f"Report saved to {output_path}"
        else:
            print(markdown_content)
            return "Report printed to stdout"


async def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Walk through a scraping branch to visualize content lineage"
    )
    parser.add_argument("run_id", help="Scraping run ID to analyze")
    parser.add_argument(
        "--branch-index",
        "-b",
        type=int,
        default=0,
        help="Which branch to analyze (default: 0, the first deepest branch)",
    )
    parser.add_argument(
        "--output", "-o", help="Output markdown file (default: print to stdout)"
    )
    parser.add_argument(
        "--list-branches",
        "-l",
        action="store_true",
        help="List available branches without generating report",
    )

    args = parser.parse_args()

    try:
        walker = BranchWalker()
        await walker.initialize()

        if args.list_branches:
            # List available branches
            run = await walker.get_scraping_run(args.run_id)
            if not run:
                print(f"❌ Scraping run {args.run_id} not found")
                return 1

            pages = await walker.get_all_pages(args.run_id)
            if not pages:
                print(f"❌ No pages found for run {args.run_id}")
                return 1

            roots = walker.build_tree(pages)
            branches = walker.find_deepest_branches(roots)

            print(f"📊 Available branches for run {args.run_id}:")
            print(f"   Run: {run.input_file}")
            print(f"   Total pages: {len(pages)}")
            print(f"   Root URLs: {len(roots)}")
            print(f"   Deepest branches: {len(branches)}")
            print()

            for i, branch in enumerate(branches):
                print(f"   Branch {i}: {len(branch)} pages (depth {branch[-1].depth})")
                print(f"     Root: {branch[0].url}")
                print(f"     Leaf: {branch[-1].url}")
                print()

            return 0

        # Generate report
        result = await walker.generate_report(
            args.run_id, args.branch_index, args.output
        )

        if args.output:
            print(f"✅ {result}")

        return 0

    except Exception as e:
        print(f"❌ Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
