"""Base model classes and mixins."""

import uuid
from datetime import datetime
from typing import Any, Dict

from sqlalchemy import Column, DateTime, String, Text, UUID, func, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.orm import relationship

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
    """
    Base model class with common fields and functionality.
    
    Provides multi-tenant publisher isolation, user audit trails, and standard
    timestamp tracking. All catalog entities inherit from this base model to ensure
    consistent publisher-level data isolation and audit capabilities.
    
    Key Features:
    - Publisher-based multi-tenant isolation (publisher_id)
    - User audit trails (created_by, updated_by with User relationships)
    - Timestamp tracking (created_at, updated_at)
    - Flexible metadata storage (additional_data JSONB)
    - Backward compatibility (tenant_id property alias)
    """
    
    __abstract__ = True
    
    id = Column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4,
        comment="Primary key UUID"
    )
    
    # Publisher isolation - every record belongs to a publisher (tenant)
    publisher_id = Column(
        UUID(as_uuid=True), 
        ForeignKey("publishers.id", ondelete="CASCADE"),
        nullable=False,
        comment="Publisher UUID for multi-tenant isolation"
    )
    
    # Audit fields with user relationships
    created_by = Column(
        UUID(as_uuid=True), 
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        comment="User UUID who created this record"
    )
    
    updated_by = Column(
        UUID(as_uuid=True), 
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
        comment="User UUID who last updated this record"
    )
    
    # Additional data field for flexible information
    additional_data = Column(
        JSONB, 
        default=dict,
        comment="Additional metadata in JSON format"
    )

    # Relationships
    @declared_attr
    def publisher(cls):
        return relationship("Publisher", lazy="select")
    
    @declared_attr 
    def created_by_user(cls):
        return relationship("User", foreign_keys=[cls.created_by], lazy="select")
    
    @declared_attr
    def updated_by_user(cls):
        return relationship("User", foreign_keys=[cls.updated_by], lazy="select")

    # Backward compatibility property
    @property
    def tenant_id(self) -> uuid.UUID:
        """Backward compatibility alias for publisher_id."""
        return self.publisher_id
    
    @tenant_id.setter
    def tenant_id(self, value: uuid.UUID) -> None:
        """Backward compatibility setter for publisher_id."""
        self.publisher_id = value

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

    def update_from_dict(self, data: Dict[str, Any], updated_by_user_id: uuid.UUID = None) -> None:
        """Update model instance from dictionary."""
        for key, value in data.items():
            if hasattr(self, key):
                setattr(self, key, value)
        
        # Automatically set updated_by if provided
        if updated_by_user_id:
            self.updated_by = updated_by_user_id
    
    def set_audit_fields(self, created_by_user_id: uuid.UUID, updated_by_user_id: uuid.UUID = None) -> None:
        """Set audit trail fields for user tracking."""
        if not self.created_by:
            self.created_by = created_by_user_id
        
        if updated_by_user_id:
            self.updated_by = updated_by_user_id
    
    def get_audit_info(self) -> Dict[str, Any]:
        """Get audit trail information."""
        return {
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "created_by": self.created_by,
            "updated_by": self.updated_by,
            "publisher_id": self.publisher_id
        }

    def __repr__(self) -> str:
        """String representation of the model."""
        return f"<{self.__class__.__name__}(id={self.id})>"