"""
Database models for product enrichment system.
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, Numeric, DateTime, Text, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all database models."""
    pass


class EnrichedProduct(Base):
    """
    Stores enriched product data from web crawling.
    
    UPC is the primary unique identifier.
    """
    __tablename__ = "enriched_products"
    
    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # Input data (what user provided)
    upc: Mapped[str] = mapped_column(String(13), unique=True, nullable=False, index=True)
    brand: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    product_name: Mapped[str] = mapped_column(Text, nullable=False)
    size: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    color: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Enriched data (what we found)
    msrp: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Metadata
    confidence_score: Mapped[int] = mapped_column(Integer, nullable=False)  # 0-100
    sources: Mapped[dict] = mapped_column(JSON, nullable=False)  # Which retailers confirmed this
    source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, 
        nullable=False, 
        default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )
    
    def __repr__(self) -> str:
        return f"<EnrichedProduct(upc={self.upc}, brand={self.brand}, confidence={self.confidence_score})>"
