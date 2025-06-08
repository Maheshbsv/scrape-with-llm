# Detailed Implementation Plan: AI-Powered PSU Empanelment Scraper

## Project Overview
Build a web scraping system that monitors 25-50 PSU websites for empanelment notifications using Playwright for scraping and local Llama models for intelligent content extraction. The system will run daily batch jobs and provide a web dashboard for monitoring.

## Technology Stack
- **Backend**: FastAPI (Python 3.9+)
- **Web Scraping**: Playwright
- **LLM**: Ollama + Llama 3.1 8B (local)
- **Database**: PostgreSQL
- **Frontend**: HTML/CSS/JavaScript (simple dashboard)
- **Scheduler**: APScheduler
- **Data Export**: openpyxl for Excel generation
- **Containerization**: Docker (optional)

## Directory Structure
```
psu_scraper/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app entry point
│   ├── config/
│   │   ├── __init__.py
│   │   ├── settings.py         # App configuration
│   │   └── sites.csv           # PSU sites configuration
│   ├── database/
│   │   ├── __init__.py
│   │   ├── connection.py       # Database connection
│   │   ├── models.py           # SQLAlchemy models
│   │   └── operations.py       # Database CRUD operations
│   ├── scrapers/
│   │   ├── __init__.py
│   │   ├── base_scraper.py     # Abstract base scraper
│   │   ├── playwright_manager.py # Browser management
│   │   ├── table_scraper.py    # For tabular data sites
│   │   ├── list_scraper.py     # For list-based sites
│   │   └── generic_scraper.py  # LLM-powered fallback
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── processor.py        # Llama integration via Ollama
│   │   ├── prompts.py          # Structured prompts
│   │   └── validators.py       # Data validation logic
│   ├── scheduler/
│   │   ├── __init__.py
│   │   ├── jobs.py             # Scheduled job definitions
│   │   └── runner.py           # Job execution logic
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes.py           # API endpoints
│   │   └── schemas.py          # Pydantic models
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── logger.py           # Logging configuration
│   │   ├── excel_exporter.py   # Excel export functionality
│   │   └── helpers.py          # Utility functions
│   └── static/
│       ├── css/
│       │   └── dashboard.css
│       ├── js/
│       │   └── dashboard.js
│       └── templates/
│           └── dashboard.html
├── tests/
│   ├── __init__.py
│   ├── test_scrapers.py
│   ├── test_llm.py
│   └── test_api.py
├── requirements.txt
├── docker-compose.yml
├── Dockerfile
└── README.md
```

## Database Schema Design

### 1. PSU Sources Table
```sql
CREATE TABLE psu_sources (
    id SERIAL PRIMARY KEY,
    psu_name VARCHAR(100) NOT NULL,
    base_url TEXT NOT NULL UNIQUE,
    page_type VARCHAR(50) DEFAULT 'generic', -- table, list, generic
    scrape_frequency_hours INTEGER DEFAULT 24,
    active BOOLEAN DEFAULT true,
    last_scraped TIMESTAMP,
    last_success TIMESTAMP,
    success_count INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### 2. Notifications Table
```sql
CREATE TABLE notifications (
    id SERIAL PRIMARY KEY,
    source_id INTEGER REFERENCES psu_sources(id) ON DELETE CASCADE,
    tender_id VARCHAR(200),
    title TEXT NOT NULL,
    location VARCHAR(200),
    category VARCHAR(100),
    start_date DATE,
    end_date DATE,
    status VARCHAR(20) DEFAULT 'active', -- active, expired, cancelled
    raw_content TEXT,
    extracted_data JSONB, -- Store additional structured data
    content_hash VARCHAR(64) NOT NULL,
    extracted_at TIMESTAMP DEFAULT NOW(),
    is_new BOOLEAN DEFAULT true,
    UNIQUE(source_id, content_hash)
);

CREATE INDEX idx_notifications_source_id ON notifications(source_id);
CREATE INDEX idx_notifications_status ON notifications(status);
CREATE INDEX idx_notifications_end_date ON notifications(end_date);
```

### 3. Scraping Logs Table
```sql
CREATE TABLE scraping_logs (
    id SERIAL PRIMARY KEY,
    source_id INTEGER REFERENCES psu_sources(id) ON DELETE CASCADE,
    scraped_at TIMESTAMP DEFAULT NOW(),
    status VARCHAR(20) NOT NULL, -- success, error, partial, timeout
    notifications_found INTEGER DEFAULT 0,
    new_notifications INTEGER DEFAULT 0,
    error_message TEXT,
    execution_time_seconds FLOAT,
    page_size_kb INTEGER
);

