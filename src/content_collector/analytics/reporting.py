"""Analytics and reporting for scraping operations."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import desc, func
from sqlalchemy.orm import selectinload

from content_collector.config.settings import settings
from content_collector.storage.database import db_manager
from content_collector.storage.models import Domain, Page, ScrapingRun

logger = structlog.get_logger(__name__)


class ReportGenerator:
    """Generate analytics reports for scraping operations."""

    def __init__(self):
        self.logger = logger.bind(component="reporting")

    async def generate_run_report(self, run_id: str) -> Dict[str, Any]:
        """Generate a comprehensive report for a specific scraping run."""
        try:
            async with db_manager.session() as session:
                run = await session.get(ScrapingRun, run_id)
                if not run:
                    raise ValueError(f"Run {run_id} not found")

                from sqlalchemy import select

                pages_query = select(Page).where(Page.scraping_run_id == run_id)
                pages_result = await session.execute(pages_query)
                pages = pages_result.scalars().all()

                total_pages = len(pages)
                success_count = len([p for p in pages if p.status_code == 200])
                failure_count = total_pages - success_count

                domain_counts = {}
                for page in pages:
                    domain_counts[page.domain] = domain_counts.get(page.domain, 0) + 1

                status_counts = {}
                for page in pages:
                    status_counts[page.status_code] = (
                        status_counts.get(page.status_code, 0) + 1
                    )

                failed_urls = [
                    {
                        "url": p.url,
                        "status_code": p.status_code,
                        "error": p.last_error,
                        "retry_count": p.retry_count,
                    }
                    for p in pages
                    if p.status_code != 200
                ]

                total_content_length = sum(p.content_length or 0 for p in pages)
                avg_content_length = (
                    total_content_length / total_pages if total_pages > 0 else 0
                )

                report = {
                    "run_info": {
                        "run_id": run_id,
                        "status": run.status,
                        "start_time": (
                            run.created_at.isoformat() if run.created_at else None
                        ),
                        "end_time": (
                            run.updated_at.isoformat() if run.updated_at else None
                        ),
                        "input_file": run.input_file,
                        "max_depth": run.max_depth,
                    },
                    "summary": {
                        "total_pages": total_pages,
                        "success_count": success_count,
                        "failure_count": failure_count,
                        "success_rate": (
                            (success_count / total_pages * 100)
                            if total_pages > 0
                            else 0
                        ),
                        "total_content_bytes": total_content_length,
                        "avg_content_length": avg_content_length,
                    },
                    "domains": {
                        "total_domains": len(domain_counts),
                        "distribution": dict(
                            sorted(
                                domain_counts.items(), key=lambda x: x[1], reverse=True
                            )
                        ),
                    },
                    "status_codes": status_counts,
                    "failures": {"count": failure_count, "details": failed_urls[:10]},
                }

                return report

        except Exception as e:
            self.logger.error(
                "Failed to generate run report", run_id=run_id, error=str(e)
            )
            raise

    async def generate_tree_report(self, run_id: str) -> Dict[str, Any]:
        """Generate a tree structure report showing parent-child URL relationships."""
        try:
            async with db_manager.session() as session:
                run = await session.get(ScrapingRun, run_id)
                if not run:
                    raise ValueError(f"Run {run_id} not found")

                from sqlalchemy import select

                pages_query = select(Page).where(Page.scraping_run_id == run_id)
                pages_result = await session.execute(pages_query)
                pages = pages_result.scalars().all()

                # Create a mapping of page ID to page for easy lookup
                pages_by_id = {page.id: page for page in pages}
                pages_by_url = {page.url: page for page in pages}

                # Build the tree structure
                tree_roots = []
                all_nodes = {}

                for page in pages:
                    node = {
                        "id": page.id,
                        "url": page.url,
                        "domain": page.domain,
                        "status_code": page.status_code,
                        "depth": page.depth,
                        "title": page.title,
                        "content_type": page.content_type,
                        "content_length": page.content_length,
                        "retry_count": page.retry_count,
                        "last_error": page.last_error,
                        "referer_url": page.referer_url,
                        "created_at": (
                            page.created_at.isoformat() if page.created_at else None
                        ),
                        "children": [],
                    }
                    all_nodes[page.id] = node

                # Try to build parent-child relationships
                # First attempt: Use parent_id if available
                parent_child_found = False
                for page in pages:
                    if page.parent_id and page.parent_id in all_nodes:
                        all_nodes[page.parent_id]["children"].append(all_nodes[page.id])
                        parent_child_found = True

                # If no parent_id relationships found, build relationships based on depth and URL patterns
                if not parent_child_found:
                    tree_roots = []
                    depth_groups = {}

                    # Group pages by depth
                    for page in pages:
                        if page.depth not in depth_groups:
                            depth_groups[page.depth] = []
                        depth_groups[page.depth].append(page)

                    # Start with depth 0 as roots
                    if 0 in depth_groups:
                        for page in depth_groups[0]:
                            tree_roots.append(all_nodes[page.id])

                    # Build relationships based on URL hierarchy and depth
                    for depth in sorted(depth_groups.keys())[1:]:  # Skip depth 0
                        for page in depth_groups[depth]:
                            # First try referer_url
                            parent_found = False
                            if page.referer_url and page.referer_url in pages_by_url:
                                parent_page_id = pages_by_url[page.referer_url].id
                                if parent_page_id in all_nodes:
                                    all_nodes[parent_page_id]["children"].append(
                                        all_nodes[page.id]
                                    )
                                    parent_found = True

                            # If no referer relationship found, try to find best parent from previous depth
                            if (
                                not parent_found
                                and depth > 0
                                and (depth - 1) in depth_groups
                            ):
                                best_parent = None
                                best_score = 0

                                for potential_parent in depth_groups[depth - 1]:
                                    if potential_parent.domain == page.domain:
                                        # Calculate URL path containment (protocol-agnostic)
                                        parent_url = (
                                            potential_parent.url.replace("https://", "")
                                            .replace("http://", "")
                                            .rstrip("/")
                                        )
                                        page_url = (
                                            page.url.replace("https://", "")
                                            .replace("http://", "")
                                            .rstrip("/")
                                        )

                                        # Check if page URL starts with parent URL (path containment)
                                        if (
                                            page_url.startswith(parent_url)
                                            and page_url != parent_url
                                        ):
                                            # Prefer more specific matches (longer parent paths)
                                            score = len(parent_url)
                                            if score > best_score:
                                                best_score = score
                                                best_parent = potential_parent

                                if best_parent:
                                    all_nodes[best_parent.id]["children"].append(
                                        all_nodes[page.id]
                                    )
                                    parent_found = True

                            # If still no parent found, make it a root (only for reasonable cases)
                            if not parent_found:
                                # Only add as root if it's depth 1 or a reasonable standalone page
                                if (
                                    depth == 1 or len(tree_roots) < 20
                                ):  # Limit standalone roots
                                    tree_roots.append(all_nodes[page.id])
                                # Otherwise, attach to first available root
                                elif tree_roots:
                                    tree_roots[0]["children"].append(all_nodes[page.id])
                else:
                    # parent_id relationships were found, identify roots
                    for page in pages:
                        if not page.parent_id:
                            tree_roots.append(all_nodes[page.id])

                # If still no structure found, fallback to depth-based grouping
                if not tree_roots and not any(
                    node["children"] for node in all_nodes.values()
                ):
                    # Group by depth and show limited roots
                    depth_0_pages = [page for page in pages if page.depth == 0]
                    if depth_0_pages:
                        for page in depth_0_pages:  # Show all depth 0 pages as roots
                            tree_roots.append(all_nodes[page.id])
                    else:
                        # No depth 0 pages, show first few pages as roots
                        sorted_pages = sorted(pages, key=lambda p: (p.depth, p.url))
                        for page in sorted_pages[
                            :50
                        ]:  # Increase limit to show more structure
                            tree_roots.append(all_nodes[page.id])

                # Sort tree roots and children by URL for consistency
                tree_roots.sort(key=lambda x: x["url"])
                self._sort_tree_children(tree_roots)

                # Generate statistics
                total_pages = len(pages)
                success_count = len([p for p in pages if p.status_code == 200])
                max_depth = max([p.depth for p in pages]) if pages else 0

                # Count actual relationships found
                total_children = sum(
                    len(node["children"]) for node in all_nodes.values()
                )
                relationship_type = (
                    "parent_id"
                    if parent_child_found
                    else "inferred" if total_children > 0 else "flat"
                )

                tree_report = {
                    "run_info": {
                        "run_id": run_id,
                        "status": run.status,
                        "start_time": (
                            run.created_at.isoformat() if run.created_at else None
                        ),
                        "end_time": (
                            run.updated_at.isoformat() if run.updated_at else None
                        ),
                        "input_file": run.input_file,
                        "max_depth_configured": run.max_depth,
                        "max_depth_actual": max_depth,
                        "relationship_type": relationship_type,
                    },
                    "tree_summary": {
                        "total_pages": total_pages,
                        "root_pages": len(tree_roots),
                        "success_count": success_count,
                        "failure_count": total_pages - success_count,
                        "success_rate": (
                            (success_count / total_pages * 100)
                            if total_pages > 0
                            else 0
                        ),
                        "max_depth_reached": max_depth,
                        "total_relationships": total_children,
                        "relationship_type": relationship_type,
                    },
                    "tree": tree_roots,
                }

                return tree_report

        except Exception as e:
            self.logger.error(
                "Failed to generate tree report", run_id=run_id, error=str(e)
            )
            raise

    def _sort_tree_children(self, nodes: List[Dict[str, Any]]) -> None:
        """Recursively sort children in tree nodes by URL."""
        for node in nodes:
            if node["children"]:
                node["children"].sort(key=lambda x: x["url"])
                self._sort_tree_children(node["children"])

    def generate_tree_text(
        self, tree_data: Dict[str, Any], show_details: bool = True
    ) -> str:
        """Generate a text representation of the tree structure."""
        lines = []

        # Add header information
        run_info = tree_data["run_info"]
        summary = tree_data["tree_summary"]

        lines.append("=" * 80)
        lines.append(f"CONTENT COLLECTOR - TREE REPORT")
        lines.append("=" * 80)
        lines.append(f"Run ID: {run_info['run_id']}")
        lines.append(f"Status: {run_info['status']}")
        lines.append(f"Input File: {run_info['input_file']}")
        lines.append(f"Start Time: {run_info['start_time']}")
        lines.append(f"End Time: {run_info['end_time']}")
        lines.append(f"Max Depth Configured: {run_info['max_depth_configured']}")
        lines.append(f"Max Depth Reached: {run_info['max_depth_actual']}")
        lines.append("")
        lines.append("SUMMARY:")
        lines.append(f"  Total Pages: {summary['total_pages']}")
        lines.append(f"  Root Pages: {summary['root_pages']}")
        lines.append(f"  Success Count: {summary['success_count']}")
        lines.append(f"  Failure Count: {summary['failure_count']}")
        lines.append(f"  Success Rate: {summary['success_rate']:.1f}%")
        lines.append("")
        lines.append("TREE STRUCTURE:")
        lines.append("-" * 80)

        # Generate tree structure
        for root in tree_data["tree"]:
            self._add_tree_node_text(lines, root, "", True, show_details)

        lines.append("-" * 80)
        lines.append(f"Generated: {datetime.utcnow().isoformat()}")

        return "\n".join(lines)

    def _add_tree_node_text(
        self,
        lines: List[str],
        node: Dict[str, Any],
        prefix: str,
        is_last: bool,
        show_details: bool,
    ) -> None:
        """Add a tree node and its children to the text lines."""
        # Create the tree connector
        connector = "└── " if is_last else "├── "

        # Format the node information
        url = node["url"]
        status = node["status_code"]
        depth = node["depth"]

        # Status indicator
        status_icon = "✅" if status == 200 else "❌"

        # Basic line
        basic_line = f"{prefix}{connector}{status_icon} [{depth}] {url}"

        if show_details:
            # Add additional details
            details = []
            if node["title"]:
                details.append(f"Title: {node['title'][:50]}...")
            if node["content_type"]:
                details.append(f"Type: {node['content_type']}")
            if node["content_length"]:
                details.append(f"Size: {node['content_length']} bytes")
            if status != 200 and node["last_error"]:
                details.append(f"Error: {node['last_error'][:100]}...")

            lines.append(basic_line)
            if details:
                detail_prefix = prefix + ("    " if is_last else "│   ")
                for detail in details:
                    lines.append(f"{detail_prefix}   {detail}")
        else:
            lines.append(basic_line)

        # Add children
        children = node["children"]
        child_prefix = prefix + ("    " if is_last else "│   ")

        for i, child in enumerate(children):
            child_is_last = i == len(children) - 1
            self._add_tree_node_text(
                lines, child, child_prefix, child_is_last, show_details
            )

    async def save_tree_report(
        self, tree_data: Dict[str, Any], filename: str, format_type: str = "json"
    ) -> Path:
        """Save tree report to file in specified format."""
        try:
            reports_dir = settings.storage.reports_dir
            reports_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

            if format_type.lower() == "txt":
                filename_with_ext = f"{timestamp}_{filename}.txt"
                file_path = reports_dir / filename_with_ext

                tree_text = self.generate_tree_text(tree_data, show_details=True)

                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(tree_text)
            else:
                filename_with_ext = f"{timestamp}_{filename}.json"
                file_path = reports_dir / filename_with_ext

                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(tree_data, f, indent=2, ensure_ascii=False)

            self.logger.info(
                "Tree report saved", file_path=str(file_path), format=format_type
            )
            return file_path

        except Exception as e:
            self.logger.error("Failed to save tree report", error=str(e))
            raise

    async def generate_tree_report(self, run_id: str) -> Dict[str, Any]:
        """Generate a tree structure report showing parent-child URL relationships."""
        try:
            async with db_manager.session() as session:
                run = await session.get(ScrapingRun, run_id)
                if not run:
                    raise ValueError(f"Run {run_id} not found")

                from sqlalchemy import select

                pages_query = select(Page).where(Page.scraping_run_id == run_id)
                pages_result = await session.execute(pages_query)
                pages = pages_result.scalars().all()

                # Create a mapping of page ID to page for easy lookup
                pages_by_id = {page.id: page for page in pages}

                # Build the tree structure
                tree_roots = []
                all_nodes = {}

                for page in pages:
                    node = {
                        "id": page.id,
                        "url": page.url,
                        "domain": page.domain,
                        "status_code": page.status_code,
                        "depth": page.depth,
                        "title": page.title,
                        "content_type": page.content_type,
                        "content_length": page.content_length,
                        "retry_count": page.retry_count,
                        "last_error": page.last_error,
                        "created_at": (
                            page.created_at.isoformat() if page.created_at else None
                        ),
                        "children": [],
                    }
                    all_nodes[page.id] = node

                # Build parent-child relationships
                for page in pages:
                    if page.parent_id and page.parent_id in all_nodes:
                        # Add this page as a child of its parent
                        all_nodes[page.parent_id]["children"].append(all_nodes[page.id])
                    else:
                        # This is a root node (no parent)
                        tree_roots.append(all_nodes[page.id])

                # Sort tree roots and children by URL for consistency
                tree_roots.sort(key=lambda x: x["url"])
                self._sort_tree_children(tree_roots)

                # Generate statistics
                total_pages = len(pages)
                success_count = len([p for p in pages if p.status_code == 200])
                max_depth = max([p.depth for p in pages]) if pages else 0

                tree_report = {
                    "run_info": {
                        "run_id": run_id,
                        "status": run.status,
                        "start_time": (
                            run.created_at.isoformat() if run.created_at else None
                        ),
                        "end_time": (
                            run.updated_at.isoformat() if run.updated_at else None
                        ),
                        "input_file": run.input_file,
                        "max_depth_configured": run.max_depth,
                        "max_depth_actual": max_depth,
                    },
                    "tree_summary": {
                        "total_pages": total_pages,
                        "root_pages": len(tree_roots),
                        "success_count": success_count,
                        "failure_count": total_pages - success_count,
                        "success_rate": (
                            (success_count / total_pages * 100)
                            if total_pages > 0
                            else 0
                        ),
                        "max_depth_reached": max_depth,
                    },
                    "tree": tree_roots,
                }

                return tree_report

        except Exception as e:
            self.logger.error(
                "Failed to generate tree report", run_id=run_id, error=str(e)
            )
            raise

    def _sort_tree_children(self, nodes: List[Dict[str, Any]]) -> None:
        """Recursively sort children in tree nodes by URL."""
        for node in nodes:
            if node["children"]:
                node["children"].sort(key=lambda x: x["url"])
                self._sort_tree_children(node["children"])

    def generate_tree_text(
        self, tree_data: Dict[str, Any], show_details: bool = True
    ) -> str:
        """Generate a text representation of the tree structure."""
        lines = []

        # Add header information
        run_info = tree_data["run_info"]
        summary = tree_data["tree_summary"]

        lines.append("=" * 80)
        lines.append(f"CONTENT COLLECTOR - TREE REPORT")
        lines.append("=" * 80)
        lines.append(f"Run ID: {run_info['run_id']}")
        lines.append(f"Status: {run_info['status']}")
        lines.append(f"Input File: {run_info['input_file']}")
        lines.append(f"Start Time: {run_info['start_time']}")
        lines.append(f"End Time: {run_info['end_time']}")
        lines.append(f"Max Depth Configured: {run_info['max_depth_configured']}")
        lines.append(f"Max Depth Reached: {run_info['max_depth_actual']}")
        lines.append("")
        lines.append("SUMMARY:")
        lines.append(f"  Total Pages: {summary['total_pages']}")
        lines.append(f"  Root Pages: {summary['root_pages']}")
        lines.append(f"  Success Count: {summary['success_count']}")
        lines.append(f"  Failure Count: {summary['failure_count']}")
        lines.append(f"  Success Rate: {summary['success_rate']:.1f}%")
        lines.append("")
        lines.append("TREE STRUCTURE:")
        lines.append("-" * 80)

        # Generate tree structure
        for root in tree_data["tree"]:
            self._add_tree_node_text(lines, root, "", True, show_details)

        lines.append("-" * 80)
        lines.append(f"Generated: {datetime.utcnow().isoformat()}")

        return "\n".join(lines)

    def _add_tree_node_text(
        self,
        lines: List[str],
        node: Dict[str, Any],
        prefix: str,
        is_last: bool,
        show_details: bool,
    ) -> None:
        """Add a tree node and its children to the text lines."""
        # Create the tree connector
        connector = "└── " if is_last else "├── "

        # Format the node information
        url = node["url"]
        status = node["status_code"]
        depth = node["depth"]

        # Status indicator
        status_icon = "✅" if status == 200 else "❌"

        # Basic line
        basic_line = f"{prefix}{connector}{status_icon} [{depth}] {url}"

        if show_details:
            # Add additional details
            details = []
            if node["title"]:
                details.append(f"Title: {node['title'][:50]}...")
            if node["content_type"]:
                details.append(f"Type: {node['content_type']}")
            if node["content_length"]:
                details.append(f"Size: {node['content_length']} bytes")
            if status != 200 and node["last_error"]:
                details.append(f"Error: {node['last_error'][:100]}...")

            lines.append(basic_line)
            if details:
                detail_prefix = prefix + ("    " if is_last else "│   ")
                for detail in details:
                    lines.append(f"{detail_prefix}   {detail}")
        else:
            lines.append(basic_line)

        # Add children
        children = node["children"]
        child_prefix = prefix + ("    " if is_last else "│   ")

        for i, child in enumerate(children):
            child_is_last = i == len(children) - 1
            self._add_tree_node_text(
                lines, child, child_prefix, child_is_last, show_details
            )

    async def save_tree_report(
        self, tree_data: Dict[str, Any], filename: str, format_type: str = "json"
    ) -> Path:
        """Save tree report to file in specified format."""
        try:
            reports_dir = settings.storage.reports_dir
            reports_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

            if format_type.lower() == "txt":
                filename_with_ext = f"{timestamp}_{filename}.txt"
                file_path = reports_dir / filename_with_ext

                tree_text = self.generate_tree_text(tree_data, show_details=True)

                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(tree_text)
            else:
                filename_with_ext = f"{timestamp}_{filename}.json"
                file_path = reports_dir / filename_with_ext

                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(tree_data, f, indent=2, ensure_ascii=False)

            self.logger.info(
                "Tree report saved", file_path=str(file_path), format=format_type
            )
            return file_path

        except Exception as e:
            self.logger.error("Failed to save tree report", error=str(e))
            raise


report_generator = ReportGenerator()
