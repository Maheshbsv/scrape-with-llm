from pydantic_settings import BaseSettings
from pydantic import Field, validator
import os
from typing import Optional
from pathlib import Path

class Settings(BaseSettings):
    """Application settings using Pydantic"""
    
    # Project paths
    PROJECT_ROOT: Path = Path(__file__).parent.parent.parent
    LOG_DIR: Path = PROJECT_ROOT / "logs"
    EXPORT_DIR: Path = PROJECT_ROOT / "exports"
    
    # Scraping settings
    PLAYWRIGHT_HEADLESS: bool = True
    MAX_CONCURRENT_SCRAPERS: int = 3
    MAX_BROWSER_CONTEXTS: int = 5
    DEFAULT_USER_AGENT: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
    SCRAPING_DELAY_MIN: int = 1
    SCRAPING_DELAY_MAX: int = 5
    # Database
    DATABASE_URL: str = Field(
        default="postgresql://postgres:postgres@localhost/psu_scraper",
        description="Database connection string"
    )
    
    # LLM
    OLLAMA_URL: str = Field(
        default="http://localhost:11434",
        description="Ollama API endpoint"
    )
    LLAMA_MODEL: str = Field(
        default="llama2",
        description="Llama model name"
    )
    
    # Scraping
    PLAYWRIGHT_HEADLESS: bool = Field(
        default=True,
        description="Run browser in headless mode"
    )
    PAGE_TIMEOUT: int = Field(
        default=30000,
        description="Page load timeout in milliseconds"
    )
    MAX_BROWSER_CONTEXTS: int = Field(
        default=5,
        description="Maximum number of concurrent browser contexts"
    )
    DEFAULT_USER_AGENT: str = Field(
        default="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    )
    
    # Scheduler
    SCHEDULER_TIMEZONE: str = Field(
        default="Asia/Kolkata",
        description="Timezone for scheduler"
    )
    DAILY_SCRAPE_TIME: str = Field(
        default="08:00",
        description="Daily scraping time (24-hour format)"
    )
    MAX_CONCURRENT_SCRAPERS: int = Field(
        default=3,
        description="Maximum number of concurrent scrapers"
    )
    
    # API
    API_TITLE: str = "PSU Empanelment Scraper API"
    API_VERSION: str = "1.0.0"
    CORS_ORIGINS: list[str] = ["*"]
    
    # Logging
    LOG_LEVEL: str = Field(
        default="INFO",
        description="Logging level"
    )
    
    # Export
    EXPORT_CHUNK_SIZE: int = Field(
        default=1000,
        description="Number of records per Excel sheet"
    )
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        
    @validator("LOG_DIR", "EXPORT_DIR")
    def create_directories(cls, v: Path) -> Path:
        """Create directories if they don't exist"""
        v.mkdir(parents=True, exist_ok=True)
        return v
    
    @validator("DATABASE_URL")
    def validate_database_url(cls, v: str) -> str:
        """Validate database URL format"""
        if not v.startswith(("postgresql://", "postgresql+asyncpg://")):
            raise ValueError("Only PostgreSQL databases are supported")
        return v
    
    @validator("DAILY_SCRAPE_TIME")
    def validate_scrape_time(cls, v: str) -> str:
        """Validate scrape time format"""
        try:
            hour, minute = map(int, v.split(":"))
            if not (0 <= hour < 24 and 0 <= minute < 60):
                raise ValueError
        except ValueError:
            raise ValueError("Invalid time format. Use HH:MM (24-hour)")
        return v

# Create global settings instance
settings = Settings()