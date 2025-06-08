import logging
import os
import asyncio
from datetime import datetime
from functools import wraps
import time
from typing import Callable, Any

# Base configuration
LOG_FORMAT = '%(asctime)s | %(name)s | %(levelname)s | %(message)s'
LOG_DIR = "logs"

def setup_logger(name: str, level: str = "INFO") -> logging.Logger:
    """Set up and configure a logger instance"""
    # Create logs directory if it doesn't exist
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)
    
    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Remove existing handlers
    logger.handlers.clear()
    
    # File handler - separate file for each module
    file_handler = logging.FileHandler(
        os.path.join(LOG_DIR, f"{name.replace('.', '_')}_{datetime.now().strftime('%Y%m%d')}.log")
    )
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    logger.addHandler(file_handler)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    logger.addHandler(console_handler)
    
    return logger

# Create loggers for different components
scraper_logger = setup_logger('psu_scraper.scraper')
llm_logger = setup_logger('psu_scraper.llm')
api_logger = setup_logger('psu_scraper.api')
scheduler_logger = setup_logger('psu_scraper.scheduler')

def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for a module"""
    return setup_logger(f"psu_scraper.{name}")

def log_execution_time(func: Callable) -> Callable:
    """Decorator to log function execution time"""
    @wraps(func)
    async def async_wrapper(*args, **kwargs) -> Any:
        start_time = time.time()
        try:
            result = await func(*args, **kwargs)
            execution_time = time.time() - start_time
            get_logger(func.__module__).debug(
                f"{func.__name__} executed in {execution_time:.2f} seconds"
            )
            return result
        except Exception as e:
            execution_time = time.time() - start_time
            get_logger(func.__module__).error(
                f"{func.__name__} failed after {execution_time:.2f} seconds: {str(e)}"
            )
            raise
    
    @wraps(func)
    def sync_wrapper(*args, **kwargs) -> Any:
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            execution_time = time.time() - start_time
            get_logger(func.__module__).debug(
                f"{func.__name__} executed in {execution_time:.2f} seconds"
            )
            return result
        except Exception as e:
            execution_time = time.time() - start_time
            get_logger(func.__module__).error(
                f"{func.__name__} failed after {execution_time:.2f} seconds: {str(e)}"
            )
            raise
    
    return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper