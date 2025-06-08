from sqlalchemy import create_engine, MetaData, select, update, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool
from contextlib import contextmanager, asynccontextmanager
from typing import Generator, List, Optional, Dict, Any
import logging
from datetime import datetime, date, timedelta
import hashlib
import json

from .models import PSUSource, Notification, ScrapingLog
from .connection import db_manager
from ..utils.logger import get_logger

logger = get_logger(__name__)

class DatabaseOperations:
    """Async database operations for PSU scraper"""
    
    def __init__(self):
        self.db_manager = db_manager
    
    # PSU Source Operations
    async def create_source(self, source_data: Dict[str, Any]) -> PSUSource:
        """Create a new PSU source"""
        async with self.db_manager.get_async_session() as session:
            source = PSUSource(**source_data)
            session.add(source)
            await session.flush()
            await session.refresh(source)
            logger.info(f"Created PSU source: {source.psu_name}")
            return source
    
    async def get_source(self, source_id: int) -> Optional[PSUSource]:
        """Get PSU source by ID"""
        async with self.db_manager.get_async_session() as session:
            stmt = select(PSUSource).where(PSUSource.id == source_id)
            result = await session.execute(stmt)
            return result.scalars().first()
    
    async def get_active_sources(self) -> List[PSUSource]:
        """Get all active PSU sources"""
        async with self.db_manager.get_async_session() as session:
            stmt = select(PSUSource).where(PSUSource.active == True)
            result = await session.execute(stmt)
            return result.scalars().all()
    
    async def update_source_status(
        self,
        source_id: int,
        success: bool = True,
        notifications_count: int = 0,
        error_message: str = None
    ) -> bool:
        """Update PSU source scraping status"""
        async with self.db_manager.get_async_session() as session:
            now = datetime.now()
            stmt = (
                update(PSUSource)
                .where(PSUSource.id == source_id)
                .values({
                    'last_scraped': now,
                    'last_success': now if success else None,
                    'success_count': PSUSource.success_count + (1 if success else 0),
                    'error_count': PSUSource.error_count + (0 if success else 1),
                    'updated_at': now
                })
            )
            await session.execute(stmt)
            return True
    
    # Notification Operations
    async def create_notifications(
        self,
        source_id: int,
        notifications: List[Dict[str, Any]]
    ) -> List[Notification]:
        """Create multiple notifications with duplicate checking"""
        async with self.db_manager.get_async_session() as session:
            result = []
            for data in notifications:
                # Generate content hash
                content = json.dumps(data, sort_keys=True)
                content_hash = hashlib.sha256(content.encode()).hexdigest()
                
                # Check for duplicates
                stmt = select(Notification).where(
                    and_(
                        Notification.source_id == source_id,
                        Notification.content_hash == content_hash
                    )
                )
                existing = await session.execute(stmt)
                if not existing.scalars().first():
                    notification = Notification(
                        source_id=source_id,
                        content_hash=content_hash,
                        **data
                    )
                    session.add(notification)
                    result.append(notification)
            
            if result:
                await session.flush()
                for notification in result:
                    await session.refresh(notification)
            
            return result
    
    async def get_notifications(
        self,
        source_id: Optional[int] = None,
        status: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Notification]:
        """Get notifications with filtering"""
        async with self.db_manager.get_async_session() as session:
            query = select(Notification)
            
            # Apply filters
            conditions = []
            if source_id:
                conditions.append(Notification.source_id == source_id)
            if status:
                conditions.append(Notification.status == status)
            if start_date:
                conditions.append(Notification.extracted_at >= start_date)
            if end_date:
                conditions.append(Notification.extracted_at <= end_date)
            
            if conditions:
                query = query.where(and_(*conditions))
            
            # Apply ordering and pagination
            query = query.order_by(desc(Notification.extracted_at))
            query = query.offset(offset).limit(limit)
            
            result = await session.execute(query)
            return result.scalars().all()
    
    # Scraping Log Operations
    async def create_scraping_log(self, log_data: Dict[str, Any]) -> ScrapingLog:
        """Create a scraping log entry"""
        async with self.db_manager.get_async_session() as session:
            log = ScrapingLog(**log_data)
            session.add(log)
            await session.flush()
            await session.refresh(log)
            return log
    
    async def get_recent_scraping_logs(
        self,
        source_id: Optional[int] = None,
        days: int = 7,
        limit: int = 100
    ) -> List[ScrapingLog]:
        """Get recent scraping logs"""
        async with self.db_manager.get_async_session() as session:
            query = select(ScrapingLog)
            
            conditions = []
            if source_id:
                conditions.append(ScrapingLog.source_id == source_id)
            if days:
                cutoff = datetime.now() - timedelta(days=days)
                conditions.append(ScrapingLog.scraped_at >= cutoff)
            
            if conditions:
                query = query.where(and_(*conditions))
            
            query = query.order_by(desc(ScrapingLog.scraped_at)).limit(limit)
            result = await session.execute(query)
            return result.scalars().all()

# Global database operations instance
db_ops = DatabaseOperations()