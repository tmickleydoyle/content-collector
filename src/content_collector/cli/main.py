"""Command-line interface for the content collector."""

import asyncio
from pathlib import Path
from typing import Optional

import structlog
import typer
from rich.console import Console
from rich.table import Table

from content_collector.analytics.reporting import report_generator
from content_collector.core.content_parser import ContentParser
from content_collector.storage.database import db_manager

app = typer.Typer(help="Content Collector - Scalable web scraping tool")
console = Console()
logger = structlog.get_logger()


@app.command()
def init(
    create_db: bool = typer.Option(
        True, "--create-db/--no-create-db", help="Create database tables"
    )
):
    """Initialize the content collector system."""
    console.print("🚀 Initializing Content Collector...", style="bold blue")

    async def _init():
        try:
            await db_manager.initialize()
            console.print("✅ Database connection established", style="green")

            if create_db:
                await db_manager.create_tables()
                console.print("✅ Database tables created", style="green")

            healthy = await db_manager.health_check()
            if healthy:
                console.print("✅ Database health check passed", style="green")
            else:
                console.print("❌ Database health check failed", style="red")

        except Exception as e:
            console.print(f"❌ Initialization failed: {e}", style="red")
            raise typer.Exit(1)
        finally:
            await db_manager.close()

    asyncio.run(_init())
    console.print("🎉 Content Collector initialized successfully!", style="bold green")


@app.command()
def status(
    run_id: Optional[str] = typer.Option(
        None, "--run-id", help="Specific run ID to check"
    )
):
    """Show the current status of scraping runs."""
    console.print("📊 Checking scraper status...", style="bold blue")

    async def _status():
        try:
            await db_manager.initialize()

            if run_id:
                async with db_manager.session() as session:
                    from content_collector.storage.models import ScrapingRun

                    run = await session.get(ScrapingRun, run_id)
                    if run:
                        table = Table(title=f"Run Status: {run_id}")
                        table.add_column("Field", style="cyan")
                        table.add_column("Value", style="white")

                        table.add_row("Status", run.status)
                        table.add_row("Input File", run.input_file)
                        table.add_row("Total URLs", str(run.total_urls))
                        table.add_row("Created", str(run.created_at))
                        table.add_row("Updated", str(run.updated_at))
                        if run.error_message:
                            table.add_row("Error", run.error_message)

                        console.print(table)
                    else:
                        console.print(f"❌ Run {run_id} not found", style="red")
            else:
                async with db_manager.session() as session:
                    from sqlalchemy import desc, select

                    from content_collector.storage.models import ScrapingRun

                    query = (
                        select(ScrapingRun)
                        .order_by(desc(ScrapingRun.created_at))
                        .limit(10)
                    )
                    result = await session.execute(query)
                    runs = result.scalars().all()

                    if runs:
                        table = Table(title="Recent Scraping Runs")
                        table.add_column("Run ID", style="cyan")
                        table.add_column("Status", style="white")
                        table.add_column("URLs", style="green")
                        table.add_column("Created", style="yellow")

                        for run in runs:
                            status_style = (
                                "green"
                                if run.status == "completed"
                                else "red" if run.status == "failed" else "yellow"
                            )
                            table.add_row(
                                run.id[:8] + "...",
                                f"[{status_style}]{run.status}[/{status_style}]",
                                str(run.total_urls),
                                str(run.created_at)[:19] if run.created_at else "N/A",
                            )

                        console.print(table)
                    else:
                        console.print("No scraping runs found", style="yellow")

        except Exception as e:
            console.print(f"❌ Failed to get status: {e}", style="red")
            raise typer.Exit(1)
        finally:
            await db_manager.close()

    asyncio.run(_status())


@app.command()
def report(
    run_id: str = typer.Argument(..., help="Run ID to generate report for"),
    output_format: str = typer.Option(
        "table", "--format", help="Output format: table, json, csv"
    ),
    save_file: Optional[Path] = typer.Option(
        None, "--save", help="Save report to file"
    ),
    detailed: bool = typer.Option(
        False, "--detailed", help="Include detailed page information"
    ),
):
    """Generate a comprehensive report for a scraping run."""
    console.print("📈 Generating report...", style="bold blue")

    async def _report():
        try:
            await db_manager.initialize()
            report_data = await report_generator.generate_run_report(
                run_id, detailed=detailed
            )

            if output_format == "json":
                import json

                output = json.dumps(report_data, indent=2, default=str)
                if save_file:
                    save_file.write_text(output)
                    console.print(f"✅ JSON report saved to {save_file}", style="green")
                else:
                    console.print(output)

            elif output_format == "csv":
                # Convert to CSV format
                import csv
                import io

                output = io.StringIO()
                if report_data.get("pages"):
                    writer = csv.writer(output)
                    writer.writerow(["URL", "Status", "Title", "Content Length"])
                    for page in report_data["pages"]:
                        writer.writerow(
                            [
                                page.get("url", ""),
                                page.get("status_code", ""),
                                page.get("title", ""),
                                page.get("content_length", ""),
                            ]
                        )

                csv_content = output.getvalue()
                if save_file:
                    save_file.write_text(csv_content)
                    console.print(f"✅ CSV report saved to {save_file}", style="green")
                else:
                    console.print(csv_content)

            else:  # table format
                await report_generator.print_run_report(
                    run_id, console, detailed=detailed
                )

            if save_file and output_format == "table":
                console.print(
                    "💡 Use --format json or --format csv to save table reports",
                    style="yellow",
                )

        except Exception as e:
            console.print(f"❌ Report generation failed: {e}", style="red")
            raise typer.Exit(1)
        finally:
            await db_manager.close()

    asyncio.run(_report())


