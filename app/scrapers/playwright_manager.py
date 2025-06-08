import asyncio
from typing import Optional, List, Dict, Any
from playwright.async_api import async_playwright, Browser, Playwright
from contextlib import asynccontextmanager
import time
from datetime import datetime, timedelta
import random

from ..config.settings import settings
from ..utils.logger import scraper_logger, get_logger

logger = get_logger(__name__)

class BrowserManager:
    """Manages Playwright browser instances with connection pooling"""
    
    def __init__(self, max_browsers: int = None, browser_type: str = 'chromium'):
        self.max_browsers = max_browsers or settings.max_concurrent_scrapers
        self.browser_type = browser_type
        self.playwright: Optional[Playwright] = None
        self.browsers: List[Browser] = []
        self.browser_usage: Dict[Browser, datetime] = {}
        self.lock = asyncio.Lock()
        self.logger = scraper_logger.logger
        
        # Browser configuration
        self.browser_args = [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--disable-background-timer-throttling',
            '--disable-backgrounding-occluded-windows',
            '--disable-renderer-backgrounding',
            '--disable-features=TranslateUI',
            '--disable-ipc-flooding-protection',
            '--disable-web-security',
            '--disable-features=VizDisplayCompositor'
        ]
        
        if settings.playwright_headless:
            self.browser_args.extend([
                '--headless',
                '--disable-gpu',
                '--no-first-run',
                '--no-default-browser-check'
            ])
    
    async def initialize(self):
        """Initialize Playwright and create initial browser pool"""
        try:
            self.playwright = await async_playwright().start()
            self.logger.info("Playwright initialized successfully")
            
            # Pre-create browsers up to max limit
            for i in range(min(2, self.max_browsers)):  # Start with 2 browsers
                browser = await self._create_browser()
                self.browsers.append(browser)
                self.browser_usage[browser] = datetime.now()
            
            self.logger.info(f"Created {len(self.browsers)} initial browser instances")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize Playwright: {e}")
            raise
    
    async def _create_browser(self) -> Browser:
        """Create a new browser instance"""
        try:
            if self.browser_type == 'chromium':
                browser = await self.playwright.chromium.launch(
                    headless=settings.playwright_headless,
                    args=self.browser_args,
                    timeout=30000
                )
            elif self.browser_type == 'firefox':
                browser = await self.playwright.firefox.launch(
                    headless=settings.playwright_headless,
                    timeout=30000
                )
            else:
                browser = await self.playwright.webkit.launch(
                    headless=settings.playwright_headless,
                    timeout=30000
                )
            
            self.logger.debug(f"Created new {self.browser_type} browser instance")
            return browser
            
        except Exception as e:
            self.logger.error(f"Failed to create browser: {e}")
            raise
    
    @asynccontextmanager
    async def get_browser(self):
        """Get a browser instance from the pool"""
        browser = None
        try:
            async with self.lock:
                # Try to get an available browser
                browser = await self._get_available_browser()
                if browser:
                    self.browser_usage[browser] = datetime.now()
            
            if not browser:
                raise Exception("No browser available")
            
            yield browser
            
        except Exception as e:
            self.logger.error(f"Browser manager error: {e}")
            raise
        finally:
            if browser:
                # Clean up any hanging contexts/pages
                await self._cleanup_browser_contexts(browser)
    
    async def _get_available_browser(self) -> Optional[Browser]:
        """Get an available browser from the pool"""
        # First, try to find an existing browser that's not busy
        for browser in self.browsers:
            if await self._is_browser_available(browser):
                return browser
        
        # If no available browser and we haven't reached the limit, create a new one
        if len(self.browsers) < self.max_browsers:
            try:
                browser = await self._create_browser()
                self.browsers.append(browser)
                self.browser_usage[browser] = datetime.now()
                return browser
            except Exception as e:
                self.logger.error(f"Failed to create new browser: {e}")
        
        # Wait for a browser to become available
        return await self._wait_for_available_browser()
    
    async def _is_browser_available(self, browser: Browser) -> bool:
        """Check if a browser is available for use"""
        try:
            # Check if browser is still connected
            if not browser.is_connected():
                return False
            
            # Check if browser has too many contexts
            contexts = browser.contexts
            if len(contexts) > 5:  # Arbitrary limit
                return False
            
            return True
            
        except Exception:
            return False
    
    async def _wait_for_available_browser(self, timeout: int = 30) -> Optional[Browser]:
        """Wait for a browser to become available"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            for browser in self.browsers:
                if await self._is_browser_available(browser):
                    return browser
            
            await asyncio.sleep(0.5)  # Short delay before checking again
        
        self.logger.warning("Timeout waiting for available browser")
        return None
    
    async def _cleanup_browser_contexts(self, browser: Browser):
        """Clean up browser contexts and pages"""
        try:
            contexts = browser.contexts
            for context in contexts:
                pages = context.pages
                for page in pages:
                    if not page.is_closed():
                        await page.close()
                await context.close()
        except Exception as e:
            self.logger.debug(f"Context cleanup error (non-critical): {e}")
    
    async def cleanup_idle_browsers(self, max_idle_time: int = 300):
        """Clean up browsers that have been idle for too long"""
        try:
            async with self.lock:
                current_time = datetime.now()
                browsers_to_remove = []
                
                for browser, last_used in self.browser_usage.items():
                    if (current_time - last_used).seconds > max_idle_time:
                        if len(self.browsers) > 1:  # Keep at least one browser
                            browsers_to_remove.append(browser)
                
                for browser in browsers_to_remove:
                    try:
                        await browser.close()
                        self.browsers.remove(browser)
                        del self.browser_usage[browser]
                        self.logger.info("Closed idle browser instance")
                    except Exception as e:
                        self.logger.error(f"Error closing idle browser: {e}")
                        
        except Exception as e:
            self.logger.error(f"Error during idle browser cleanup: {e}")
    
    async def get_browser_stats(self) -> Dict[str, Any]:
        """Get browser pool statistics"""
        try:
            active_browsers = 0
            total_contexts = 0
            total_pages = 0
            
            for browser in self.browsers:
                if browser.is_connected():
                    active_browsers += 1
                    contexts = browser.contexts
                    total_contexts += len(contexts)
                    for context in contexts:
                        total_pages += len(context.pages)
            
            return {
                'total_browsers': len(self.browsers),
                'active_browsers': active_browsers,
                'total_contexts': total_contexts,
                'total_pages': total_pages,
                'max_browsers': self.max_browsers
            }
            
        except Exception as e:
            self.logger.error(f"Error getting browser stats: {e}")
            return {}
    
    async def restart_unhealthy_browsers(self):
        """Restart browsers that appear to be unhealthy"""
        try:
            async with self.lock:
                unhealthy_browsers = []
                
                for browser in self.browsers:
                    if not browser.is_connected():
                        unhealthy_browsers.append(browser)
                
                for browser in unhealthy_browsers:
                    try:
                        # Remove from pool
                        self.browsers.remove(browser)
                        if browser in self.browser_usage:
                            del self.browser_usage[browser]
                        
                        # Try to close gracefully
                        try:
                            await browser.close()
                        except:
                            pass
                        
                        # Create replacement
                        new_browser = await self._create_browser()
                        self.browsers.append(new_browser)
                        self.browser_usage[new_browser] = datetime.now()
                        
                        self.logger.info("Restarted unhealthy browser instance")
                        
                    except Exception as e:
                        self.logger.error(f"Error restarting browser: {e}")
                        
        except Exception as e:
            self.logger.error(f"Error during browser health check: {e}")
    
    async def shutdown(self):
        """Shutdown all browsers and Playwright"""
        try:
            # Close all browsers
            for browser in self.browsers:
                try:
                    await browser.close()
                except Exception as e:
                    self.logger.error(f"Error closing browser during shutdown: {e}")
            
            # Clear browser pool
            self.browsers.clear()
            self.browser_usage.clear()
            
            # Stop Playwright
            if self.playwright:
                await self.playwright.stop()
                self.playwright = None
            
            self.logger.info("Browser manager shutdown completed")
            
        except Exception as e:
            self.logger.error(f"Error during browser manager shutdown: {e}")

class PlaywrightManager:
    """Manager for Playwright browser instances"""
    
    def __init__(self):
        self.browser: Optional[Browser] = None
        self.playwright = None
        self._lock = asyncio.Lock()
        
        # Browser pool configuration
        self.max_contexts = settings.max_browser_contexts
        self.active_contexts: Dict[str, BrowserContext] = {}
    
    async def initialize(self):
        """Initialize Playwright and browser"""
        if not self.playwright:
            self.playwright = await async_playwright().start()
            
            # Launch browser with appropriate options
            self.browser = await self.playwright.chromium.launch(
                headless=settings.playwright_headless,
                args=['--no-sandbox', '--disable-dev-shm-usage']
            )
            
            logger.info("Playwright and browser initialized")
    
    async def cleanup(self):
        """Clean up resources"""
        if self.browser:
            for context_id in list(self.active_contexts.keys()):
                await self._close_context(context_id)
            
            await self.browser.close()
            self.browser = None
        
        if self.playwright:
            await self.playwright.stop()
            self.playwright = None
        
        logger.info("Playwright resources cleaned up")
    
    @asynccontextmanager
    async def get_context(self) -> BrowserContext:
        """Get a browser context with retry logic"""
        if not self.browser:
            await self.initialize()
        
        context_id = None
        try:
            async with self._lock:
                # Clean up any stale contexts
                await self._cleanup_stale_contexts()
                
                # Create new context if under limit
                if len(self.active_contexts) >= self.max_contexts:
                    # Reuse least recently used context
                    context_id = min(self.active_contexts.keys())
                    context = self.active_contexts[context_id]
                else:
                    # Create new context
                    context = await self._create_context()
                    context_id = str(random.randint(1000, 9999))
                    self.active_contexts[context_id] = context
            
            yield context
            
        except Exception as e:
            logger.error(f"Error in browser context: {e}")
            if context_id:
                await self._close_context(context_id)
            raise
    
    async def _create_context(self) -> BrowserContext:
        """Create a new browser context with stealth settings"""
        context = await self.browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent=settings.default_user_agent,
            java_script_enabled=True,
            accept_downloads=False
        )
        
        # Add stealth mode script
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => false,
            });
        """)
        
        return context
    
    async def _close_context(self, context_id: str):
        """Close a browser context"""
        try:
            context = self.active_contexts.pop(context_id, None)
            if context:
                await context.close()
        except Exception as e:
            logger.error(f"Error closing context {context_id}: {e}")
    
    async def _cleanup_stale_contexts(self):
        """Clean up any stale contexts"""
        stale_contexts = []
        for context_id, context in self.active_contexts.items():
            try:
                # Check if context is still responsive
                await context.pages()
            except Exception:
                stale_contexts.append(context_id)
        
        for context_id in stale_contexts:
            await self._close_context(context_id)
    
    @staticmethod
    async def navigate_with_retry(
        page,
        url: str,
        max_retries: int = 3,
        timeout: int = None
    ) -> bool:
        """Navigate to URL with retry logic"""
        timeout = timeout or settings.page_timeout
        retries = 0
        
        while retries < max_retries:
            try:
                await page.goto(
                    url,
                    timeout=timeout,
                    wait_until='networkidle'
                )
                return True
                
            except PlaywrightTimeout:
                retries += 1
                if retries < max_retries:
                    delay = 2 ** retries  # Exponential backoff
                    logger.warning(f"Navigation timeout, retrying in {delay}s...")
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"Navigation failed after {max_retries} retries")
                    return False
                    
            except Exception as e:
                logger.error(f"Navigation error: {e}")
                return False
    
    @staticmethod
    async def extract_page_content(page, selector: str = None) -> str:
        """Extract content from page"""
        try:
            if selector:
                element = await page.wait_for_selector(selector)
                return await element.inner_text()
            else:
                return await page.content()
        except Exception as e:
            logger.error(f"Content extraction error: {e}")
            return ""

# Global browser manager instance
browser_manager = BrowserManager()

# Utility functions for browser management
async def initialize_browser_manager():
    """Initialize the global browser manager"""
    await browser_manager.initialize()

async def shutdown_browser_manager():
    """Shutdown the global browser manager"""
    await browser_manager.shutdown()

async def get_browser_instance():
    """Get a browser instance from the global manager"""
    async with browser_manager.get_browser() as browser:
        yield browser

# Health check and maintenance tasks
async def browser_maintenance_task():
    """Background task for browser maintenance"""
    while True:
        try:
            # Clean up idle browsers every 5 minutes
            await browser_manager.cleanup_idle_browsers()
            
            # Restart unhealthy browsers
            await browser_manager.restart_unhealthy_browsers()
            
            # Log browser stats
            stats = await browser_manager.get_browser_stats()
            scraper_logger.logger.debug(f"Browser stats: {stats}")
            
            # Wait 5 minutes before next maintenance cycle
            await asyncio.sleep(300)
            
        except Exception as e:
            scraper_logger.logger.error(f"Browser maintenance task error: {e}")
            await asyncio.sleep(60)  # Wait 1 minute on error