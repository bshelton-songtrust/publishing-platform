"""Tenant model for multi-tenant isolation."""

import uuid
from sqlalchemy import Column, String, CheckConstraint, Index, UUID
from sqlalchemy.dialects.postgresql import JSONB

from .base import TimestampMixin
from src.core.database import Base


class Tenant(Base, TimestampMixin):
    """
    Tenant model representing a publishing company or organization.
    All other entities belong to a tenant for data isolation.
    """
    
    __tablename__ = "tenants"
    
    # Primary key
    id = Column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4,
        comment="Primary key UUID"
    )
    
    # Basic information
    name = Column(
        String(255), 
        nullable=False,
        comment="Tenant organization name"
    )
    subdomain = Column(
        String(100), 
        unique=True, 
        nullable=False,
        comment="Unique subdomain identifier"
    )
    
    # Status and configuration
    status = Column(
        String(20), 
        default="active",
        nullable=False,
        comment="Tenant status: active, suspended, archived, trial"
    )
    plan_type = Column(
        String(50), 
        default="free",
        nullable=False,
        comment="Subscription plan: free, starter, professional, enterprise"
    )
    
    # Configuration and settings
    settings = Column(
        JSONB, 
        default=dict,
        comment="Tenant-specific configuration settings"
    )
    
    # Additional flexible data
    additional_data = Column(
        JSONB, 
        default=dict,
        comment="Additional metadata in JSON format"
    )

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'suspended', 'archived', 'trial')",
            name="valid_tenant_status"
        ),
        CheckConstraint(
            "plan_type IN ('free', 'starter', 'professional', 'enterprise')",
            name="valid_plan_type"
        ),
        Index("idx_tenants_subdomain", "subdomain"),
        Index("idx_tenants_status", "status"),
    )

    def __repr__(self) -> str:
        return f"<Tenant(id={self.id}, name='{self.name}', subdomain='{self.subdomain}')>"