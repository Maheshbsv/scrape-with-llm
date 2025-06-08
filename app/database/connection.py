from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import create_engine, MetaData
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool
from contextlib import contextmanager, asynccontextmanager
from typing import Generator, AsyncGenerator, List, Optional, Dict, Any
import logging
from datetime import datetime, date, timedelta
import hashlib
import json

from .models import Base, PSUSource, Notification, ScrapingLog
from ..config.settings import settings
from ..utils.logger import get_logger

logger = get_logger(__name__)

class DatabaseManager:
    def __init__(self, database_url: str = None):
        self.database_url = database_url or settings.database_url
        self.engine = None
        self.async_engine = None
        self.SessionLocal = None
        self.AsyncSessionLocal = None
        self._initialize_engines()
    
    def _initialize_engines(self):
        """Initialize database engines and session factories"""
        try:
            # Sync engine for migrations and utility operations
            self.engine = create_engine(
                self.database_url,
                poolclass=NullPool,
                echo=settings.log_level.upper() == "DEBUG",
                pool_pre_ping=True
            )
            
            # Async engine for main application
            async_url = self.database_url.replace('postgresql://', 'postgresql+asyncpg://')
            self.async_engine = create_async_engine(
                async_url,
                echo=settings.log_level.upper() == "DEBUG",
                pool_pre_ping=True
            )
            
            # Session factories
            self.SessionLocal = sessionmaker(
                autocommit=False,
                autoflush=False,
                bind=self.engine
            )
            
            self.AsyncSessionLocal = async_sessionmaker(
                self.async_engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
            
            logger.info("Database engines initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize database engines: {e}")
            raise
    
    async def create_tables(self):
        """Create all tables"""
        try:
            async with self.async_engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables created successfully")
        except Exception as e:
            logger.error(f"Failed to create tables: {e}")
            raise
    
    def drop_tables(self):
        """Drop all tables (use with caution)"""
        try:
            Base.metadata.drop_all(bind=self.engine)
            logger.info("Database tables dropped successfully")
        except Exception as e:
            logger.error(f"Failed to drop tables: {e}")
            raise
    
    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """Get a synchronous database session"""
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    
    @asynccontextmanager
    async def get_async_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get an asynchronous database session"""
        session = self.AsyncSessionLocal()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

# Global database manager instance
db_manager = DatabaseManager()