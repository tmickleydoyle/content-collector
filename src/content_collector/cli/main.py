"""Command-line interface for the content collector."""

import asyncio
from pathlib import Path
from typing import Optional

import structlog
import typer
from rich.console import Console
from rich.table import Table

from content_collector.analytics.reporting import report_generator
from content_collector.core.scraper import ScrapingEngine
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
def run(
    input_file: Path = typer.Argument(
        ..., help="Path to input file containing CSV paths"
    ),
    max_pages: Optional[int] = typer.Option(
        None, "--max-pages", help="Maximum number of pages to scrape"
    ),
    depth: int = typer.Option(
        1, "--depth", help="Maximum depth for recursive crawling"
    ),
    enable_loop_prevention: bool = typer.Option(
        True,
        "--enable-loop-prevention/--disable-loop-prevention",
        help="Enable or disable loop prevention during crawling",
    ),
    allow_cross_domain: bool = typer.Option(
        False,
        "--allow-cross-domain/--same-domain-only",
        help="Allow cross-domain crawling or restrict to same domain only",
    ),
    high_performance: bool = typer.Option(
        False,
        "--high-performance/--standard",
        help="Use high-performance parallel scraper engine",
    ),
    enhanced_parsing: bool = typer.Option(
        False,
        "--enhanced-parsing/--standard-parsing",
        help="Use enhanced JavaScript-aware link extraction for SPAs",
    ),
    max_workers: Optional[int] = typer.Option(
        None,
        "--max-workers",
        help="Maximum number of concurrent workers (high-performance mode only)",
    ),
    debug_links: bool = typer.Option(
        False,
        "--debug-links",
        help="Enable debug output for link extraction (shows all found/filtered links)",
    ),
):
    """Run the web scraper with the specified parameters."""
    console.print(f"🕷️  Starting scraping run...", style="bold blue")
    console.print(f"Input file: {input_file}")
    if max_pages:
        console.print(f"Max pages: {max_pages}")
    console.print(f"Max depth: {depth}")
    console.print(
        f"Loop prevention: {'enabled' if enable_loop_prevention else 'disabled'}"
    )
    console.print(
        f"Cross-domain crawling: {'allowed' if allow_cross_domain else 'same domain only'}"
    )
    console.print(f"Engine: {'High-Performance' if high_performance else 'Standard'}")
    console.print(
        f"Parser: {'Enhanced (JS-aware)' if enhanced_parsing else 'Standard'}"
    )
    if high_performance and max_workers:
        console.print(f"Max workers: {max_workers}")

    async def _run():
        from content_collector.config.settings import settings

        original_loop_setting = settings.scraping.enable_loop_prevention
        original_cross_domain_setting = settings.scraping.allow_cross_domain
        settings.scraping.enable_loop_prevention = enable_loop_prevention
        settings.scraping.allow_cross_domain = allow_cross_domain

        # Choose scraper engine based on performance mode
        if high_performance:
            from content_collector.core.enhanced_scraper import (
                HighPerformanceScrapingEngine,
            )

            scraper = HighPerformanceScrapingEngine(
                max_workers=max_workers, debug_links=debug_links
            )
            console.print(
                "🚀 Using High-Performance Scraping Engine", style="bold green"
            )
        else:
            scraper = ScrapingEngine(debug_links=debug_links)
            console.print("⚙️  Using Standard Scraping Engine", style="bold yellow")

        try:
            await db_manager.initialize()
            run_id = await scraper.run(input_file, max_pages, depth)
            console.print(f"✅ Scraping completed! Run ID: {run_id}", style="green")
            return run_id
        except Exception as e:
            console.print(f"❌ Scraping failed: {e}", style="red")
            return None
        finally:
            settings.scraping.enable_loop_prevention = original_loop_setting
            settings.scraping.allow_cross_domain = original_cross_domain_setting
            await db_manager.close()

    run_id = asyncio.run(_run())
    if run_id is None:
        raise typer.Exit(1)
    console.print(f"📊 Run ID for status/reports: {run_id}", style="cyan")


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
    run_id: Optional[str] = typer.Option(
        None, "--run-id", help="Generate report for specific run"
    ),
    system: bool = typer.Option(False, "--system", help="Generate system-wide report"),
    tree: bool = typer.Option(
        False,
        "--tree",
        help="Generate tree structure report showing parent-child URL relationships",
    ),
    save: bool = typer.Option(False, "--save", help="Save report to file"),
    format_type: str = typer.Option(
        "json", "--format", help="Output format: json or txt (for tree reports)"
    ),
    days: int = typer.Option(7, "--days", help="Days to include in system report"),
):
    """Generate analytics reports."""
    if tree and not run_id:
        console.print(
            "❌ Tree reports require a specific run ID. Use --run-id option.",
            style="red",
        )
        raise typer.Exit(1)

    if tree:
        console.print("🌳 Generating tree structure report...", style="bold blue")
    else:
        console.print("📈 Generating report...", style="bold blue")

    async def _report():
        try:
            await db_manager.initialize()

            if tree and run_id:
                # Generate tree structure report
                tree_data = await report_generator.generate_tree_report(run_id)

                summary = tree_data["tree_summary"]
                run_info = tree_data["run_info"]

                # Display tree summary in console
                table = Table(title=f"Tree Report: {run_id[:8]}...")
                table.add_column("Metric", style="cyan")
                table.add_column("Value", style="white")

                table.add_row("Total Pages", str(summary["total_pages"]))
                table.add_row("Root Pages", str(summary["root_pages"]))
                table.add_row("Success Count", str(summary["success_count"]))
                table.add_row("Failure Count", str(summary["failure_count"]))
                table.add_row("Success Rate", f"{summary['success_rate']:.1f}%")
                table.add_row(
                    "Max Depth Configured", str(run_info["max_depth_configured"])
                )
                table.add_row("Max Depth Reached", str(run_info["max_depth_actual"]))

                console.print(table)

                # Show a preview of the tree structure (first few items)
                if tree_data["tree"]:
                    console.print("\n🌳 Tree Structure Preview:", style="bold green")
                    preview_text = report_generator.generate_tree_text(
                        {
                            "tree": tree_data["tree"][:3],
                            "run_info": run_info,
                            "tree_summary": summary,
                        },
                        show_details=False,
                    )
                    # Show just the tree part, not the full header
                    tree_lines = (
                        preview_text.split("TREE STRUCTURE:")[1]
                        .split("-" * 80)[0]
                        .strip()
                    )
                    console.print(
                        tree_lines[:1000] + "..."
                        if len(tree_lines) > 1000
                        else tree_lines
                    )

                    if len(tree_data["tree"]) > 3:
                        console.print(
                            f"... and {len(tree_data['tree']) - 3} more root URLs"
                        )

                report_data = tree_data

            elif run_id:
                report_data = await report_generator.generate_run_report(run_id)

                summary = report_data["summary"]
                table = Table(title=f"Run Report: {run_id[:8]}...")
                table.add_column("Metric", style="cyan")
                table.add_column("Value", style="white")

                table.add_row("Total Pages", str(summary["total_pages"]))
                table.add_row("Success Count", str(summary["success_count"]))
                table.add_row("Failure Count", str(summary["failure_count"]))
                table.add_row("Success Rate", f"{summary['success_rate']:.1f}%")
                table.add_row(
                    "Total Content", f"{summary['total_content_bytes']:,} bytes"
                )

                console.print(table)

            elif system:
                report_data = await report_generator.generate_system_report(days)

                runs = report_data["runs"]
                pages = report_data["pages"]

                table = Table(title=f"System Report ({days} days)")
                table.add_column("Metric", style="cyan")
                table.add_column("Value", style="white")

                table.add_row("Total Runs", str(runs["total_runs"]))
                table.add_row("Completed Runs", str(runs["completed_runs"]))
                table.add_row("Failed Runs", str(runs["failed_runs"]))
                table.add_row("Total Pages Scraped", str(pages["total_scraped"]))
                table.add_row("Success Rate", f"{pages['success_rate']:.1f}%")
                table.add_row(
                    "Unique Domains", str(report_data["domains"]["unique_domains"])
                )

                console.print(table)

            else:
                console.print(
                    "❌ Please specify --run-id, --system, or --tree with --run-id",
                    style="red",
                )
                raise typer.Exit(1)

            if save:
                if tree and run_id:
                    filename = f"tree_{run_id[:8]}_report"
                    saved_path = await report_generator.save_tree_report(
                        report_data, filename, format_type
                    )
                else:
                    filename = f"{'run_' + run_id if run_id else 'system'}_report.json"
                    saved_path = await report_generator.save_report(
                        report_data, filename
                    )
                console.print(f"💾 Report saved to: {saved_path}", style="green")

        except Exception as e:
            console.print(f"❌ Failed to generate report: {e}", style="red")
            raise typer.Exit(1)
        finally:
            await db_manager.close()

    asyncio.run(_report())


