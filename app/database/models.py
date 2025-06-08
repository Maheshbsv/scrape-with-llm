from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, Date, Float, ForeignKey, JSON, UniqueConstraint, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime, date
from typing import Optional, Dict, Any

Base = declarative_base()

class PSUSource(Base):
    __tablename__ = "psu_sources"
    
    id = Column(Integer, primary_key=True, index=True)
    psu_name = Column(String(100), nullable=False, index=True)
    base_url = Column(Text, nullable=False, unique=True)
    page_type = Column(String(50), default='generic')  # table, list, generic
    scrape_frequency_hours = Column(Integer, default=24)
    active = Column(Boolean, default=True, index=True)
    last_scraped = Column(DateTime, nullable=True)
    last_success = Column(DateTime, nullable=True)
    success_count = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    notifications = relationship("Notification", back_populates="source", cascade="all, delete-orphan")
    scraping_logs = relationship("ScrapingLog", back_populates="source", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<PSUSource(id={self.id}, psu_name='{self.psu_name}', active={self.active})>"

class Notification(Base):
    __tablename__ = "notifications"
    
    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, ForeignKey("psu_sources.id", ondelete="CASCADE"), nullable=False, index=True)
    tender_id = Column(String(200), nullable=True, index=True)
    title = Column(Text, nullable=False)
    location = Column(String(200), nullable=True)
    category = Column(String(100), nullable=True)
    start_date = Column(Date, nullable=True, index=True)
    end_date = Column(Date, nullable=True, index=True)
    status = Column(String(20), default='active', index=True)  # active, expired, cancelled
    raw_content = Column(Text, nullable=True)
    extracted_data = Column(JSON, nullable=True)  # Store additional structured data
    content_hash = Column(String(64), nullable=False, index=True)
    extracted_at = Column(DateTime, default=func.now(), index=True)
    is_new = Column(Boolean, default=True, index=True)
    
    # Relationships
    source = relationship("PSUSource", back_populates="notifications")
    
    # Unique constraint to prevent duplicates
    __table_args__ = (
        UniqueConstraint('source_id', 'content_hash', name='uq_source_content_hash'),
        Index('idx_notifications_dates', 'start_date', 'end_date'),
        Index('idx_notifications_search', 'title', 'category'),
    )
    
    def __repr__(self):
        return f"<Notification(id={self.id}, title='{self.title[:50]}...', status='{self.status}')>"
    
    @property
    def is_expired(self) -> bool:
        """Check if notification is expired based on end_date"""
        if self.end_date:
            return self.end_date < date.today()
        return False
    
    @property
    def days_remaining(self) -> Optional[int]:
        """Calculate days remaining until end_date"""
        if self.end_date:
            delta = self.end_date - date.today()
            return delta.days if delta.days >= 0 else 0
        return None

class ScrapingLog(Base):
    __tablename__ = "scraping_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, ForeignKey("psu_sources.id", ondelete="CASCADE"), nullable=False, index=True)
    scraped_at = Column(DateTime, default=func.now(), index=True)
    status = Column(String(20), nullable=False, index=True)  # success, error, partial, timeout
    notifications_found = Column(Integer, default=0)
    new_notifications = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    execution_time_seconds = Column(Float, nullable=True)
    page_size_kb = Column(Integer, nullable=True)
    
    # Relationships
    source = relationship("PSUSource", back_populates="scraping_logs")
    
    def __repr__(self):
        return f"<ScrapingLog(id={self.id}, source_id={self.source_id}, status='{self.status}')>"

class NotificationQueue(Base):
    __tablename__ = "notification_queue"
    
    id = Column(Integer, primary_key=True, index=True)
    notification_id = Column(Integer, ForeignKey("notifications.id", ondelete="CASCADE"), nullable=False)
    notification_type = Column(String(50), nullable=False)  # email, slack, webhook
    recipient = Column(Text, nullable=False)
    status = Column(String(20), default='pending', index=True)  # pending, sent, failed
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now(), index=True)
    sent_at = Column(DateTime, nullable=True)
    
    def __repr__(self):
        return f"<NotificationQueue(id={self.id}, type='{self.notification_type}', status='{self.status}')>"

# Additional helper tables for future enhancements

class ScrapingConfig(Base):
    __tablename__ = "scraping_configs"
    
    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, ForeignKey("psu_sources.id", ondelete="CASCADE"), nullable=False)
    config_key = Column(String(100), nullable=False)
    config_value = Column(Text, nullable=True)
    config_type = Column(String(20), default='string')  # string, json, boolean, integer
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        UniqueConstraint('source_id', 'config_key', name='uq_source_config_key'),
    )

class AuditLog(Base):
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    table_name = Column(String(50), nullable=False, index=True)
    record_id = Column(Integer, nullable=False)
    action = Column(String(20), nullable=False, index=True)  # insert, update, delete
    old_values = Column(JSON, nullable=True)
    new_values = Column(JSON, nullable=True)
    changed_by = Column(String(100), nullable=True)
    changed_at = Column(DateTime, default=func.now(), index=True)
    
    def __repr__(self):
        return f"<AuditLog(id={self.id}, table='{self.table_name}', action='{self.action}')>"