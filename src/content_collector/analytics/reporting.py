"""Analytics and reporting for scraping operations."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
import structlog
from sqlalchemy import func, desc
from sqlalchemy.orm import selectinload

from content_collector.config.settings import settings
from content_collector.storage.database import db_manager
from content_collector.storage.models import Page, ScrapingRun, Domain

logger = structlog.get_logger(__name__)


class ReportGenerator:
    """Generate analytics reports for scraping operations."""
    
    def __init__(self):
        self.logger = logger.bind(component="reporting")
        
    async def generate_run_report(self, run_id: str) -> Dict[str, Any]:
        """Generate a comprehensive report for a specific scraping run."""
        try:
            async with db_manager.session() as session:
                # Get run details
                run = await session.get(ScrapingRun, run_id)
                if not run:
                    raise ValueError(f"Run {run_id} not found")
                
                # Get pages for this run
                from sqlalchemy import select
                pages_query = select(Page).where(Page.scraping_run_id == run_id)
                pages_result = await session.execute(pages_query)
                pages = pages_result.scalars().all()
                
                # Calculate statistics
                total_pages = len(pages)
                success_count = len([p for p in pages if p.status_code == 200])
                failure_count = total_pages - success_count
                
                # Domain distribution
                domain_counts = {}
                for page in pages:
                    domain_counts[page.domain] = domain_counts.get(page.domain, 0) + 1
                
                # Status code distribution
                status_counts = {}
                for page in pages:
                    status_counts[page.status_code] = status_counts.get(page.status_code, 0) + 1
                
                # Failed URLs with reasons
                failed_urls = [
                    {
                        "url": p.url,
                        "status_code": p.status_code,
                        "error": p.last_error,
                        "retry_count": p.retry_count
                    }
                    for p in pages if p.status_code != 200
                ]
                
                # Content statistics
                total_content_length = sum(p.content_length or 0 for p in pages)
                avg_content_length = total_content_length / total_pages if total_pages > 0 else 0
                
                report = {
                    "run_info": {
                        "run_id": run_id,
                        "status": run.status,
                        "start_time": run.created_at.isoformat() if run.created_at else None,
                        "end_time": run.updated_at.isoformat() if run.updated_at else None,
                        "input_file": run.input_file,
                        "max_depth": run.max_depth
                    },
                    "summary": {
                        "total_pages": total_pages,
                        "success_count": success_count,
                        "failure_count": failure_count,
                        "success_rate": (success_count / total_pages * 100) if total_pages > 0 else 0,
                        "total_content_bytes": total_content_length,
                        "avg_content_length": avg_content_length
                    },
                    "domains": {
                        "total_domains": len(domain_counts),
                        "distribution": dict(sorted(domain_counts.items(), key=lambda x: x[1], reverse=True))
                    },
                    "status_codes": status_counts,
                    "failures": {
                        "count": failure_count,
                        "details": failed_urls[:10]  # Top 10 failures
                    }
                }
                
                return report
                
        except Exception as e:
            self.logger.error("Failed to generate run report", run_id=run_id, error=str(e))
            raise
    
    async def generate_system_report(self, days: int = 7) -> Dict[str, Any]:
        """Generate system-wide analytics report."""
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            async with db_manager.session() as session:
                from sqlalchemy import select
                
                # Get all runs in period
                runs_query = select(ScrapingRun).where(ScrapingRun.created_at >= cutoff_date)
                runs_result = await session.execute(runs_query)
                runs = runs_result.scalars().all()
                
                # Get all pages in period
                pages_query = select(Page).where(Page.created_at >= cutoff_date)
                pages_result = await session.execute(pages_query)
                pages = pages_result.scalars().all()
                
                # Run statistics
                run_stats = {
                    "total_runs": len(runs),
                    "completed_runs": len([r for r in runs if r.status == "completed"]),
                    "failed_runs": len([r for r in runs if r.status == "failed"]),
                    "running_runs": len([r for r in runs if r.status == "running"])
                }
                
                # Page statistics
                total_pages = len(pages)
                successful_pages = len([p for p in pages if p.status_code == 200])
                
                # Domain analysis
                domain_counts = {}
                for page in pages:
                    domain_counts[page.domain] = domain_counts.get(page.domain, 0) + 1
                
                # Error analysis
                error_counts = {}
                for page in pages:
                    if page.status_code != 200:
                        error_counts[page.status_code] = error_counts.get(page.status_code, 0) + 1
                
                # Storage analysis
                total_content_size = sum(p.content_length or 0 for p in pages)
                
                # File system usage
                storage_stats = await self._get_storage_stats()
                
                report = {
                    "period": {
                        "days": days,
                        "start_date": cutoff_date.isoformat(),
                        "end_date": datetime.utcnow().isoformat()
                    },
                    "runs": run_stats,
                    "pages": {
                        "total_scraped": total_pages,
                        "successful": successful_pages,
                        "failed": total_pages - successful_pages,
                        "success_rate": (successful_pages / total_pages * 100) if total_pages > 0 else 0
                    },
                    "domains": {
                        "unique_domains": len(domain_counts),
                        "top_domains": dict(list(sorted(domain_counts.items(), key=lambda x: x[1], reverse=True))[:10])
                    },
                    "errors": {
                        "error_distribution": error_counts
                    },
                    "storage": {
                        "database_content_bytes": total_content_size,
                        "file_system": storage_stats
                    }
                }
                
                return report
                
        except Exception as e:
            self.logger.error("Failed to generate system report", error=str(e))
            raise
    
    async def _get_storage_stats(self) -> Dict[str, Any]:
        """Get file system storage statistics."""
        try:
            content_dir = settings.storage.content_dir
            if not content_dir.exists():
                return {"total_files": 0, "total_size_bytes": 0}
            
            total_files = 0
            total_size = 0
            
            for file_path in content_dir.rglob("*"):
                if file_path.is_file():
                    total_files += 1
                    total_size += file_path.stat().st_size
            
            return {
                "total_files": total_files,
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / (1024 * 1024), 2)
            }
            
        except Exception as e:
            self.logger.error("Failed to get storage stats", error=str(e))
            return {"total_files": 0, "total_size_bytes": 0, "error": str(e)}
    
    async def save_report(self, report: Dict[str, Any], filename: str) -> Path:
        """Save report to file."""
        try:
            reports_dir = settings.storage.reports_dir
            reports_dir.mkdir(parents=True, exist_ok=True)
            
            # Add timestamp to filename
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            filename_with_timestamp = f"{timestamp}_{filename}"
            
            file_path = reports_dir / filename_with_timestamp
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            
            self.logger.info("Report saved", file_path=str(file_path))
            return file_path
            
        except Exception as e:
            self.logger.error("Failed to save report", error=str(e))
            raise


# Global report generator instance
report_generator = ReportGenerator()