@app.command()
def cleanup(
    days: int = typer.Option(7, "--days", help="Delete runs older than N days"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be deleted"),
):
    """Clean up old scraping runs and associated data."""
    console.print("🧹 Cleaning up old data...", style="bold blue")

    async def _cleanup():
        try:
            await db_manager.initialize()
            deleted_count = await db_manager.cleanup_old_runs(days, dry_run=dry_run)

            if dry_run:
                console.print(
                    f"Would delete {deleted_count} runs older than {days} days",
                    style="yellow",
                )
            else:
                console.print(
                    f"✅ Deleted {deleted_count} runs older than {days} days",
                    style="green",
                )

        except Exception as e:
            console.print(f"❌ Cleanup failed: {e}", style="red")
            raise typer.Exit(1)
        finally:
            await db_manager.close()

    asyncio.run(_cleanup())


@app.command()
def turbo(
    input_file: Path = typer.Argument(..., help="CSV file containing URLs to scrape"),
    performance: str = typer.Option(
        "balanced",
        "--performance",
        help="Performance mode: conservative, balanced, aggressive, maximum",
    ),
    max_workers: Optional[int] = typer.Option(
        None, "--max-workers", help="Override number of concurrent workers"
    ),
    max_pages: Optional[int] = typer.Option(
        None, "--max-pages", help="Maximum number of pages to scrape"
    ),
    depth: int = typer.Option(1, "--depth", help="Maximum crawling depth"),
    allow_cross_domain: bool = typer.Option(
        False,
        "--allow-cross-domain/--same-domain-only",
        help="Allow crawling across different domains",
    ),
    show_stats: bool = typer.Option(
        False, "--show-stats", help="Display real-time performance statistics"
    ),
):
    """High-performance web scraping with intelligent content processing."""
    import psutil

    # System info
    cpu_count = psutil.cpu_count()
    memory_gb = round(psutil.virtual_memory().total / (1024**3), 1)

    # Performance mode settings
    performance_configs = {
        "conservative": {"base_workers": min(5, cpu_count), "connections": 10},
        "balanced": {"base_workers": min(10, cpu_count), "connections": 20},
        "aggressive": {"base_workers": min(20, cpu_count), "connections": 40},
        "maximum": {"base_workers": min(50, cpu_count), "connections": 100},
    }

    config = performance_configs.get(performance, performance_configs["balanced"])
    workers = max_workers or config["base_workers"]
    max_connections = config["connections"]
    max_connections_per_host = max_connections // 2

    console.print("🖥️  System Information:", style="bold blue")
    console.print(f"   CPUs: {cpu_count}")
    console.print(f"   Memory: {memory_gb} GB")
    console.print(f"   Recommended max workers: {min(30, cpu_count * 3)}")

    console.print("🚀 Starting TURBO scraping run...", style="bold green")
    console.print(f"Input file: {input_file}")
    console.print(f"Performance mode: {performance.upper()}")
    console.print(f"Max workers: {workers}")
    console.print(f"Max connections: {max_connections}")
    console.print(f"Max connections per host: {max_connections_per_host}")

    if max_pages:
        console.print(f"Max pages: {max_pages}")

    console.print(f"Max depth: {depth}")
    console.print("Loop prevention: enabled")
    console.print(
        f"Cross-domain crawling: {'allowed' if allow_cross_domain else 'same domain only'}"
    )
    console.print(f"Real-time stats: {'enabled' if show_stats else 'disabled'}")

    async def _turbo_run():
        from content_collector.config.settings import settings
        from content_collector.core.scraper import (
            ScrapingEngine as HighPerformanceScrapingEngine,
        )

        # Update settings
        original_cross_domain = settings.scraping.allow_cross_domain
        settings.scraping.allow_cross_domain = allow_cross_domain

        try:
            engine = HighPerformanceScrapingEngine(
                max_workers=workers,
                max_pages=max_pages,
                max_depth=depth,
                max_connections=max_connections,
                max_connections_per_host=max_connections_per_host,
                show_stats=show_stats,
            )

            run_id = await engine.run(input_file, max_pages=max_pages, max_depth=depth)
            console.print(
                f"✅ TURBO scraping completed! Run ID: {run_id}", style="bold green"
            )

            # Show performance summary
            stats = engine.get_final_stats()
            if stats:
                console.print("\n📊 Performance Summary:", style="bold blue")
                console.print(
                    f"   Total time: {stats.get('total_time', 0):.2f} seconds"
                )
                console.print(f"   URLs processed: {stats.get('urls_processed', 0)}")
                console.print(f"   URLs failed: {stats.get('urls_failed', 0)}")
                console.print(f"   Success rate: {stats.get('success_rate', 0):.1f}%")
                console.print(
                    f"   Average processing time: "
                    f"{stats.get('avg_processing_time', 0):.2f}s per URL"
                )
                console.print(
                    f"   Throughput: {stats.get('throughput', 0):.1f} URLs/second"
                )

            console.print(
                f"📊 Run ID for status/reports: {run_id}", style="bold yellow"
            )

        except Exception as e:
            console.print(f"❌ TURBO scraping failed: {e}", style="red")
            raise typer.Exit(1)
        finally:
            settings.scraping.allow_cross_domain = original_cross_domain
            await db_manager.close()

    asyncio.run(_turbo_run())


@app.command()
def benchmark(
    mode: str = typer.Option(
        "comprehensive", "--mode", help="Benchmark mode: parsing, comprehensive"
    ),
    save_results: bool = typer.Option(
        True, "--save-results/--no-save-results", help="Save benchmark results to file"
    ),
):
    """Run performance benchmarks on the content collector."""
    console.print("⚡ Performance Benchmarking Suite", style="bold blue")

    async def _benchmark():
        parser = None
        try:
            if mode == "parsing":
                console.print(
                    "🔍 Testing Comprehensive Parsing Capabilities...",
                    style="bold yellow",
                )

                parser = ContentParser()

                # Test URLs for different content types
                test_urls = [
                    "https://example.com",  # Basic HTML
                    "https://react.dev",  # JavaScript-heavy SPA
                ]

                for url in test_urls:
                    console.print(f"\nTesting: {url}")
                    try:
                        import time

                        start_time = time.time()
                        result = await parser.parse(url, url)
                        duration = time.time() - start_time

                        console.print(f"  ✅ Parsed in {duration:.2f}s")
                        console.print(
                            f"  📄 Content: {len(result.get('body_text', ''))} characters"
                        )
                        console.print(f"  🔗 Links: {len(result.get('links', []))}")

                    except Exception as e:
                        console.print(f"  ❌ Failed: {e}", style="red")

            elif mode == "comprehensive":
                console.print("🚀 Comprehensive System Benchmark", style="bold yellow")
                console.print("This would run full system benchmarks including:")
                console.print("  - Concurrent processing performance")
                console.print("  - Database operation speed")
                console.print("  - Memory usage patterns")
                console.print("  - Network efficiency")
                console.print("  - Content parsing accuracy")
                console.print(
                    "\n💡 Use 'turbo' command with --show-stats for real performance metrics"
                )

        except Exception as e:
            console.print(f"❌ Benchmark failed: {e}", style="red")
        finally:
            if parser:
                await parser.close()

    asyncio.run(_benchmark())


@app.command()
def test_parsing(
    url: Optional[str] = typer.Option(
        None, "--url", help="Specific URL to test parsing"
    ),
    show_content: bool = typer.Option(
        False, "--show-content", help="Display extracted content"
    ),
):
    """Test comprehensive content parsing capabilities."""
    console.print("🔍 Testing Comprehensive Parsing", style="bold blue")

    async def _test():
        parser = None
        try:
            parser = ContentParser()

            if url:
                test_urls = [url]
            else:
                # Default test URLs covering different content types
                test_urls = [
                    "https://example.com",
                    "https://www.python.org",
                ]

            for test_url in test_urls:
                console.print(f"\n📄 Testing: {test_url}", style="bold cyan")

                try:
                    import time

                    start_time = time.time()
                    result = await parser.parse(test_url, test_url)
                    duration = time.time() - start_time

                    # Display results
                    console.print(f"⏱️  Processing time: {duration:.2f} seconds")
                    console.print(f"📝 Title: {result.get('title', 'No title')}")

                    body_text = result.get("body_text", "")
                    console.print(f"📄 Content length: {len(body_text)} characters")
                    console.print(
                        f"📊 Word count: {len(body_text.split()) if body_text else 0}"
                    )
                    console.print(f"🔗 Links found: {len(result.get('links', []))}")
                    console.print(f"🖼️  Images found: {len(result.get('images', []))}")

                    if show_content and body_text:
                        console.print("\n📖 Content Preview:", style="bold yellow")
                        preview = (
                            body_text[:500] + "..."
                            if len(body_text) > 500
                            else body_text
                        )
                        console.print(preview, style="white")

                    console.print("✅ Parsing completed successfully", style="green")

                except Exception as e:
                    console.print(f"❌ Parsing failed: {e}", style="red")
                    import traceback

                    console.print(traceback.format_exc(), style="red")

        except Exception as e:
            console.print(f"❌ Test setup failed: {e}", style="red")
        finally:
            if parser:
                await parser.close()

    asyncio.run(_test())


def main(args=None):
    """Main entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
