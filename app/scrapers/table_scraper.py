from typing import List, Dict, Any, Optional
from playwright.async_api import Page
from bs4 import BeautifulSoup
from datetime import datetime

from .base_scraper import BaseScraper, ScrapingResult, NotificationData
from ..utils.logger import log_execution_time

class TableScraper(BaseScraper):
    """Scraper implementation for tabular data structures"""
    
    def __init__(self, source_config: Dict[str, Any]):
        super().__init__(source_config)
        self.table_selector = source_config.get('table_selector', 'table')
        self.header_mapping = source_config.get('header_mapping', {})
    
    @log_execution_time
    async def extract_notifications(self, page: Page) -> ScrapingResult:
        try:
            # Wait for table to be present
            await page.wait_for_selector(self.table_selector, timeout=self.timeout)
            
            # Get table content
            table_html = await page.inner_html(self.table_selector)
            soup = BeautifulSoup(table_html, 'html.parser')
            
            # Extract headers and data
            headers = self._extract_headers(soup)
            rows = self._extract_rows(soup)
            
            notifications = []
            for row in rows:
                notification = self._process_row(row, headers)
                if notification:
                    notifications.append(notification)
            
            return ScrapingResult(
                success=True,
                notifications=[n.__dict__ for n in notifications],
                raw_content=table_html,
                page_size_kb=len(table_html) // 1024
            )
            
        except Exception as e:
            self.logger.error(f"Error extracting table data from {self.psu_name}: {str(e)}")
            return ScrapingResult(
                success=False,
                notifications=[],
                error_message=str(e)
            )
    
    async def validate_page_structure(self, page: Page) -> bool:
        """Validate if the page contains the expected table structure"""
        try:
            table = await page.query_selector(self.table_selector)
            if not table:
                return False
            
            # Check if table has rows
            rows = await table.query_selector_all('tr')
            return len(rows) > 1  # At least header and one data row
            
        except Exception as e:
            self.logger.error(f"Error validating table structure: {str(e)}")
            return False
    
    def _extract_headers(self, soup: BeautifulSoup) -> List[str]:
        """Extract and normalize table headers"""
        headers = []
        header_row = soup.find('tr')
        if header_row:
            for th in header_row.find_all(['th', 'td']):
                header = th.get_text(strip=True).lower()
                header = self.header_mapping.get(header, header)
                headers.append(header)
        return headers
    
    def _extract_rows(self, soup: BeautifulSoup) -> List[List[str]]:
        """Extract data rows from the table"""
        rows = []
        for tr in soup.find_all('tr')[1:]:  # Skip header row
            row = [td.get_text(strip=True) for td in tr.find_all(['td', 'th'])]
            if any(cell for cell in row):  # Skip empty rows
                rows.append(row)
        return rows
    
    def _process_row(self, row: List[str], headers: List[str]) -> Optional[NotificationData]:
        """Process a table row into a NotificationData object"""
        try:
            row_data = dict(zip(headers, row))
            
            # Extract required fields
            title = row_data.get('title') or row_data.get('description') or row_data.get('tender_name')
            if not title:
                return None
            
            notification = NotificationData(
                title=title,
                tender_id=row_data.get('tender_id') or row_data.get('reference_no'),
                location=row_data.get('location') or row_data.get('place'),
                category=row_data.get('category') or row_data.get('type'),
                start_date=self._parse_date(row_data.get('start_date') or row_data.get('publish_date')),
                end_date=self._parse_date(row_data.get('end_date') or row_data.get('closing_date')),
                raw_content=str(row_data),
                extracted_data=row_data
            )
            
            return notification
            
        except Exception as e:
            self.logger.error(f"Error processing row: {str(e)}")
            return None
    
    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime.date]:
        """Parse date string into datetime object"""
        if not date_str:
            return None
            
        try:
            # Try common date formats
            for fmt in ["%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d.%m.%Y"]:
                try:
                    return datetime.strptime(date_str.strip(), fmt).date()
                except ValueError:
                    continue
                    
            return None
            
        except Exception:
            return None