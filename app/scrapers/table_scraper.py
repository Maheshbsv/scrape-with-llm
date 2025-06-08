from typing import List, Dict, Any, Optional
from playwright.async_api import Page
from bs4 import BeautifulSoup
from datetime import datetime, date
import re

from .base_scraper import BaseScraper, NotificationData
from ..utils.logger import log_execution_time

class TableScraper(BaseScraper):
    """Scraper implementation for tabular data structures"""
    
    def __init__(self, source_config: Dict[str, Any]):
        super().__init__(source_config)
        self.table_selector = source_config.get('table_selector', 'table')
        self.header_mapping = source_config.get('header_mapping', {})
    
    @log_execution_time
    async def extract_notifications(self, page: Page) -> List[NotificationData]:
        """Extract notifications from table structure"""
        try:
            # Wait for table to be present
            await page.wait_for_selector(self.table_selector, timeout=self.timeout)
            
            # Get table content
            table_html = await page.inner_html(self.table_selector)
            soup = BeautifulSoup(table_html, 'html5lib')
            
            # Extract headers and data
            headers = self._extract_headers(soup)
            rows = self._extract_rows(soup)
            
            notifications = []
            for row in rows:
                notification = self._process_row(row, headers)
                if notification:
                    notifications.append(notification)
            print(f"Extracted {len(notifications)} notifications from {self.psu_name}")
            return notifications
            
        except Exception as e:
            # self.logger.error(f"Error extracting table data from {self.psu_name}: {str(e)}")
            return []

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
            # self.logger.error(f"Error validating table structure: {str(e)}")
            return False

    def _extract_headers(self, soup: BeautifulSoup) -> List[str]:
        """Extract and normalize table headers"""
        headers = []
        header_row = soup.select_one('tr')  # Use select_one instead of find
        if header_row:
            # Use select instead of find_all
            for th in header_row.select('th, td'):
                header = th.get_text(strip=True).lower()
                header = self.header_mapping.get(header, header)
                headers.append(header)
        return headers
    
    def _extract_rows(self, soup: BeautifulSoup) -> List[List[str]]:
        """Extract data rows from the table"""
        rows = []
        # Use select instead of find_all
        for tr in soup.select('tr')[1:]:  # Skip header row
            row = [td.get_text(strip=True) for td in tr.select('td, th')]
            if any(cell for cell in row):  # Skip empty rows
                rows.append(row)
        return rows
    
    def _parse_date(self, date_str: Optional[str]) -> Optional[date]:
        """Parse date string into date object"""
        if not date_str:
            return None
            
        try:
            # Remove any extra whitespace
            date_str = date_str.strip()
            
            # Common date formats
            formats = [
                '%d-%m-%Y', '%d/%m/%Y', '%Y-%m-%d', '%Y/%m/%d',
                '%d-%m-%y', '%d/%m/%y', '%y-%m-%d', '%y/%m/%d',
                '%d %b %Y', '%d %B %Y',
                '%b %d, %Y', '%B %d, %Y'
            ]
            
            # Try each format
            for fmt in formats:
                try:
                    return datetime.strptime(date_str, fmt).date()
                except ValueError:
                    continue
                    
            # If no format works, try to extract date using regex
            date_pattern = r'(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})'
            match = re.search(date_pattern, date_str)
            if match:
                day, month, year = map(int, match.groups())
                if year < 100:
                    year += 2000 if year < 50 else 1900
                return date(year, month, day)
                
        except Exception as e:
            #self.logger.warning(f"Failed to parse date '{date_str}': {str(e)}")
            print(f"Failed to parse date '{date_str}': {str(e)}")
            
        return None
    
    def _process_row(self, row: List[str], headers: List[str]) -> Optional[NotificationData]:
        """Process a table row into a NotificationData object"""
        try:
            row_data = dict(zip(headers, row))
            
            # Extract required fields
            title = row_data.get('title') or row_data.get('description') or row_data.get('tender_name')
            if not title:
                return None
            
            # Create notification object
            notification = NotificationData(
                title=title,
                tender_id=row_data.get('tender_id') or row_data.get('ref_no'),
                location=row_data.get('location'),
                category=row_data.get('category'),
                start_date=self._parse_date(row_data.get('start_date') or row_data.get('date_of_advertisement')),
                end_date=self._parse_date(row_data.get('end_date') or row_data.get('last_date')),
                raw_content=str(row_data),
                extracted_data=row_data
            )
            
            return notification
            
        except Exception as e:
            # self.logger.error(f"Error processing row {row}: {str(e)}")
            return None