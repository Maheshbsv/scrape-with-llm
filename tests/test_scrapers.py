import pytest
import asyncio
from datetime import datetime
from playwright.async_api import Page

from app.scrapers.base_scraper import NotificationData
from app.scrapers.table_scraper import TableScraper
from app.scrapers.list_scraper import ListScraper
from app.scrapers.generic_scraper import GenericScraper
from app.scrapers.playwright_manager import PlaywrightManager
from app.database.operations import db_ops

# Test data
TEST_TABLE_HTML = """
<table>
    <tr>
        <th>Title</th>
        <th>Tender ID</th>
        <th>Location</th>
        <th>Start Date</th>
        <th>End Date</th>
    </tr>
    <tr>
        <td>Test Tender</td>
        <td>TEST001</td>
        <td>Mumbai</td>
        <td>2025-06-01</td>
        <td>2025-06-30</td>
    </tr>
</table>
"""

TEST_LIST_HTML = """
<div class="notifications-list">
    <div class="item">
        <h3>Sample Notification</h3>
        <p>Tender No: LIST001</p>
        <p>Location: Delhi</p>
        <p>Valid from: 1st June 2025 to 30th June 2025</p>
    </div>
</div>
"""

@pytest.fixture
async def browser_manager():
    manager = PlaywrightManager()
    await manager.initialize()
    yield manager
    await manager.cleanup()

@pytest.fixture
def table_source():
    return {
        'id': 1,
        'psu_name': 'Test PSU',
        'base_url': 'http://example.com/table',
        'page_type': 'table',
        'scrape_frequency_hours': 24,
        'active': True
    }

@pytest.fixture
def list_source():
    return {
        'id': 2,
        'psu_name': 'Test PSU',
        'base_url': 'http://example.com/list',
        'page_type': 'list',
        'scrape_frequency_hours': 24,
        'active': True
    }

@pytest.mark.asyncio
async def test_table_scraper(browser_manager, table_source):
    async with browser_manager.get_context() as context:
        page = await context.new_page()
        await page.set_content(TEST_TABLE_HTML)
        
        scraper = TableScraper(table_source)
        result = await scraper.extract_notifications(page)
        
        assert result.success
        assert len(result.notifications) == 1
        notification = NotificationData(**result.notifications[0])
        assert notification.tender_id == 'TEST001'
        assert notification.location == 'Mumbai'

@pytest.mark.asyncio
async def test_list_scraper(browser_manager, list_source):
    async with browser_manager.get_context() as context:
        page = await context.new_page()
        await page.set_content(TEST_LIST_HTML)
        
        scraper = ListScraper(list_source)
        result = await scraper.extract_notifications(page)
        
        assert result.success
        assert len(result.notifications) == 1
        notification = NotificationData(**result.notifications[0])
        assert notification.tender_id == 'LIST001'
        assert notification.location == 'Delhi'

@pytest.mark.asyncio
async def test_browser_manager():
    manager = PlaywrightManager()
    await manager.initialize()
    
    async with manager.get_context() as context:
        page = await context.new_page()
        await PlaywrightManager.navigate_with_retry(
            page,
            'http://example.com',
            max_retries=1
        )
        
        content = await PlaywrightManager.extract_page_content(page)
        assert content
    
    await manager.cleanup()

@pytest.mark.asyncio
async def test_database_operations():
    # Test source creation
    source_data = {
        'psu_name': 'Test PSU',
        'base_url': 'http://test.com',
        'page_type': 'table',
        'scrape_frequency_hours': 24
    }
    source = await db_ops.create_source(source_data)
    assert source.id
    assert source.psu_name == 'Test PSU'
    
    # Test notification creation
    notification_data = [{
        'title': 'Test Notification',
        'tender_id': 'TEST001',
        'location': 'Test Location',
        'start_date': datetime.now().date(),
        'end_date': datetime.now().date()
    }]
    notifications = await db_ops.create_notifications(source.id, notification_data)
    assert len(notifications) == 1
    assert notifications[0].tender_id == 'TEST001'
    
    # Test notification retrieval
    results = await db_ops.get_notifications(source_id=source.id)
    assert len(results) == 1
    assert results[0].title == 'Test Notification'