from typing import List, Dict, Any
import asyncio
from datetime import datetime, timedelta
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from ..utils.logger import get_logger
from ..database.operations import get_active_sources, update_source_status
from ..database.models import ScrapingLog
from ..scrapers.playwright_manager import PlaywrightManager
from ..scrapers.table_scraper import TableScraper
from ..scrapers.list_scraper import ListScraper
from ..scrapers.generic_scraper import GenericScraper
from ..config.settings import settings

logger = get_logger(__name__)

class ScrapingJobs:
    """Manager for scraping job definitions and execution"""
    
    def __init__(self):
        self.browser_manager = PlaywrightManager()
        self.scheduler = AsyncIOScheduler(timezone=settings.scheduler_timezone)
        
    async def start(self):
        """Start the scheduler and initialize jobs"""
        if not self.scheduler.running:
            self.scheduler.start()
            await self._schedule_jobs()
            logger.info("Scheduler started successfully")
    
    async def stop(self):
        """Stop the scheduler and cleanup resources"""
        if self.scheduler.running:
            self.scheduler.shutdown()
            await self.browser_manager.cleanup()
            logger.info("Scheduler stopped")
    
    async def _schedule_jobs(self):
        """Schedule all required jobs"""
        # Daily scraping job
        self.scheduler.add_job(
            self._run_daily_scraping,
            CronTrigger(
                hour=settings.daily_scrape_time.split(':')[0],
                minute=settings.daily_scrape_time.split(':')[1]
            ),
            id='daily_scraping',
            replace_existing=True
        )
        
        # Hourly status check
        self.scheduler.add_job(
            self._check_scraping_status,
            IntervalTrigger(hours=1),
            id='status_check',
            replace_existing=True
        )
        
        # Cleanup job (daily at midnight)
        self.scheduler.add_job(
            self._cleanup_old_logs,
            CronTrigger(hour=0, minute=0),
            id='log_cleanup',
            replace_existing=True
        )
    
    async def _run_daily_scraping(self):
        """Execute daily scraping for all active sources"""
        try:
            sources = await get_active_sources()
            logger.info(f"Starting daily scraping for {len(sources)} sources")
            
            # Group sources by scraping frequency
            frequency_groups: Dict[int, List[Dict[str, Any]]] = {}
            for source in sources:
                freq = source.scrape_frequency_hours
                if freq not in frequency_groups:
                    frequency_groups[freq] = []
                frequency_groups[freq].append(source)
            
            # Process each frequency group
            for freq, group in frequency_groups.items():
                if self._should_scrape_frequency(freq):
                    await self._process_source_group(group)
            
            logger.info("Daily scraping completed")
            
        except Exception as e:
            logger.error(f"Error in daily scraping: {e}")
    
    async def _process_source_group(self, sources: List[Dict[str, Any]]):
        """Process a group of sources with concurrent scraping"""
        tasks = []
        semaphore = asyncio.Semaphore(settings.max_concurrent_scrapers)
        
        async def scrape_with_semaphore(source):
            async with semaphore:
                return await self._scrape_source(source)
        
        for source in sources:
            tasks.append(scrape_with_semaphore(source))
        
        await asyncio.gather(*tasks)
    
    async def _scrape_source(self, source: Dict[str, Any]):
        """Scrape a single source"""
        try:
            # Get appropriate scraper
            scraper = self._get_scraper(source)
            if not scraper:
                logger.error(f"No suitable scraper found for {source['psu_name']}")
                return
            
            # Initialize browser context
            context = await self.browser_manager.get_browser_context()
            
            # Execute scraping
            result = await scraper.extract_notifications(context)
            
            # Update source status
            await update_source_status(
                source['id'],
                success=result.success,
                notifications_count=len(result.notifications)
            )
            
            # Log scraping results
            await ScrapingLog.create(
                source_id=source['id'],
                status='success' if result.success else 'error',
                notifications_found=len(result.notifications),
                error_message=result.error_message,
                execution_time_seconds=result.execution_time,
                page_size_kb=result.page_size_kb
            )
            
        except Exception as e:
            logger.error(f"Error scraping {source['psu_name']}: {e}")
            await update_source_status(source['id'], success=False)
    
    def _get_scraper(self, source: Dict[str, Any]):
        """Get appropriate scraper for the source"""
        scrapers = {
            'table': TableScraper,
            'list': ListScraper,
            'generic': GenericScraper
        }
        
        scraper_class = scrapers.get(source['page_type'], GenericScraper)
        return scraper_class(source)
    
    def _should_scrape_frequency(self, frequency_hours: int) -> bool:
        """Check if sources with given frequency should be scraped"""
        current_hour = datetime.now(pytz.timezone(settings.scheduler_timezone)).hour
        return current_hour % frequency_hours == 0
    
    async def _check_scraping_status(self):
        """Check and report scraping status"""
        try:
            # Implement status checking logic
            pass
        except Exception as e:
            logger.error(f"Error checking scraping status: {e}")
    
    async def _cleanup_old_logs(self):
        """Clean up old logs and temporary files"""
        try:
            # Keep logs for 30 days
            cutoff_date = datetime.now() - timedelta(days=30)
            # Implement cleanup logic
            pass
        except Exception as e:
            logger.error(f"Error cleaning up logs: {e}")
    
    async def run_source_immediately(self, source_id: int):
        """Run scraping for a specific source immediately"""
        try:
            source = await get_active_sources(source_id=source_id)
            if source:
                await self._scrape_source(source)
                return True
            return False
        except Exception as e:
            logger.error(f"Error running immediate scrape for source {source_id}: {e}")
            return False