from typing import List, Dict, Any, Optional
from playwright.async_api import Page
from bs4 import BeautifulSoup
from datetime import datetime

from .base_scraper import BaseScraper, ScrapingResult, NotificationData
from ..llm.processor import LlamaProcessor
from ..utils.logger import log_execution_time

class GenericScraper(BaseScraper):
    """Scraper implementation for unstructured pages using LLM for extraction"""
    
    def __init__(self, source_config: Dict[str, Any]):
        super().__init__(source_config)
        self.content_selector = source_config.get('content_selector', 'main, #content, .content')
        self.llm_processor = LlamaProcessor(
            ollama_url=self.source_config.get('ollama_url'),
            model=self.source_config.get('llama_model')
        )
        
    @log_execution_time
    async def extract_notifications(self, page: Page) -> ScrapingResult:
        try:
            # Wait for main content
            await page.wait_for_selector(self.content_selector, timeout=self.timeout)
            
            # Get page content
            content = await page.inner_html(self.content_selector)
            text_content = await page.inner_text(self.content_selector)
            
            # Clean content
            cleaned_text = self._clean_text(text_content)
            
            # Use LLM to extract notifications
            extracted_data = await self.llm_processor.extract_notifications(
                cleaned_text,
                self.page_type
            )
            
            notifications = []
            for data in extracted_data:
                notification = self._create_notification(data)
                if notification:
                    notifications.append(notification)
            
            return ScrapingResult(
                success=True,
                notifications=[n.__dict__ for n in notifications],
                raw_content=content,
                page_size_kb=len(content) // 1024
            )
            
        except Exception as e:
            self.logger.error(f"Error extracting data from {self.psu_name} using LLM: {str(e)}")
            return ScrapingResult(
                success=False,
                notifications=[],
                error_message=str(e)
            )
    
    async def validate_page_structure(self, page: Page) -> bool:
        """Validate if the page contains any meaningful content"""
        try:
            content = await page.query_selector(self.content_selector)
            if not content:
                return False
            
            # Check if there's substantial text content
            text = await content.inner_text()
            return len(text.strip()) > 100  # At least 100 characters
            
        except Exception as e:
            self.logger.error(f"Error validating page content: {str(e)}")
            return False
    
    def _clean_text(self, text: str) -> str:
        """Clean and normalize text content"""
        # Remove extra whitespace
        text = ' '.join(text.split())
        
        # Remove common noise
        noise_patterns = [
            r'copyright ©.*$',
            r'all rights reserved',
            r'privacy policy',
            r'terms of use',
        ]
        
        for pattern in noise_patterns:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)
        
        return text.strip()
    
    def _create_notification(self, data: Dict[str, Any]) -> Optional[NotificationData]:
        """Create NotificationData from LLM extracted data"""
        try:
            # Require at least a title
            title = data.get('title') or data.get('description')
            if not title:
                return None
            
            # Parse dates if they're strings
            start_date = self._parse_date(data.get('start_date'))
            end_date = self._parse_date(data.get('end_date'))
            
            notification = NotificationData(
                title=title,
                tender_id=data.get('tender_id'),
                location=data.get('location'),
                category=data.get('category'),
                start_date=start_date,
                end_date=end_date,
                raw_content=str(data),
                extracted_data=data
            )
            
            return notification
            
        except Exception as e:
            self.logger.error(f"Error creating notification from LLM data: {str(e)}")
            return None
    
    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime.date]:
        """Parse date string into datetime object"""
        if not date_str:
            return None
            
        try:
            # Try common date formats
            for fmt in ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%d %B %Y", "%d %b %Y"]:
                try:
                    return datetime.strptime(date_str.strip(), fmt).date()
                except ValueError:
                    continue
            
            # If no format matches, let LLM try to parse it
            parsed_date = await self.llm_processor.parse_date(date_str)
            if parsed_date:
                return parsed_date
                    
            return None
            
        except Exception:
            return None