CREATE INDEX idx_scraping_logs_source_id ON scraping_logs(source_id);
CREATE INDEX idx_scraping_logs_scraped_at ON scraping_logs(scraped_at);
```

### 4. Notification Queue Table (for future notifications)
```sql
CREATE TABLE notification_queue (
    id SERIAL PRIMARY KEY,
    notification_id INTEGER REFERENCES notifications(id) ON DELETE CASCADE,
    notification_type VARCHAR(50), -- email, slack, webhook
    recipient TEXT,
    status VARCHAR(20) DEFAULT 'pending', -- pending, sent, failed
    created_at TIMESTAMP DEFAULT NOW(),
    sent_at TIMESTAMP
);
```

## Component Implementation Details

### 1. Configuration Management (`config/settings.py`)
```python
from pydantic import BaseSettings
from typing import List

class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://user:password@localhost/psu_scraper"
    
    # LLM
    ollama_url: str = "http://localhost:11434"
    llama_model: str = "llama3.1:8b"
    
    # Scraping
    playwright_headless: bool = True
    request_timeout: int = 30
    max_concurrent_scrapers: int = 5
    
    # Scheduler
    scheduler_timezone: str = "Asia/Kolkata"
    daily_scrape_time: str = "08:00"
    
    # Export
    export_directory: str = "./exports"
    
    class Config:
        env_file = ".env"
```

### 2. Base Scraper Architecture (`scrapers/base_scraper.py`)
```python
from abc import ABC, abstractmethod
from typing import List, Dict, Any
from playwright.async_api import Page

class BaseScraper(ABC):
    def __init__(self, source_config: Dict[str, Any]):
        self.source_config = source_config
        self.psu_name = source_config['psu_name']
        self.base_url = source_config['base_url']
        
    @abstractmethod
    async def extract_notifications(self, page: Page) -> List[Dict[str, Any]]:
        """Extract notifications from the page"""
        pass
    
    @abstractmethod
    async def validate_page_structure(self, page: Page) -> bool:
        """Validate if page structure matches expected format"""
        pass
    
    def preprocess_content(self, content: str) -> str:
        """Clean and preprocess scraped content"""
        # Remove extra whitespace, normalize text
        pass
```

### 3. LLM Integration (`llm/processor.py`)
```python
import httpx
from typing import List, Dict, Any
import json

class LlamaProcessor:
    def __init__(self, ollama_url: str, model: str):
        self.ollama_url = ollama_url
        self.model = model
        self.client = httpx.AsyncClient(timeout=60.0)
    
    async def extract_notifications(self, content: str, page_type: str) -> List[Dict[str, Any]]:
        """Extract structured notification data using Llama"""
        prompt = self._build_extraction_prompt(content, page_type)
        response = await self._call_ollama(prompt)
        return self._parse_llm_response(response)
    
    async def classify_page_type(self, content: str) -> str:
        """Classify page structure type"""
        prompt = self._build_classification_prompt(content)
        response = await self._call_ollama(prompt)
        return response.strip().lower()
    
    def _build_extraction_prompt(self, content: str, page_type: str) -> str:
        """Build structured extraction prompt based on page type"""
        # Implementation details for different prompt strategies
        pass
```

### 4. Scheduler Implementation (`scheduler/jobs.py`)
```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import asyncio

class ScrapingScheduler:
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        
    async def start_daily_scraping(self):
        """Start daily scraping job"""
        self.scheduler.add_job(
            self.run_daily_scraping,
            CronTrigger(hour=8, minute=0),  # 8 AM daily
            id='daily_scraping',
            replace_existing=True
        )
        
    async def run_daily_scraping(self):
        """Execute daily scraping for all active sources"""
        # Implementation for orchestrating all scraping jobs
        pass
```

### 5. Web Dashboard (`api/routes.py`)
```python
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

