"""Database models for content collector."""

from datetime import datetime
from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import uuid

Base = declarative_base()


class ScrapingRun(Base):
    """Model for tracking scraping runs."""
    __tablename__ = 'scraping_runs'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    input_file = Column(String, nullable=False)
    status = Column(String, nullable=False, default="running")  # running, completed, failed
    max_depth = Column(Integer, default=1)
    total_urls = Column(Integer, default=0)
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship to pages
    pages = relationship("Page", back_populates="scraping_run")


class Page(Base):
    """Model for storing scraped page information."""
    __tablename__ = 'pages'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    url = Column(String, nullable=False, index=True)
    scraping_run_id = Column(String, ForeignKey('scraping_runs.id'))
    parent_id = Column(String, ForeignKey('pages.id'))
    domain = Column(String, nullable=False, index=True)
    status_code = Column(Integer)
    depth = Column(Integer, nullable=False, default=0)
    
    # Content metadata
    content_hash = Column(String)
    title = Column(String)
    meta_description = Column(Text)
    content_type = Column(String)
    content_length = Column(Integer, default=0)
    
    # Error handling
    retry_count = Column(Integer, default=0)
    last_error = Column(Text)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    scraping_run = relationship("ScrapingRun", back_populates="pages")
    parent = relationship("Page", remote_side=[id])
    children = relationship("Page")


class Domain(Base):
    """Model for tracking domain-specific information."""
    __tablename__ = 'domains'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, unique=True, nullable=False, index=True)
    total_pages = Column(Integer, default=0)
    successful_pages = Column(Integer, default=0)
    failed_pages = Column(Integer, default=0)
    last_scraped = Column(DateTime)
    is_blocked = Column(Boolean, default=False)
    robots_txt_url = Column(String)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)