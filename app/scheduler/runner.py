import asyncio
from datetime import datetime
import signal
from typing import Optional

from ..utils.logger import get_logger
from .jobs import ScrapingJobs

logger = get_logger(__name__)

class SchedulerRunner:
    """Runner for managing the scheduler lifecycle"""
    
    def __init__(self):
        self.jobs = ScrapingJobs()
        self._shutdown = False
        self._shutdown_event = asyncio.Event()
    
    async def start(self):
        """Start the scheduler and set up signal handlers"""
        try:
            # Set up signal handlers
            for sig in (signal.SIGTERM, signal.SIGINT):
                signal.signal(sig, self._signal_handler)
            
            logger.info("Starting scheduler runner")
            await self.jobs.start()
            
            # Wait for shutdown signal
            await self._shutdown_event.wait()
            
        except Exception as e:
            logger.error(f"Error in scheduler runner: {e}")
            raise
        finally:
            await self.shutdown()
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info(f"Received signal {signum}")
        self._shutdown = True
        self._shutdown_event.set()
    
    async def shutdown(self):
        """Shutdown the scheduler gracefully"""
        logger.info("Shutting down scheduler runner")
        await self.jobs.stop()
    
    @classmethod
    async def run(cls):
        """Class method to run the scheduler"""
        runner = cls()
        await runner.start()

# Convenience function to run the scheduler
async def run_scheduler():
    """Run the scheduler"""
    await SchedulerRunner.run()

if __name__ == "__main__":
    asyncio.run(run_scheduler())