app = FastAPI(title="PSU Empanelment Scraper Dashboard")
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main dashboard page"""
    return templates.TemplateResponse("dashboard.html", {"request": request})

@app.get("/api/sources")
async def get_sources():
    """Get all PSU sources with status"""
    pass

@app.get("/api/notifications")
async def get_notifications(limit: int = 100, status: str = None):
    """Get recent notifications with filtering"""
    pass

@app.get("/api/stats")
async def get_stats():
    """Get scraping statistics"""
    pass

@app.post("/api/export")
async def export_data(date_range: str = "30d"):
    """Export notifications to Excel"""
    pass
```

### 6. Excel Export (`utils/excel_exporter.py`)
```python
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment
from typing import List, Dict

class ExcelExporter:
    def __init__(self):
        self.workbook = Workbook()
        
    def export_notifications(self, notifications: List[Dict], filename: str):
        """Export notifications to Excel with formatting"""
        # Implementation for creating structured Excel output
        # Include sheets for: All Notifications, Active Tenders, Expired, Summary
        pass
    
    def add_summary_sheet(self, stats: Dict):
        """Add summary statistics sheet"""
        pass
```

## Implementation Phases

### Phase 1: Core Infrastructure (Week 1)
1. **Database Setup**
   - Create PostgreSQL database
   - Implement SQLAlchemy models
   - Create database operations layer
   - Write database migration scripts

2. **Configuration System**
   - Implement settings management
   - Create sites.csv structure
   - Build configuration validation

3. **Basic Playwright Integration**
   - Set up browser management
   - Implement basic page scraping
   - Add error handling and timeouts

### Phase 2: LLM Integration (Week 2)
1. **Ollama Setup**
   - Install and configure Ollama
   - Download Llama 3.1 8B model
   - Implement LLM processor class

2. **Prompt Engineering**
   - Design extraction prompts for different page types
   - Implement response parsing and validation
   - Create fallback mechanisms

3. **Scraper Architecture**
   - Implement base scraper class
   - Create specialized scrapers (table, list, generic)
   - Add content preprocessing

### Phase 3: Scheduling and Automation (Week 3)
1. **Job Scheduler**
   - Implement APScheduler integration
   - Create daily job orchestration
   - Add job monitoring and logging

2. **Data Processing Pipeline**
   - Implement notification extraction workflow
   - Add duplicate detection
   - Create data validation rules

3. **Error Handling**
   - Implement comprehensive error handling
   - Add retry mechanisms
   - Create failure notifications

### Phase 4: Web Dashboard and Export (Week 4)
1. **API Development**
   - Create FastAPI endpoints
   - Implement data filtering and pagination
   - Add real-time status updates

2. **Dashboard Frontend**
   - Create responsive HTML dashboard
   - Add JavaScript for dynamic updates
   - Implement data visualization (charts/graphs)

3. **Excel Export**
   - Implement Excel generation
   - Add formatting and multiple sheets
   - Create download functionality

### Phase 5: Testing and Deployment (Week 5)
1. **Testing**
   - Unit tests for core components
   - Integration tests for scraping workflow
   - End-to-end testing

2. **Deployment**
   - Create Docker containers
   - Set up docker-compose
   - Document deployment process

3. **Monitoring**
   - Add comprehensive logging
   - Create health check endpoints
   - Implement performance monitoring

## Key Features to Implement

### 1. Adaptive Scraping
- Automatic page type detection using LLM
- Fallback mechanisms when primary extraction fails
- Learning from successful extraction patterns

### 2. Data Quality Assurance
- Date format validation and standardization
- Duplicate detection using content hashing
- Data completeness checks

### 3. Scalability Considerations
- Concurrent scraping with rate limiting
- Browser pool management
- Efficient database queries with indexing

### 4. Monitoring and Alerting
- Scraping success/failure tracking
- Performance metrics collection
- Provision for future notification systems

### 5. User Experience
- Intuitive dashboard with real-time updates
- Easy Excel export with proper formatting
- Clear error messages and status indicators

## Configuration Files

### 1. sites.csv Format
```csv
psu_name,base_url,page_type,scrape_frequency_hours,active,notes
SBI,https://sbi.co.in/web/sbi-in-the-news/empanelment-of-vendors,table,24,true,Clean tabular format
ONGC,https://ongc.co.in/tenders/empanelment,list,24,true,List-based layout
IOCL,https://iocl.com/tenders,generic,24,true,Requires LLM parsing
```

### 2. requirements.txt
```
fastapi==0.104.1
uvicorn==0.24.0
playwright==1.40.0
sqlalchemy==2.0.23
asyncpg==0.29.0
apscheduler==3.10.4
httpx==0.25.2
pydantic==2.5.0
openpyxl==3.1.2
jinja2==3.1.2
python-multipart==0.0.6
```

## Success Metrics
1. **Reliability**: 95%+ successful scraping rate
2. **Accuracy**: 90%+ correct data extraction
3. **Performance**: Complete daily cycle within 2 hours
4. **Scalability**: Handle 50+ PSU sites without performance degradation
5. **Usability**: Intuitive dashboard requiring minimal training

## Risk Mitigation
1. **Site Changes**: LLM-powered adaptive extraction
2. **Rate Limiting**: Respectful scraping with delays
3. **System Failures**: Comprehensive error handling and logging
4. **Data Quality**: Multi-layer validation and manual review capabilities
5. **Scalability**: Modular architecture for easy expansion
