from typing import List, Dict, Any, Optional
from playwright.async_api import Page, ElementHandle
from bs4 import BeautifulSoup
from datetime import datetime
import re

from .base_scraper import BaseScraper, ScrapingResult, NotificationData
from ..utils.logger import log_execution_time

class ListScraper(BaseScraper):
    """Scraper implementation for list-based notification pages"""
    
    def __init__(self, source_config: Dict[str, Any]):
        super().__init__(source_config)
        self.list_selector = source_config.get('list_selector', '.notifications-list, .tenders-list')
        self.item_selector = source_config.get('item_selector', 'li, .item, .notification')
        self.date_patterns = [
            r'(\d{2}[-./]\d{2}[-./]\d{4})',  # DD-MM-YYYY
            r'(\d{4}[-./]\d{2}[-./]\d{2})',  # YYYY-MM-DD
            r'(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4})'  # 15 January 2024
        ]
    
    @log_execution_time
    async def extract_notifications(self, page: Page) -> ScrapingResult:
        try:
            # Wait for list container
            await page.wait_for_selector(self.list_selector, timeout=self.timeout)
            
            # Get all notification items
            items = await page.query_selector_all(f"{self.list_selector} {self.item_selector}")
            
            notifications = []
            for item in items:
                notification = await self._process_item(item)
                if notification:
                    notifications.append(notification)
            
            content = await page.inner_html(self.list_selector)
            return ScrapingResult(
                success=True,
                notifications=[n.__dict__ for n in notifications],
                raw_content=content,
                page_size_kb=len(content) // 1024
            )
            
        except Exception as e:
            self.logger.error(f"Error extracting list data from {self.psu_name}: {str(e)}")
            return ScrapingResult(
                success=False,
                notifications=[],
                error_message=str(e)
            )
    
    async def validate_page_structure(self, page: Page) -> bool:
        """Validate if the page contains the expected list structure"""
        try:
            list_container = await page.query_selector(self.list_selector)
            if not list_container:
                return False
            
            # Check if there are list items
            items = await list_container.query_selector_all(self.item_selector)
            return len(items) > 0
            
        except Exception as e:
            self.logger.error(f"Error validating list structure: {str(e)}")
            return False
    
    async def _process_item(self, item: ElementHandle) -> Optional[NotificationData]:
        """Process a list item into a NotificationData object"""
        try:
            # Get item content
            content = await item.inner_html()
            soup = BeautifulSoup(content, 'html.parser')
            text = soup.get_text(strip=True)
            
            # Extract title (usually the main text or link text)
            title_elem = await item.query_selector('a, h3, h4, .title')
            title = await title_elem.inner_text() if title_elem else text
            if not title:
                return None
                
            # Extract dates from text
            dates = self._extract_dates(text)
            start_date, end_date = dates if dates else (None, None)
            
            # Try to extract tender ID using common patterns
            tender_id = self._extract_tender_id(text)
            
            # Look for location keywords
            location = self._extract_location(text)
            
            # Extract category if available
            category = await self._extract_category(item)
            
            notification = NotificationData(
                title=title.strip(),
                tender_id=tender_id,
                location=location,
                category=category,
                start_date=start_date,
                end_date=end_date,
                raw_content=content,
                extracted_data={'full_text': text}
            )
            
            return notification
            
        except Exception as e:
            self.logger.error(f"Error processing list item: {str(e)}")
            return None
    
    def _extract_dates(self, text: str) -> Optional[tuple[datetime.date, datetime.date]]:
        """Extract start and end dates from text"""
        try:
            dates = []
            for pattern in self.date_patterns:
                found_dates = re.findall(pattern, text)
                for date_str in found_dates:
                    try:
                        # Try parsing with different formats
                        for fmt in ["%d-%m-%Y", "%Y-%m-%d", "%d %B %Y", "%d %b %Y"]:
                            try:
                                date_obj = datetime.strptime(date_str, fmt).date()
                                dates.append(date_obj)
                                break
                            except ValueError:
                                continue
                    except Exception:
                        continue
            
            # Sort dates and return earliest and latest
            if len(dates) >= 2:
                dates.sort()
                return dates[0], dates[-1]
            elif len(dates) == 1:
                return dates[0], None
            return None
            
        except Exception:
            return None
    
    def _extract_tender_id(self, text: str) -> Optional[str]:
        """Extract tender ID using common patterns"""
        patterns = [
            r'tender\s+(?:no|number|id)[:.]\s*([A-Za-z0-9-_/]+)',
            r'ref(?:erence)?\s*(?:no|number|id)?[:.]\s*([A-Za-z0-9-_/]+)',
            r'(?:notification|tender)\s+([A-Za-z0-9-_/]{6,})'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None
    
    def _extract_location(self, text: str) -> Optional[str]:
        """Extract location information from text"""
        location_patterns = [
            r'(?:at|in|location[:]?)\s+([A-Za-z\s,]+(?:District|City|State|Region))',
            r'([A-Za-z\s]+(?:District|City|State|Region))',
        ]
        
        for pattern in location_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None
    
    async def _extract_category(self, item: ElementHandle) -> Optional[str]:
        """Extract category from item tags or classes"""
        try:
            # Check for category in dedicated elements
            category_elem = await item.query_selector('.category, .type, .tag')
            if category_elem:
                return await category_elem.inner_text()
            
            # Check element classes for category hints
            classes = await item.get_attribute('class')
            if classes:
                class_list = classes.split()
                for cls in class_list:
                    if cls.lower().endswith(('type', 'category')):
                        return cls.replace('-', ' ').replace('_', ' ').title()
            
            return None
            
        except Exception:
            return None