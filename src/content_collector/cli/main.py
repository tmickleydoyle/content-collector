"""Command-line interface for the content collector."""

import asyncio
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
import structlog

from content_collector.core.scraper import ScrapingEngine
from content_collector.storage.database import db_manager
from content_collector.analytics.reporting import report_generator

app = typer.Typer(help="Content Collector - Scalable web scraping tool")
console = Console()
logger = structlog.get_logger()


@app.command()
def init(
    create_db: bool = typer.Option(True, "--create-db/--no-create-db", help="Create database tables")
):
    """Initialize the content collector system."""
    console.print("🚀 Initializing Content Collector...", style="bold blue")
    
    async def _init():
        try:
            # Initialize database connection
            await db_manager.initialize()
            console.print("✅ Database connection established", style="green")
            
            if create_db:
                await db_manager.create_tables()
                console.print("✅ Database tables created", style="green")
            
            # Test database health
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
    input_file: Path = typer.Argument(..., help="Path to input file containing CSV paths"),
    max_pages: Optional[int] = typer.Option(None, "--max-pages", help="Maximum number of pages to scrape"),
    depth: int = typer.Option(1, "--depth", help="Maximum depth for recursive crawling")
):
    """Run the web scraper with the specified parameters."""
    console.print(f"🕷️  Starting scraping run...", style="bold blue")
    console.print(f"Input file: {input_file}")
    if max_pages:
        console.print(f"Max pages: {max_pages}")
    console.print(f"Max depth: {depth}")
    
    async def _run():
        scraper = ScrapingEngine()
        try:
            await db_manager.initialize()
            run_id = await scraper.run(input_file, max_pages)
            console.print(f"✅ Scraping completed! Run ID: {run_id}", style="green")
            return run_id
        except Exception as e:
            console.print(f"❌ Scraping failed: {e}", style="red")
            raise typer.Exit(1)
        finally:
            await db_manager.close()
    
    run_id = asyncio.run(_run())
    console.print(f"📊 Run ID for status/reports: {run_id}", style="cyan")


@app.command()
def status(
    run_id: Optional[str] = typer.Option(None, "--run-id", help="Specific run ID to check")
):
    """Show the current status of scraping runs."""
    console.print("📊 Checking scraper status...", style="bold blue")
    
    async def _status():
        try:
            await db_manager.initialize()
            
            if run_id:
                # Show specific run status
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
                # Show recent runs
                async with db_manager.session() as session:
                    from sqlalchemy import select, desc
                    from content_collector.storage.models import ScrapingRun
                    
                    query = select(ScrapingRun).order_by(desc(ScrapingRun.created_at)).limit(10)
                    result = await session.execute(query)
                    runs = result.scalars().all()
                    
                    if runs:
                        table = Table(title="Recent Scraping Runs")
                        table.add_column("Run ID", style="cyan")
                        table.add_column("Status", style="white")
                        table.add_column("URLs", style="green")
                        table.add_column("Created", style="yellow")
                        
                        for run in runs:
                            status_style = "green" if run.status == "completed" else "red" if run.status == "failed" else "yellow"
                            table.add_row(
                                run.id[:8] + "...",
                                f"[{status_style}]{run.status}[/{status_style}]",
                                str(run.total_urls),
                                str(run.created_at)[:19] if run.created_at else "N/A"
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
    run_id: Optional[str] = typer.Option(None, "--run-id", help="Generate report for specific run"),
    system: bool = typer.Option(False, "--system", help="Generate system-wide report"),
    save: bool = typer.Option(False, "--save", help="Save report to file"),
    days: int = typer.Option(7, "--days", help="Days to include in system report")
):
    """Generate analytics reports."""
    console.print("📈 Generating report...", style="bold blue")
    
    async def _report():
        try:
            await db_manager.initialize()
            
            if run_id:
                report_data = await report_generator.generate_run_report(run_id)
                
                # Display summary
                summary = report_data["summary"]
                table = Table(title=f"Run Report: {run_id[:8]}...")
                table.add_column("Metric", style="cyan")
                table.add_column("Value", style="white")
                
                table.add_row("Total Pages", str(summary["total_pages"]))
                table.add_row("Success Count", str(summary["success_count"]))
                table.add_row("Failure Count", str(summary["failure_count"]))
                table.add_row("Success Rate", f"{summary['success_rate']:.1f}%")
                table.add_row("Total Content", f"{summary['total_content_bytes']:,} bytes")
                
                console.print(table)
                
            elif system:
                report_data = await report_generator.generate_system_report(days)
                
                # Display system summary
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
                table.add_row("Unique Domains", str(report_data["domains"]["unique_domains"]))
                
                console.print(table)
                
            else:
                console.print("❌ Please specify --run-id or --system", style="red")
                raise typer.Exit(1)
            
            if save:
                filename = f"{'run_' + run_id if run_id else 'system'}_report.json"
                saved_path = await report_generator.save_report(report_data, filename)
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
    confirm: bool = typer.Option(False, "--confirm", help="Skip confirmation prompt")
):
    """Clean up old scraped content and data."""
    if not confirm:
        confirm = typer.confirm(f"⚠️  This will remove content older than {days} days. Continue?")
        if not confirm:
            console.print("Cleanup cancelled", style="yellow")
            return
    
    console.print(f"🧹 Cleaning up content older than {days} days...", style="bold blue")
    
    async def _cleanup():
        try:
            from content_collector.storage.file_storage import file_storage
            
            removed_count = await file_storage.cleanup_old_content(days)
            console.print(f"✅ Removed {removed_count} old content directories", style="green")
            
        except Exception as e:
            console.print(f"❌ Cleanup failed: {e}", style="red")
            raise typer.Exit(1)
    
    asyncio.run(_cleanup())


if __name__ == "__main__":
    app()