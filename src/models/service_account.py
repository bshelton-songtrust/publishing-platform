"""ServiceAccount model for external system authentication."""

import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List
import secrets
import hashlib

from sqlalchemy import (
    Column, String, Boolean, DateTime, CheckConstraint, 
    Index, UUID, Text, ForeignKey, func, Integer, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import JSONB, ARRAY, INET
from sqlalchemy.orm import relationship, validates

from .base import TimestampMixin
from src.core.database import Base


class ServiceAccount(Base, TimestampMixin):
    """
    ServiceAccount model for managing external system authentication.
    
    This model handles:
    - Service identity and authentication for external systems
    - API key management for services like Songtrust, Spirit
    - Rate limiting and quota management
    - IP restriction and security controls
    - Webhook configuration for events
    - Usage tracking and analytics
    
    Use Cases:
    - Songtrust platform accessing creator catalogs
    - Spirit publisher systems accessing their catalog
    - Third-party integrations (royalty systems, distribution)
    - CI/CD pipelines and automation tools
    - Analytics and reporting systems
    
    Security Features:
    - IP allowlist/blocklist
    - Rate limiting per service
    - Scoped permissions
    - Automatic token rotation
    - Usage monitoring and alerts
    """
    
    __tablename__ = "service_accounts"
    
    # Core Identity Fields
    id = Column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4,
        comment="Primary key UUID for service account"
    )
    
    # Service Identity
    name = Column(
        String(100),
        nullable=False,
        unique=True,
        comment="Unique service account name (e.g., 'songtrust-api', 'spirit-integration')"
    )
    
    display_name = Column(
        String(255),
        nullable=False,
        comment="Human-readable display name for the service"
    )
    
    description = Column(
        Text,
        comment="Detailed description of the service and its purpose"
    )
    
    service_type = Column(
        String(50),
        nullable=False,
        default="external",
        comment="Type of service: external, internal, partner, automation"
    )
    
    # Publisher Association
    publisher_id = Column(
        UUID(as_uuid=True),
        ForeignKey("publishers.id", ondelete="CASCADE"),
        nullable=True,
        comment="Associated publisher (null for cross-publisher services)"
    )
    
    # Owner Information
    owner_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="User who owns/manages this service account"
    )
    
    owner_email = Column(
        String(255),
        nullable=False,
        comment="Contact email for service account issues"
    )
    
    # Status and Lifecycle
    status = Column(
        String(20),
        nullable=False,
        default="active",
        comment="Service account status: active, suspended, revoked, expired"
    )
    
    is_active = Column(
        Boolean,
        default=True,
        nullable=False,
        comment="Whether the service account is currently active"
    )
    
    suspended_at = Column(
        DateTime(timezone=True),
        comment="Timestamp when service was suspended"
    )
    
    suspended_reason = Column(
        Text,
        comment="Reason for suspension"
    )
    
    expires_at = Column(
        DateTime(timezone=True),
        comment="Expiration date for the service account"
    )
    
    # Permissions and Scopes
    scopes = Column(
        ARRAY(String),
        default=list,
        comment="Array of permission scopes (e.g., ['catalog:read', 'works:create'])"
    )
    
    permissions = Column(
        JSONB,
        default=dict,
        comment="Detailed permissions configuration"
    )
    
    # Specific access restrictions
    allowed_resources = Column(
        JSONB,
        default=dict,
        comment="Specific resources this service can access (e.g., specific catalogs)"
    )
    
    # Rate Limiting
    rate_limit_per_minute = Column(
        Integer,
        default=60,
        comment="Maximum requests per minute"
    )
    
    rate_limit_per_hour = Column(
        Integer,
        default=1000,
        comment="Maximum requests per hour"
    )
    
    rate_limit_per_day = Column(
        Integer,
        default=10000,
        comment="Maximum requests per day"
    )
    
    burst_limit = Column(
        Integer,
        default=10,
        comment="Maximum burst requests allowed"
    )
    
    # IP Restrictions
    allowed_ips = Column(
        ARRAY(INET),
        default=list,
        comment="List of allowed IP addresses/ranges"
    )
    
    blocked_ips = Column(
        ARRAY(INET),
        default=list,
        comment="List of blocked IP addresses/ranges"
    )
    
    require_ip_allowlist = Column(
        Boolean,
        default=False,
        comment="Whether to enforce IP allowlist"
    )
    
    # Webhook Configuration
    webhook_url = Column(
        String(500),
        comment="Webhook URL for sending events to the service"
    )
    
    webhook_secret = Column(
        String(255),
        comment="Secret for webhook signature verification"
    )
    
    webhook_events = Column(
        ARRAY(String),
        default=list,
        comment="List of events to send via webhook"
    )
    
    # Usage Tracking
    last_used_at = Column(
        DateTime(timezone=True),
        comment="Last time this service account was used"
    )
    
    total_requests = Column(
        Integer,
        default=0,
        comment="Total number of API requests made"
    )
    
    total_errors = Column(
        Integer,
        default=0,
        comment="Total number of failed requests"
    )
    
    # Monthly usage tracking
    monthly_usage = Column(
        JSONB,
        default=dict,
        comment="Monthly usage statistics"
    )
    
    # Configuration
    config = Column(
        JSONB,
        default=dict,
        comment="Service-specific configuration"
    )
    
    # Security
    public_key = Column(
        Text,
        comment="Public key for request signing (if applicable)"
    )
    
    allowed_origins = Column(
        ARRAY(String),
        default=list,
        comment="Allowed CORS origins for browser-based requests"
    )
    
    # Metadata
    tags = Column(
        ARRAY(String),
        default=list,
        comment="Tags for categorization and search"
    )
    
    metadata = Column(
        JSONB,
        default=dict,
        comment="Additional metadata"
    )
    
    # Relationships
    publisher = relationship("Publisher", back_populates="service_accounts")
    owner = relationship("User", foreign_keys=[owner_user_id])
    tokens = relationship("ServiceToken", back_populates="service_account", cascade="all, delete-orphan")
    
    # Constraints
    __table_args__ = (
        CheckConstraint(
            "service_type IN ('external', 'internal', 'partner', 'automation', 'integration')",
            name="valid_service_type"
        ),
        CheckConstraint(
            "status IN ('active', 'suspended', 'revoked', 'expired', 'pending')",
            name="valid_service_status"
        ),
        CheckConstraint(
            "rate_limit_per_minute > 0",
            name="positive_rate_limit_minute"
        ),
        CheckConstraint(
            "rate_limit_per_hour > 0",
            name="positive_rate_limit_hour"
        ),
        CheckConstraint(
            "rate_limit_per_day > 0",
            name="positive_rate_limit_day"
        ),
        CheckConstraint(
            "burst_limit > 0",
            name="positive_burst_limit"
        ),
        CheckConstraint(
            "total_requests >= 0",
            name="non_negative_requests"
        ),
        CheckConstraint(
            "total_errors >= 0",
            name="non_negative_errors"
        ),
        Index("idx_service_accounts_name", "name", unique=True),
        Index("idx_service_accounts_publisher_id", "publisher_id"),
        Index("idx_service_accounts_owner_user_id", "owner_user_id"),
        Index("idx_service_accounts_status", "status"),
        Index("idx_service_accounts_service_type", "service_type"),
        Index("idx_service_accounts_last_used_at", "last_used_at"),
    )
    
    @validates('name')
    def validate_name(self, key, value):
        """Validate service account name format."""
        if not value or len(value) < 3:
            raise ValueError("Service account name must be at least 3 characters")
        if not value.replace('-', '').replace('_', '').isalnum():
            raise ValueError("Service account name must be alphanumeric with hyphens or underscores only")
        return value.lower()
    
    @validates('owner_email')
    def validate_owner_email(self, key, value):
        """Validate owner email format."""
        if not value or '@' not in value:
            raise ValueError("Invalid owner email format")
        return value.lower()
    
    @validates('webhook_url')
    def validate_webhook_url(self, key, value):
        """Validate webhook URL format."""
        if value and not (value.startswith('http://') or value.startswith('https://')):
            raise ValueError("Webhook URL must start with http:// or https://")
        return value
    
    # Business Logic Methods
    
    def is_valid(self) -> bool:
        """Check if service account is valid for use."""
        if not self.is_active or self.status != 'active':
            return False
        if self.expires_at and self.expires_at < datetime.utcnow():
            return False
        return True
    
    def has_scope(self, scope: str) -> bool:
        """Check if service account has a specific scope."""
        if not self.scopes:
            return False
        # Check exact match
        if scope in self.scopes:
            return True
        # Check wildcard scopes (e.g., 'catalog:*' matches 'catalog:read')
        resource = scope.split(':')[0] if ':' in scope else scope
        return f"{resource}:*" in self.scopes or "*" in self.scopes
    
    def has_permission(self, resource: str, action: str) -> bool:
        """Check if service account has permission for resource:action."""
        return self.has_scope(f"{resource}:{action}")
    
    def can_access_publisher(self, publisher_id: str) -> bool:
        """Check if service account can access a specific publisher."""
        # Cross-publisher services can access any publisher
        if not self.publisher_id:
            return True
        # Otherwise, must match the assigned publisher
        return str(self.publisher_id) == str(publisher_id)
    
    def can_access_resource(self, resource_type: str, resource_id: str) -> bool:
        """Check if service account can access a specific resource."""
        if not self.allowed_resources:
            return True  # No restrictions
        
        if resource_type not in self.allowed_resources:
            return True  # No restrictions for this resource type
        
        allowed_ids = self.allowed_resources.get(resource_type, [])
        if isinstance(allowed_ids, list):
            return resource_id in allowed_ids
        return True
    
    def increment_usage(self, error: bool = False) -> None:
        """Increment usage counters."""
        self.total_requests += 1
        if error:
            self.total_errors += 1
        self.last_used_at = datetime.utcnow()
        
        # Update monthly usage
        month_key = datetime.utcnow().strftime("%Y-%m")
        if not self.monthly_usage:
            self.monthly_usage = {}
        
        if month_key not in self.monthly_usage:
            self.monthly_usage[month_key] = {"requests": 0, "errors": 0}
        
        self.monthly_usage[month_key]["requests"] += 1
        if error:
            self.monthly_usage[month_key]["errors"] += 1
    
    def suspend(self, reason: str) -> None:
        """Suspend the service account."""
        self.status = "suspended"
        self.is_active = False
        self.suspended_at = datetime.utcnow()
        self.suspended_reason = reason
    
    def reactivate(self) -> None:
        """Reactivate a suspended service account."""
        self.status = "active"
        self.is_active = True
        self.suspended_at = None
        self.suspended_reason = None
    
    def revoke(self) -> None:
        """Permanently revoke the service account."""
        self.status = "revoked"
        self.is_active = False
    
    def generate_webhook_secret(self) -> str:
        """Generate a new webhook secret."""
        secret = secrets.token_urlsafe(32)
        self.webhook_secret = hashlib.sha256(secret.encode()).hexdigest()
        return secret
    
    def to_token_claims(self) -> Dict[str, Any]:
        """Convert to JWT token claims."""
        return {
            "sub": str(self.id),
            "type": "service",
            "service_name": self.name,
            "publisher_id": str(self.publisher_id) if self.publisher_id else None,
            "scopes": self.scopes or [],
            "rate_limits": {
                "per_minute": self.rate_limit_per_minute,
                "per_hour": self.rate_limit_per_hour,
                "per_day": self.rate_limit_per_day,
                "burst": self.burst_limit
            }
        }
    
    def __repr__(self) -> str:
        return f"<ServiceAccount(id={self.id}, name='{self.name}', type='{self.service_type}', status='{self.status}')>"