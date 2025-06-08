import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from app.scrapers.table_scraper import TableScraper
from app.scrapers.playwright_manager import PlaywrightManager
from app.database.connection import db_manager
from app.config.settings import settings

async def scrape_sbi():
    # Initialize browser manager
    browser_manager = PlaywrightManager()
    await browser_manager.initialize()
    
    try:
        # Configure source        
        source_config = {
            'id': 1,
            'psu_name': 'SBI',
            'base_url': 'https://sbi.co.in/web/sbi-in-the-news/empanelment-of-vendors',
            'page_type': 'table',
            'scrape_frequency_hours': 24,
            'active': True,
            'table_selector': '.table.table-bordered',
            'header_mapping': {
                'sr no': 'tender_id',
                'advertisement': 'title',
                'location': 'location',
                'date of advertisement': 'start_date',
                'last date': 'end_date'
            }
        }
        
        # Create scraper instance
        scraper = TableScraper(source_config)
        
        # Get browser context
        async with browser_manager.get_context() as context:
            # Create new page
            page = await context.new_page()
            
            # Navigate to URL
            success = await PlaywrightManager.navigate_with_retry(
                page,
                source_config['base_url'],
                max_retries=3
            )
            
            if success:
                # Extract notifications
                result = await scraper.extract_notifications(page)
                
                if result.success:
                    print(f"\nFound {len(result.notifications)} notifications:")
                    for notif in result.notifications:
                        print(f"\n- Title: {notif['title']}")
                        print(f"  Tender ID: {notif.get('tender_id')}")
                        print(f"  Location: {notif.get('location')}")
                        print(f"  Start Date: {notif.get('start_date')}")
                        print(f"  End Date: {notif.get('end_date')}")
                else:
                    print(f"\nError: {result.error_message}")
            else:
                print("\nFailed to load the page")
    
    finally:
        await browser_manager.cleanup()

if __name__ == "__main__":
    asyncio.run(scrape_sbi())
