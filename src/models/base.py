"""Base model classes and mixins."""

import uuid
from datetime import datetime
from typing import Any, Dict

from sqlalchemy import Column, DateTime, String, Text, UUID, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declared_attr

from src.core.database import Base


class TimestampMixin:
    """Mixin for adding created_at and updated_at timestamps."""
    
    created_at = Column(
        DateTime(timezone=True), 
        default=func.now(), 
        nullable=False,
        comment="Record creation timestamp"
    )
    updated_at = Column(
        DateTime(timezone=True), 
        default=func.now(), 
        onupdate=func.now(), 
        nullable=False,
        comment="Record last update timestamp"
    )


class BaseModel(Base, TimestampMixin):
    """Base model class with common fields and functionality."""
    
    __abstract__ = True
    
    id = Column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4,
        comment="Primary key UUID"
    )
    
    # Tenant isolation - every record belongs to a tenant
    tenant_id = Column(
        UUID(as_uuid=True), 
        nullable=False,
        comment="Tenant UUID for multi-tenant isolation"
    )
    
    # Audit fields
    created_by = Column(
        UUID(as_uuid=True), 
        nullable=False,
        comment="User UUID who created this record"
    )
    
    # Additional data field for flexible information
    additional_data = Column(
        JSONB, 
        default=dict,
        comment="Additional metadata in JSON format"
    )

    @declared_attr
    def __tablename__(cls) -> str:
        """Generate table name from class name."""
        return cls.__name__.lower()

    def to_dict(self) -> Dict[str, Any]:
        """Convert model instance to dictionary."""
        result = {}
        for column in self.__table__.columns:
            value = getattr(self, column.name)
            if isinstance(value, datetime):
                value = value.isoformat()
            elif isinstance(value, uuid.UUID):
                value = str(value)
            result[column.name] = value
        return result

    def update_from_dict(self, data: Dict[str, Any]) -> None:
        """Update model instance from dictionary."""
        for key, value in data.items():
            if hasattr(self, key):
                setattr(self, key, value)

    def __repr__(self) -> str:
        """String representation of the model."""
        return f"<{self.__class__.__name__}(id={self.id})>"