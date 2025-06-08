from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Tuple
from playwright.async_api import Page, Browser, BrowserContext
from dataclasses import dataclass
from datetime import datetime, date
import re
import hashlib
import asyncio
from urllib.parse import urljoin, urlparse

from ..utils.logger import scraper_logger, log_execution_time
from ..config.settings import settings

@dataclass
class ScrapingResult:
    """Data class for scraping results"""
    success: bool
    notifications: List[Dict[str, Any]]
    error_message: Optional[str] = None
    execution_time: float = 0.0
    page_size_kb: Optional[int] = None
    raw_content: Optional[str] = None

@dataclass
class NotificationData:
    """Data class for individual notification"""
    title: str
    tender_id: Optional[str] = None
    location: Optional[str] = None
    category: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    raw_content: Optional[str] = None
    extracted_data: Optional[Dict[str, Any]] = None

class BaseScraper(ABC):
    """Abstract base class for all scrapers"""
    
    def __init__(self, source_config: Dict[str, Any]):
        self.source_config = source_config
        self.psu_name = source_config['psu_name']
        self.base_url = source_config['base_url']
        self.page_type = source_config.get('page_type', 'generic')
        self.source_id = source_config.get('id')
        
        # Scraping configuration
        self.timeout = settings.PAGE_TIMEOUT
        self.page_timeout = settings.PAGE_TIMEOUT
        self.delay_min = settings.SCRAPING_DELAY_MIN
        self.delay_max = settings.SCRAPING_DELAY_MAX

    @abstractmethod
    async def extract_notifications(self, page: Page) -> List[NotificationData]:
        """Extract notifications from the page - must be implemented by subclasses"""
        pass
    
    @abstractmethod
    async def validate_page_structure(self, page: Page) -> bool:
        """Validate if page structure matches expected format"""
        pass
    
    async def scrape(self, browser: Browser) -> ScrapingResult:
        """Main scraping method that orchestrates the entire process"""
        start_time = datetime.now()
        
        try:
            # Log scraping start
            
            # Create browser context with custom settings
            context = await self._create_browser_context(browser)
            page = await context.new_page()
            
            try:
                # Navigate to the page
                await self._navigate_to_page(page)
                
                # Wait for content to load
                await self._wait_for_content(page)
                
                # Validate page structure
                if not await self.validate_page_structure(page):
                    raise Exception("Page structure validation failed")
                
                # Extract notifications
                notifications = await self.extract_notifications(page)
                
                # Get page size for logging
                content = await page.content()
                page_size_kb = len(content.encode('utf-8')) // 1024
                
                # Convert NotificationData objects to dictionaries
                notification_dicts = [self._notification_to_dict(notif) for notif in notifications]
                
                execution_time = (datetime.now() - start_time).total_seconds()
                
                
                
                return ScrapingResult(
                    success=True,
                    notifications=notification_dicts,
                    execution_time=execution_time,
                    page_size_kb=page_size_kb,
                    raw_content=content
                )
                
            finally:
                await page.close()
                await context.close()
                
        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            error_msg = str(e)
            
            # scraper_logger.log_scraping_error(self.psu_name, error_msg)
            
            return ScrapingResult(
                success=False,
                notifications=[],
                error_message=error_msg,
                execution_time=execution_time
            )
    
    async def _create_browser_context(self, browser: Browser) -> BrowserContext:
        """Create browser context with custom settings"""
        return await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            ignore_https_errors=True,
            java_script_enabled=True
        )
    
    async def _navigate_to_page(self, page: Page):
        """Navigate to the target page with error handling"""
        try:
            response = await page.goto(
                self.base_url,
                wait_until='domcontentloaded',
                timeout=self.page_timeout * 1000
            )
            
            if response and response.status >= 400:
                raise Exception(f"HTTP {response.status}: Failed to load page")
                
        except Exception as e:
            raise Exception(f"Navigation failed: {str(e)}")
    
    async def _wait_for_content(self, page: Page):
        """Wait for page content to load completely"""
        try:
            # Wait for basic content
            await page.wait_for_load_state('networkidle', timeout=self.timeout * 1000)
            
            # Add random delay to appear more human-like
            import random
            delay = random.uniform(self.delay_min, self.delay_max)
            await asyncio.sleep(delay)
            
        except Exception as e:
            #self.logger.warning(f"Content loading timeout for {self.psu_name}: {str(e)}")
            print(f"Content loading timeout for {self.psu_name}: {str(e)}")
    
    def _notification_to_dict(self, notification: NotificationData) -> Dict[str, Any]:
        """Convert NotificationData to dictionary"""
        return {
            'title': notification.title,
            'tender_id': notification.tender_id,
            'location': notification.location,
            'category': notification.category,
            'start_date': notification.start_date,
            'end_date': notification.end_date,
            'raw_content': notification.raw_content,
            'extracted_data': notification.extracted_data or {}
        }
    
    def preprocess_content(self, content: str) -> str:
        """Clean and preprocess scraped content"""
        if not content:
            return ""
        
        # Remove extra whitespace
        content = re.sub(r'\s+', ' ', content.strip())
        
        # Remove special characters that might cause issues
        content = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\xff]', '', content)
        
        # Normalize quotes
        content = content.replace('"', '"').replace('"', '"')
        content = content.replace(''', "'").replace(''', "'")
        
        return content
    
    def extract_dates_from_text(self, text: str) -> Tuple[Optional[date], Optional[date]]:
        """Extract start and end dates from text using regex patterns"""
        if not text:
            return None, None
        
        # Common date patterns
        date_patterns = [
            r'\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b',  # DD/MM/YYYY or DD-MM-YYYY
            r'\b(\d{4})[/-](\d{1,2})[/-](\d{1,2})\b',  # YYYY/MM/DD or YYYY-MM-DD
            r'\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{4})\b',  # DD Mon YYYY
        ]
        
        dates_found = []
        
        for pattern in date_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                try:
                    if len(match.groups()) == 3:
                        if match.group(2).isalpha():  # Month name format
                            day, month_str, year = match.groups()
                            month_map = {
                                'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
                                'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
                            }
                            month = month_map.get(month_str[:3].lower())
                            if month:
                                parsed_date = date(int(year), month, int(day))
                                dates_found.append(parsed_date)
                        else:  # Numeric format
                            parts = [int(x) for x in match.groups()]
                            # Try different date formats
                            try:
                                if parts[2] > 31:  # YYYY-MM-DD
                                    parsed_date = date(parts[0], parts[1], parts[2])
                                else:  # DD-MM-YYYY
                                    parsed_date = date(parts[2], parts[1], parts[0])
                                dates_found.append(parsed_date)
                            except ValueError:
                                continue
                except (ValueError, IndexError):
                    continue
        
        # Sort dates and return start and end
        if dates_found:
            dates_found.sort()
            return dates_found[0], dates_found[-1] if len(dates_found) > 1 else dates_found[0]
        
        return None, None
    
    def extract_tender_id_from_text(self, text: str) -> Optional[str]:
        """Extract tender ID from text using common patterns"""
        if not text:
            return None
        
        # Common tender ID patterns
        patterns = [
            r'\b(?:Tender|RFP|RFQ|EOI|NIT)(?:\s*(?:No|ID|Ref))?[:\s#]*([A-Z0-9/-]+)\b',
            r'\b([A-Z]{2,}\d{2,}/[A-Z0-9/-]+)\b',
            r'\b(\d{4}/[A-Z0-9/-]+)\b',
            r'\b([A-Z]+\d+[A-Z]*\d*)\b'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        return None
    
    def extract_category_from_text(self, text: str) -> Optional[str]:
        """Extract category/type from text"""
        if not text:
            return None
        
        # Common categories
        categories = [
            'Construction', 'Civil Work', 'Electrical', 'Mechanical', 'IT Services',
            'Consultancy', 'Supply', 'Maintenance', 'Security', 'Catering',
            'Transportation', 'Housekeeping', 'Medical', 'Legal', 'Financial',
            'Engineering', 'Procurement', 'Installation', 'AMC', 'Software'
        ]
        
        text_lower = text.lower()
        for category in categories:
            if category.lower() in text_lower:
                return category
        
        return None
    
    def extract_location_from_text(self, text: str) -> Optional[str]:
        """Extract location from text"""
        if not text:
            return None
        
        # Look for location patterns
        location_patterns = [
            r'\b(?:at|in|for)\s+([A-Z][a-zA-Z\s]+(?:City|Town|District|State))\b',
            r'\b([A-Z][a-zA-Z\s]+,\s*[A-Z][a-zA-Z\s]+)\b',  # City, State format
            r'\b([A-Z][a-zA-Z]{3,}(?:\s+[A-Z][a-zA-Z]{3,})*)\b'  # Proper nouns
        ]
        
        for pattern in location_patterns:
            match = re.search(pattern, text)
            if match:
                location = match.group(1).strip()
                # Filter out common false positives
                false_positives = ['Terms', 'Conditions', 'Details', 'Information', 'Document']
                if location not in false_positives and len(location) > 3:
                    return location
        
        return None

class ScraperFactory:
    """Factory class to create appropriate scraper instances"""
    
    @staticmethod
    def create_scraper(source_config: Dict[str, Any]) -> BaseScraper:
        """Create appropriate scraper based on page type"""
        page_type = source_config.get('page_type', 'generic').lower()
        
        if page_type == 'table':
            from .table_scraper import TableScraper
            return TableScraper(source_config)
        elif page_type == 'list':
            from .list_scraper import ListScraper
            return ListScraper(source_config)
        else:
            from .generic_scraper import GenericScraper
            return GenericScraper(source_config)