@app.command()
def cleanup(
    days: int = typer.Option(30, "--days", help="Remove content older than N days"),
    confirm: bool = typer.Option(False, "--confirm", help="Skip confirmation prompt"),
):
    """Clean up old scraped content and data."""
    if not confirm:
        confirm = typer.confirm(
            f"⚠️  This will remove content older than {days} days. Continue?"
        )
        if not confirm:
            console.print("Cleanup cancelled", style="yellow")
            return

    console.print(
        f"🧹 Cleaning up content older than {days} days...", style="bold blue"
    )

    async def _cleanup():
        try:
            from content_collector.storage.file_storage import file_storage

            removed_count = await file_storage.cleanup_old_content(days)
            console.print(
                f"✅ Removed {removed_count} old content directories", style="green"
            )

        except Exception as e:
            console.print(f"❌ Cleanup failed: {e}", style="red")
            raise typer.Exit(1)

    asyncio.run(_cleanup())


@app.command()
def turbo(
    input_file: Path = typer.Argument(
        ..., help="Path to input file containing CSV paths"
    ),
    max_pages: Optional[int] = typer.Option(
        None, "--max-pages", help="Maximum number of pages to scrape"
    ),
    depth: int = typer.Option(
        2, "--depth", help="Maximum depth for recursive crawling"
    ),
    performance_mode: str = typer.Option(
        "balanced",
        "--performance",
        help="Performance mode: conservative, balanced, aggressive, maximum",
    ),
    max_workers: Optional[int] = typer.Option(
        None, "--max-workers", help="Maximum number of concurrent workers"
    ),
    enable_loop_prevention: bool = typer.Option(
        True,
        "--enable-loop-prevention/--disable-loop-prevention",
        help="Enable or disable loop prevention during crawling",
    ),
    allow_cross_domain: bool = typer.Option(
        False,
        "--allow-cross-domain/--same-domain-only",
        help="Allow cross-domain crawling or restrict to same domain only",
    ),
    show_stats: bool = typer.Option(
        True, "--show-stats/--no-stats", help="Show real-time performance statistics"
    ),
):
    """Run the web scraper with maximum performance optimization."""
    from content_collector.config.performance import (
        apply_env_overrides,
        get_performance_settings,
        get_system_recommendations,
        validate_performance_settings,
    )
    from content_collector.core.enhanced_scraper import HighPerformanceScrapingEngine
    from content_collector.storage.database import db_manager

    # Get system recommendations
    system_info = get_system_recommendations()
    console.print("🖥️  System Information:", style="bold blue")
    console.print(f"   CPUs: {system_info['cpu_count']}")
    console.print(f"   Memory: {system_info['memory_gb']:.1f} GB")
    console.print(
        f"   Recommended max workers: {system_info['recommended_max_workers']}"
    )

    # Get performance settings
    perf_settings = get_performance_settings(performance_mode, max_workers)
    perf_settings = apply_env_overrides(perf_settings)

    # Validate settings and show warnings
    warnings = validate_performance_settings(perf_settings)
    if warnings:
        console.print("⚠️  Performance Warnings:", style="bold yellow")
        for key, warning in warnings.items():
            console.print(f"   {key}: {warning}")

    console.print(f"🚀 Starting TURBO scraping run...", style="bold green")
    console.print(f"Input file: {input_file}")
    console.print(f"Performance mode: {performance_mode.upper()}")
    console.print(f"Max workers: {perf_settings['max_workers']}")
    console.print(f"Max connections: {perf_settings['max_connections']}")
    console.print(
        f"Max connections per host: {perf_settings['max_connections_per_host']}"
    )
    if max_pages:
        console.print(f"Max pages: {max_pages}")
    console.print(f"Max depth: {depth}")
    console.print(
        f"Loop prevention: {'enabled' if enable_loop_prevention else 'disabled'}"
    )
    console.print(
        f"Cross-domain crawling: {'allowed' if allow_cross_domain else 'same domain only'}"
    )
    console.print(f"Real-time stats: {'enabled' if show_stats else 'disabled'}")

    async def _turbo_run():
        from content_collector.config.settings import settings

        # Override settings with performance optimizations
        original_settings = {
            "max_concurrent_requests": settings.scraping.max_concurrent_requests,
            "request_timeout": settings.scraping.request_timeout,
            "rate_limit_delay": settings.scraping.rate_limit_delay,
            "enable_loop_prevention": settings.scraping.enable_loop_prevention,
            "allow_cross_domain": settings.scraping.allow_cross_domain,
        }

        # Apply performance settings
        settings.scraping.max_concurrent_requests = perf_settings[
            "max_concurrent_requests"
        ]
        settings.scraping.request_timeout = perf_settings["request_timeout"]
        settings.scraping.rate_limit_delay = perf_settings["rate_limit_delay"]
        settings.scraping.enable_loop_prevention = enable_loop_prevention
        settings.scraping.allow_cross_domain = allow_cross_domain

        scraper = HighPerformanceScrapingEngine(
            max_workers=perf_settings["max_workers"]
        )

        try:
            await db_manager.initialize()

            start_time = time.time()
            run_id = await scraper.run(input_file, max_pages, depth)
            end_time = time.time()

            total_time = end_time - start_time
            stats = scraper._stats

            console.print(
                f"✅ TURBO scraping completed! Run ID: {run_id}", style="bold green"
            )
            console.print("\n📊 Performance Summary:", style="bold blue")
            console.print(f"   Total time: {total_time:.2f} seconds")
            console.print(f"   URLs processed: {stats['urls_processed']}")
            console.print(f"   URLs failed: {stats['urls_failed']}")
            console.print(
                f"   Success rate: {(stats['urls_processed'] / max(1, stats['urls_processed'] + stats['urls_failed']) * 100):.1f}%"
            )
            if stats["urls_processed"] > 0:
                console.print(
                    f"   Average processing time: {stats['total_processing_time'] / stats['urls_processed']:.2f}s per URL"
                )
                console.print(
                    f"   Throughput: {stats['urls_processed'] / max(1, total_time):.1f} URLs/second"
                )

            return run_id
        except Exception as e:
            console.print(f"❌ TURBO scraping failed: {e}", style="red")
            return None
        finally:
            # Restore original settings
            for key, value in original_settings.items():
                setattr(settings.scraping, key, value)
            await db_manager.close()

    import time

    run_id = asyncio.run(_turbo_run())
    if run_id is None:
        raise typer.Exit(1)
    console.print(f"📊 Run ID for status/reports: {run_id}", style="cyan")


def main(args=None):
    """Main entry point for the CLI application."""
    if args:
        import sys

        original_argv = sys.argv
        try:
            sys.argv = ["content-collector"] + args
            app()
            return 0
        except SystemExit as e:
            return e.code if e.code is not None else 0
        except Exception:
            return 1
        finally:
            sys.argv = original_argv
    else:
        app()


if __name__ == "__main__":
    main()
