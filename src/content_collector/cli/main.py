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
from content_collector.core.scraper import ScrapingEngine
from content_collector.input.processor import InputProcessor
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
    use_sitemaps: bool = typer.Option(
        False,
        "--use-sitemaps",
        help="Discover additional URLs from sitemaps for each domain",
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


@app.command()
def intelligence(
    url: str = typer.Argument(..., help="URL to analyze with AI-powered intelligence"),
    save_report: bool = typer.Option(
        True, "--save-report/--no-save-report", help="Save intelligence report to file"
    ),
    show_raw: bool = typer.Option(
        False, "--show-raw", help="Show raw parsing data along with intelligence"
    ),
):
    """Analyze content with AI-powered intelligence system for deep insights."""
    console.print("🧠 Content Intelligence Analysis", style="bold blue")
    console.print(f"Analyzing: {url}")

    async def _analyze():
        parser = None
        try:
            # Enable intelligence analysis
            parser = ContentParser(enable_intelligence=True)

            console.print("🔍 Parsing and analyzing content...")
            result = await parser.parse(url, url)

            if not result.get("intelligence"):
                console.print("❌ Intelligence analysis not available", style="red")
                return

            intelligence = result["intelligence"]

            # Display content overview
            console.print(f"\n📄 Content Overview", style="bold green")
            console.print(f"  Title: {result.get('title', 'N/A')}")
            console.print(f"  Content: {len(result.get('body_text', ''))} chars")
            console.print(f"  Links: {result.get('link_count', 0)}")

            # Display intelligence analysis
            console.print(f"\n🧠 Intelligence Analysis", style="bold cyan")

            # Content Quality
            quality = intelligence.get("content_quality", {})
            if quality:
                console.print(
                    f"  📊 Quality Score: {quality.get('overall_score', 'N/A')}"
                )
                console.print(
                    f"  📝 Readability: {quality.get('readability_score', 'N/A')}"
                )
                console.print(
                    f"  📏 Content Depth: {quality.get('content_depth', 'N/A')}"
                )
                console.print(
                    f"  🔗 Link Density: {quality.get('link_density', 'N/A')}"
                )

            # Content Classification
            classification = intelligence.get("content_classification", {})
            if classification:
                console.print(
                    f"  📂 Category: {classification.get('primary_category', 'N/A')}"
                )
                console.print(
                    f"  🎯 Content Type: {classification.get('content_type', 'N/A')}"
                )
                console.print(
                    f"  👥 Target Audience: {classification.get('audience', 'N/A')}"
                )

            # Keywords and Topics
            keywords = intelligence.get("keywords", [])
            if keywords:
                console.print(f"  🏷️  Top Keywords: {', '.join(keywords[:10])}")

            topics = intelligence.get("topics", [])
            if topics:
                console.print(f"  📋 Topics: {', '.join(topics[:5])}")

            # Technology Stack
            tech_stack = intelligence.get("technology_stack", {})
            if tech_stack:
                frameworks = tech_stack.get("frameworks", [])
                libraries = tech_stack.get("libraries", [])
                if frameworks:
                    console.print(f"  ⚙️  Frameworks: {', '.join(frameworks[:5])}")
                if libraries:
                    console.print(f"  📚 Libraries: {', '.join(libraries[:5])}")

            # SEO Analysis
            seo = intelligence.get("seo_analysis", {})
            if seo:
                console.print(f"\n🔍 SEO Analysis", style="bold magenta")
                console.print(f"  📊 SEO Score: {seo.get('seo_score', 'N/A')}")
                console.print(
                    f"  📰 Has Meta Description: {seo.get('has_meta_description', False)}"
                )
                console.print(f"  🏷️  H1 Count: {seo.get('h1_count', 0)}")
                console.print(f"  📝 Title Length: {seo.get('title_length', 0)} chars")
                console.print(f"  🔗 Internal Links: {seo.get('internal_links', 0)}")
                console.print(f"  🌐 External Links: {seo.get('external_links', 0)}")

            # Show raw data if requested
            if show_raw:
                console.print(f"\n📊 Raw Analysis Data", style="bold yellow")
                import json

                console.print(json.dumps(intelligence, indent=2, ensure_ascii=False))

            # Save report if requested
            if save_report:
                import json
                from datetime import datetime
                from pathlib import Path

                output_dir = Path("intelligence_reports")
                output_dir.mkdir(exist_ok=True)

                # Create filename from URL
                filename = (
                    url.replace("https://", "").replace("http://", "").replace("/", "_")
                )
                if filename.endswith("_"):
                    filename = filename[:-1]

                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                report_file = output_dir / f"{filename}_{timestamp}_intelligence.json"

                # Create comprehensive report
                report_data = {
                    "url": url,
                    "analysis_timestamp": datetime.now().isoformat(),
                    "content_overview": {
                        "title": result.get("title"),
                        "content_length": len(result.get("body_text", "")),
                        "link_count": result.get("link_count", 0),
                        "headers_count": sum(
                            len(h) for h in result.get("headers", {}).values()
                        ),
                    },
                    "intelligence_analysis": intelligence,
                    "raw_parsing_data": result if show_raw else None,
                }

                with open(report_file, "w", encoding="utf-8") as f:
                    json.dump(report_data, f, indent=2, ensure_ascii=False)

                console.print(
                    f"💾 Intelligence report saved: {report_file.absolute()}",
                    style="green",
                )

            console.print(f"\n✅ Intelligence analysis completed!", style="bold green")

        except Exception as e:
            console.print(f"❌ Analysis failed: {e}", style="red")
            import traceback

            console.print(traceback.format_exc(), style="red")
        finally:
            if parser:
                await parser.close()

    asyncio.run(_analyze())


@app.command()
def sitemap(
    domain: str = typer.Argument(
        ...,
        help="Domain to discover URLs from (e.g., example.com or https://example.com)",
    ),
    max_urls: Optional[int] = typer.Option(
        None, "--max-urls", help="Maximum number of URLs to discover"
    ),
    use_robots: bool = typer.Option(
        True, "--use-robots/--no-robots", help="Check robots.txt for sitemap locations"
    ),
    output_file: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Save discovered URLs to CSV file"
    ),
    filter_pattern: Optional[str] = typer.Option(
        None, "--filter", help="Regex pattern to filter URLs"
    ),
    exclude_pattern: Optional[str] = typer.Option(
        None, "--exclude", help="Regex pattern to exclude URLs"
    ),
    sort_by: Optional[str] = typer.Option(
        None, "--sort", help="Sort URLs by: priority, lastmod, or none"
    ),
):
    """Discover URLs from a domain's sitemap for efficient scraping."""
    console.print("🗺️  Sitemap URL Discovery", style="bold blue")
    console.print(f"Domain: {domain}")

    async def _discover(save_to_file=output_file):
        processor = InputProcessor()

        try:
            # Discover URLs from sitemap
            urls = await processor.discover_from_sitemap(
                domain=domain, max_urls=max_urls, use_robots=use_robots
            )

            # Apply filters if specified
            if filter_pattern or exclude_pattern:
                from content_collector.core.sitemap_parser import (
                    SitemapParser,
                    SitemapURL,
                )

                parser = SitemapParser()

                # Convert URLEntry back to SitemapURL for filtering
                sitemap_urls = []
                for url_entry in urls:
                    # Parse description to extract metadata
                    priority = None
                    lastmod = None
                    changefreq = None

                    if url_entry.description:
                        import re
                        from datetime import datetime

                        # Extract priority
                        priority_match = re.search(
                            r"Priority: ([\d.]+)", url_entry.description
                        )
                        if priority_match:
                            priority = float(priority_match.group(1))

                        # Extract lastmod
                        lastmod_match = re.search(
                            r"Modified: ([^\|]+)", url_entry.description
                        )
                        if lastmod_match:
                            try:
                                lastmod = datetime.fromisoformat(
                                    lastmod_match.group(1).strip()
                                )
                            except:
                                pass

                        # Extract changefreq
                        freq_match = re.search(r"Freq: (\w+)", url_entry.description)
                        if freq_match:
                            changefreq = freq_match.group(1)

                    sitemap_url = SitemapURL(
                        loc=str(url_entry.url),
                        priority=priority,
                        lastmod=lastmod,
                        changefreq=changefreq,
                    )
                    sitemap_urls.append(sitemap_url)

                # Apply filters
                if filter_pattern:
                    sitemap_urls = await parser.filter_by_pattern(
                        sitemap_urls, [filter_pattern], exclude=False
                    )

                if exclude_pattern:
                    sitemap_urls = await parser.filter_by_pattern(
                        sitemap_urls, [exclude_pattern], exclude=True
                    )

                # Sort if specified
                if sort_by == "priority":
                    sitemap_urls = parser.sort_by_priority(sitemap_urls)
                elif sort_by == "lastmod":
                    sitemap_urls = parser.sort_by_lastmod(sitemap_urls)

                # Convert back to URLEntry
                urls = []
                for sitemap_url in sitemap_urls:
                    from content_collector.input.processor import URLEntry

                    description_parts = []
                    if sitemap_url.lastmod:
                        description_parts.append(
                            f"Modified: {sitemap_url.lastmod.isoformat()}"
                        )
                    if sitemap_url.priority is not None:
                        description_parts.append(f"Priority: {sitemap_url.priority}")
                    if sitemap_url.changefreq:
                        description_parts.append(f"Freq: {sitemap_url.changefreq}")

                    description = (
                        " | ".join(description_parts) if description_parts else ""
                    )

                    url_entry = URLEntry(
                        url=str(sitemap_url.loc), description=description
                    )
                    urls.append(url_entry)

            # Display results
            console.print(
                f"\n✅ Discovered {len(urls)} URLs from sitemap", style="green"
            )

            if urls:
                # Show sample of URLs
                console.print("\n📋 Sample URLs (first 10):", style="bold")
                for i, url_entry in enumerate(urls[:10], 1):
                    console.print(f"  {i}. {url_entry.url}")
                    if url_entry.description:
                        console.print(f"     {url_entry.description}", style="dim")

                if len(urls) > 10:
                    console.print(f"  ... and {len(urls) - 10} more URLs", style="dim")

            # Save to file if specified
            if save_to_file and urls:
                import csv

                save_path = Path(save_to_file)
                with open(save_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(["url", "description"])

                    for url_entry in urls:
                        writer.writerow([str(url_entry.url), url_entry.description])

                console.print(
                    f"\n💾 URLs saved to: {save_path.absolute()}", style="green"
                )

            return urls

        except Exception as e:
            console.print(f"❌ Sitemap discovery failed: {e}", style="red")
            import traceback

            console.print(traceback.format_exc(), style="dim red")
            return []

    urls = asyncio.run(_discover())

    if not urls:
        console.print("\n⚠️  No URLs discovered from sitemap", style="yellow")
        console.print("Tips:", style="bold")
        console.print("  • Check if the domain has a sitemap.xml")
        console.print("  • Verify robots.txt contains Sitemap directives")
        console.print("  • Try without --no-robots flag")
        raise typer.Exit(1)


@app.command()
def benchmark(
    mode: str = typer.Option(
        "comprehensive",
        "--mode",
        help="Benchmark mode: parsing, intelligence, full, comprehensive",
    ),
    save_results: bool = typer.Option(
        True, "--save-results/--no-save-results", help="Save benchmark results"
    ),
):
    """Benchmark the content collector's world-class capabilities."""
    console.print("🏆 Content Collector Benchmark Suite", style="bold blue")

    async def _benchmark():
        results = {
            "timestamp": asyncio.get_event_loop().time(),
            "mode": mode,
            "tests": [],
        }

        # Define test sites covering various complexity levels
        test_sites = [
            ("Simple HTML", "https://httpbin.org/html"),
            ("JavaScript Heavy", "https://vercel.com"),
            ("Content Rich", "https://example.com"),
        ]

        if mode in ["parsing", "full", "comprehensive"]:
            console.print("\n📊 Parsing Performance Test", style="bold green")

            for name, url in test_sites:
                console.print(f"Testing {name}: {url}")

                try:
                    parser = ContentParser(enable_intelligence=False)

                    start_time = asyncio.get_event_loop().time()
                    result = await parser.parse(url, url)
                    end_time = asyncio.get_event_loop().time()

                    parsing_time = end_time - start_time

                    test_result = {
                        "test_name": f"Parsing - {name}",
                        "url": url,
                        "parsing_time": parsing_time,
                        "content_length": len(result.get("body_text", "")),
                        "links_found": result.get("link_count", 0),
                        "success": True,
                    }

                    console.print(
                        f"  ✓ Time: {parsing_time:.2f}s | Content: {test_result['content_length']} chars | Links: {test_result['links_found']}"
                    )

                    await parser.close()
                    results["tests"].append(test_result)

                except Exception as e:
                    console.print(f"  ❌ Failed: {e}", style="red")
                    results["tests"].append(
                        {
                            "test_name": f"Parsing - {name}",
                            "url": url,
                            "error": str(e),
                            "success": False,
                        }
                    )

        if mode in ["intelligence", "full", "comprehensive"]:
            console.print("\n🧠 Intelligence Analysis Performance", style="bold cyan")

            for name, url in test_sites[:2]:  # Limit intelligence tests
                console.print(f"Testing {name}: {url}")

                try:
                    parser = ContentParser(enable_intelligence=True)

                    start_time = asyncio.get_event_loop().time()
                    result = await parser.parse(url, url)
                    end_time = asyncio.get_event_loop().time()

                    total_time = end_time - start_time
                    intelligence_data = result.get("intelligence", {})

                    test_result = {
                        "test_name": f"Intelligence - {name}",
                        "url": url,
                        "total_time": total_time,
                        "has_intelligence": bool(intelligence_data),
                        "intelligence_features": (
                            len(intelligence_data.keys()) if intelligence_data else 0
                        ),
                        "content_length": len(result.get("body_text", "")),
                        "success": True,
                    }

                    console.print(
                        f"  ✓ Time: {total_time:.2f}s | Features: {test_result['intelligence_features']} | Intelligence: {'Yes' if intelligence_data else 'No'}"
                    )

                    await parser.close()
                    results["tests"].append(test_result)

                except Exception as e:
                    console.print(f"  ❌ Failed: {e}", style="red")
                    results["tests"].append(
                        {
                            "test_name": f"Intelligence - {name}",
                            "url": url,
                            "error": str(e),
                            "success": False,
                        }
                    )

        if mode == "comprehensive":
            console.print("\n🚀 Comprehensive Feature Test", style="bold magenta")

            # Test all content types
            comprehensive_tests = [
                ("HTML Parsing", "https://httpbin.org/html"),
                ("JavaScript Rendering", "https://vercel.com"),
            ]

            for test_name, test_url in comprehensive_tests:
                console.print(f"Comprehensive test: {test_name}")

                try:
                    parser = ContentParser(enable_intelligence=True, debug_links=True)

                    start_time = asyncio.get_event_loop().time()
                    result = await parser.parse(test_url, test_url)
                    end_time = asyncio.get_event_loop().time()

                    test_result = {
                        "test_name": f"Comprehensive - {test_name}",
                        "url": test_url,
                        "total_time": end_time - start_time,
                        "features": {
                            "content_length": len(result.get("body_text", "")),
                            "links_found": result.get("link_count", 0),
                            "headers_found": sum(
                                len(h) for h in result.get("headers", {}).values()
                            ),
                            "has_intelligence": bool(result.get("intelligence")),
                            "has_title": bool(result.get("title")),
                            "has_meta_description": bool(
                                result.get("meta_description")
                            ),
                            "rendering_method": result.get("rendering_method", "html"),
                        },
                        "success": True,
                    }

                    features = test_result["features"]
                    console.print(f"  ✓ Time: {test_result['total_time']:.2f}s")
                    console.print(f"    Content: {features['content_length']} chars")
                    console.print(f"    Links: {features['links_found']}")
                    console.print(f"    Method: {features['rendering_method']}")
                    console.print(
                        f"    Intelligence: {'Yes' if features['has_intelligence'] else 'No'}"
                    )

                    await parser.close()
                    results["tests"].append(test_result)

                except Exception as e:
                    console.print(f"  ❌ Failed: {e}", style="red")
                    results["tests"].append(
                        {
                            "test_name": f"Comprehensive - {test_name}",
                            "url": test_url,
                            "error": str(e),
                            "success": False,
                        }
                    )

        # Calculate summary statistics
        successful_tests = [t for t in results["tests"] if t.get("success")]
        failed_tests = [t for t in results["tests"] if not t.get("success")]

        console.print(f"\n📊 Benchmark Summary", style="bold yellow")
        console.print(f"  Total Tests: {len(results['tests'])}")
        console.print(f"  Successful: {len(successful_tests)}")
        console.print(f"  Failed: {len(failed_tests)}")

        if successful_tests:
            avg_time = sum(
                t.get("total_time", t.get("parsing_time", 0)) for t in successful_tests
            ) / len(successful_tests)
            console.print(f"  Average Time: {avg_time:.2f}s")

            total_content = sum(
                t.get("features", {}).get("content_length", t.get("content_length", 0))
                for t in successful_tests
            )
            console.print(f"  Total Content: {total_content:,} chars")

        # Save results if requested
        if save_results:
            import json
            from datetime import datetime
            from pathlib import Path

            output_dir = Path("benchmark_results")
            output_dir.mkdir(exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            results_file = output_dir / f"benchmark_{mode}_{timestamp}.json"

            results["summary"] = {
                "total_tests": len(results["tests"]),
                "successful_tests": len(successful_tests),
                "failed_tests": len(failed_tests),
                "average_time": avg_time if successful_tests else 0,
                "total_content_processed": total_content if successful_tests else 0,
            }

            with open(results_file, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2, ensure_ascii=False)

            console.print(
                f"💾 Benchmark results saved: {results_file.absolute()}", style="green"
            )

        console.print(f"\n✅ Benchmark completed!", style="bold green")

    asyncio.run(_benchmark())


@app.command()
def test_parsing(
    url: Optional[str] = typer.Option(
        None, "--url", help="Single URL to test (default: uses built-in test domains)"
    ),
    save_files: bool = typer.Option(
        True, "--save-files/--no-save-files", help="Save results to files"
    ),
    save_db: bool = typer.Option(
        False, "--save-db/--no-save-db", help="Save results to database"
    ),
):
    """Test comprehensive parsing capabilities with automatic content detection."""
    console.print("🧪 Testing Content Parser", style="bold blue")

    async def _test():
        parser = None
        try:
            # Create comprehensive parser
            parser = ContentParser(debug_links=True)

            # Determine test URLs
            test_urls = []
            if url:
                test_urls = [url]
            else:
                test_urls = [
                    "https://example.com",  # Simple HTML
                    "https://httpbin.org/html",  # Test HTML
                    "https://vercel.com",  # JS-heavy site
                ]

            console.print(f"Comprehensive parsing enabled (auto-detects content types)")
            console.print(f"URLs: {len(test_urls)}")

            results = []

            for i, test_url in enumerate(test_urls, 1):
                console.print(f"\n[{i}/{len(test_urls)}] 🔍 Parsing: {test_url}")

                try:
                    result = await parser.parse(test_url, test_url)

                    # Display results
                    console.print(f"  ✓ Title: {result.get('title', 'N/A')[:60]}...")
                    console.print(
                        f"  ✓ Content: {len(result.get('body_text', ''))} chars"
                    )
                    console.print(f"  ✓ Links: {result.get('link_count', 0)}")
                    console.print(
                        f"  ✓ Headers: {sum(len(h) for h in result.get('headers', {}).values())}"
                    )

                    if "rendering_method" in result:
                        console.print(f"  ✓ Method: {result['rendering_method']}")
                    if "ocr_performed" in result:
                        console.print(
                            f"  ✓ OCR: {'Yes' if result['ocr_performed'] else 'No'}"
                        )

                    results.append((test_url, result))

                except Exception as e:
                    console.print(f"  ❌ Failed: {e}", style="red")
                    results.append((test_url, None))

            # Save results
            if save_files or save_db:
                console.print(f"\n💾 Saving Results...")

                if save_files:
                    # Create output directory
                    import json
                    from pathlib import Path

                    output_dir = Path("test_results")
                    output_dir.mkdir(exist_ok=True)

                    for test_url, result in results:
                        if result:
                            filename = (
                                test_url.replace("https://", "")
                                .replace("http://", "")
                                .replace("/", "_")
                            )
                            if filename.endswith("_"):
                                filename = filename[:-1]

                            # Save JSON
                            json_file = output_dir / f"{filename}_result.json"
                            with open(json_file, "w", encoding="utf-8") as f:
                                json.dump(result, f, indent=2, ensure_ascii=False)

                            # Save content
                            if result.get("body_text"):
                                text_file = output_dir / f"{filename}_content.txt"
                                with open(text_file, "w", encoding="utf-8") as f:
                                    f.write(f"URL: {test_url}\n")
                                    f.write(f"Title: {result.get('title', 'N/A')}\n")
                                    f.write("=" * 50 + "\n\n")
                                    f.write(result["body_text"])

                    console.print(f"  ✓ Files saved to: {output_dir.absolute()}")

                if save_db:
                    from content_collector.storage.models import Page, ScrapingRun

                    try:
                        await db_manager.initialize()

                        async with db_manager.get_session() as session:
                            # Create run
                            run = ScrapingRun(
                                run_id="enhanced_parser_test", status="completed"
                            )
                            session.add(run)
                            await session.commit()

                            # Save pages
                            for test_url, result in results:
                                if result:
                                    page = Page(
                                        run_id=run.run_id,
                                        url=test_url,
                                        title=result.get("title"),
                                        meta_description=result.get("meta_description"),
                                        content_length=result.get("content_length", 0),
                                        link_count=result.get("link_count", 0),
                                        content_hash=result.get("content_hash"),
                                        status="completed",
                                    )
                                    session.add(page)

                            await session.commit()
                            console.print(
                                f"  ✓ Saved to database (run_id: {run.run_id})"
                            )

                    except Exception as e:
                        console.print(f"  ❌ Database save failed: {e}", style="red")
                    finally:
                        await db_manager.close()

            console.print(f"\n✅ Enhanced parsing test completed!", style="green")

            if results:
                # Summary table
                table = Table(title="Parsing Results Summary")
                table.add_column("URL", style="cyan")
                table.add_column("Status", style="green")
                table.add_column("Title", style="white")
                table.add_column("Content", style="yellow")
                table.add_column("Links", style="blue")

                for test_url, result in results:
                    if result:
                        table.add_row(
                            test_url[:40] + "..." if len(test_url) > 40 else test_url,
                            "✓ Success",
                            (
                                result.get("title", "N/A")[:30] + "..."
                                if result.get("title")
                                and len(result.get("title", "")) > 30
                                else result.get("title", "N/A")
                            ),
                            f"{len(result.get('body_text', ''))} chars",
                            str(result.get("link_count", 0)),
                        )
                    else:
                        table.add_row(
                            test_url[:40] + "..." if len(test_url) > 40 else test_url,
                            "❌ Failed",
                            "N/A",
                            "0 chars",
                            "0",
                        )

                console.print(table)

        except Exception as e:
            console.print(f"❌ Test failed: {e}", style="red")
            import traceback

            console.print(traceback.format_exc(), style="red")
        finally:
            if parser:
                await parser.close()

    asyncio.run(_test())


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
