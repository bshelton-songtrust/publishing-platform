"""ServiceToken model for API key management."""

import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import secrets
import hashlib

from sqlalchemy import (
    Column, String, Boolean, DateTime, CheckConstraint, 
    Index, UUID, Text, ForeignKey, func, Integer
)
from sqlalchemy.dialects.postgresql import JSONB, INET
from sqlalchemy.orm import relationship, validates

from .base import TimestampMixin
from src.core.database import Base


class ServiceToken(Base, TimestampMixin):
    """
    ServiceToken model for managing API keys for service accounts.
    
    This model handles:
    - API key generation and management
    - Token rotation and expiration
    - Usage tracking and analytics
    - Security event logging
    - Rate limiting at token level
    
    Features:
    - Secure token generation and storage (hashed)
    - Token rotation with grace periods
    - Automatic expiration
    - Usage analytics
    - Revocation management
    - Audit trail
    
    Security:
    - Tokens are hashed before storage
    - Support for token rotation
    - IP-based validation
    - Usage pattern monitoring
    """
    
    __tablename__ = "service_tokens"
    
    # Core Identity Fields
    id = Column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4,
        comment="Primary key UUID for service token"
    )
    
    # Foreign Key Relationships
    service_account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("service_accounts.id", ondelete="CASCADE"),
        nullable=False,
        comment="Service account this token belongs to"
    )
    
    # Token Identity
    name = Column(
        String(100),
        nullable=False,
        comment="Name/description of this token"
    )
    
    token_prefix = Column(
        String(10),
        nullable=False,
        comment="Token prefix for identification (e.g., 'srv_' or 'api_')"
    )
    
    token_hash = Column(
        String(255),
        nullable=False,
        unique=True,
        comment="SHA-256 hash of the actual token"
    )
    
    # Last 4 characters for identification
    token_suffix = Column(
        String(4),
        nullable=False,
        comment="Last 4 characters of token for identification"
    )
    
    # Token Configuration
    token_type = Column(
        String(20),
        nullable=False,
        default="api_key",
        comment="Type of token: api_key, bearer, oauth"
    )
    
    # Status and Lifecycle
    status = Column(
        String(20),
        nullable=False,
        default="active",
        comment="Token status: active, expired, revoked, rotating"
    )
    
    is_active = Column(
        Boolean,
        default=True,
        nullable=False,
        comment="Whether the token is currently active"
    )
    
    # Expiration Management
    expires_at = Column(
        DateTime(timezone=True),
        comment="Token expiration date (null for non-expiring)"
    )
    
    # Rotation Management
    rotated_from_id = Column(
        UUID(as_uuid=True),
        ForeignKey("service_tokens.id", ondelete="SET NULL"),
        comment="Previous token ID if this is a rotated token"
    )
    
    rotated_to_id = Column(
        UUID(as_uuid=True),
        ForeignKey("service_tokens.id", ondelete="SET NULL"),
        comment="New token ID if this token was rotated"
    )
    
    rotation_grace_period_ends = Column(
        DateTime(timezone=True),
        comment="End of grace period for rotated tokens"
    )
    
    # Scopes and Permissions (can override service account defaults)
    scopes = Column(
        JSONB,
        comment="Token-specific scopes (overrides service account if specified)"
    )
    
    # Rate Limiting (can override service account defaults)
    rate_limit_override = Column(
        JSONB,
        comment="Token-specific rate limits"
    )
    
    # Usage Tracking
    last_used_at = Column(
        DateTime(timezone=True),
        comment="Last time this token was used"
    )
    
    last_used_ip = Column(
        INET,
        comment="IP address of last usage"
    )
    
    last_used_user_agent = Column(
        Text,
        comment="User agent of last usage"
    )
    
    total_requests = Column(
        Integer,
        default=0,
        comment="Total number of requests made with this token"
    )
    
    total_errors = Column(
        Integer,
        default=0,
        comment="Total number of failed requests"
    )
    
    # Daily usage tracking
    daily_usage = Column(
        JSONB,
        default=dict,
        comment="Daily usage statistics"
    )
    
    # Security Events
    security_events = Column(
        JSONB,
        default=list,
        comment="Security events related to this token"
    )
    
    # Revocation
    revoked_at = Column(
        DateTime(timezone=True),
        comment="Timestamp when token was revoked"
    )
    
    revoked_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        comment="User who revoked the token"
    )
    
    revocation_reason = Column(
        Text,
        comment="Reason for revocation"
    )
    
    # Metadata
    metadata = Column(
        JSONB,
        default=dict,
        comment="Additional metadata"
    )
    
    # Relationships
    service_account = relationship("ServiceAccount", back_populates="tokens")
    rotated_from = relationship("ServiceToken", foreign_keys=[rotated_from_id], remote_side=[id])
    rotated_to = relationship("ServiceToken", foreign_keys=[rotated_to_id], remote_side=[id])
    revoker = relationship("User", foreign_keys=[revoked_by])
    
    # Constraints
    __table_args__ = (
        CheckConstraint(
            "token_type IN ('api_key', 'bearer', 'oauth', 'jwt')",
            name="valid_token_type"
        ),
        CheckConstraint(
            "status IN ('active', 'expired', 'revoked', 'rotating', 'suspended')",
            name="valid_token_status"
        ),
        CheckConstraint(
            "total_requests >= 0",
            name="non_negative_token_requests"
        ),
        CheckConstraint(
            "total_errors >= 0",
            name="non_negative_token_errors"
        ),
        Index("idx_service_tokens_service_account_id", "service_account_id"),
        Index("idx_service_tokens_token_hash", "token_hash", unique=True),
        Index("idx_service_tokens_token_prefix", "token_prefix"),
        Index("idx_service_tokens_status", "status"),
        Index("idx_service_tokens_expires_at", "expires_at"),
        Index("idx_service_tokens_last_used_at", "last_used_at"),
    )
    
    # Business Logic Methods
    
    @classmethod
    def generate_token(cls, prefix: str = "srv") -> tuple[str, str]:
        """
        Generate a new token and its hash.
        Returns (raw_token, token_hash).
        """
        # Generate cryptographically secure random token
        random_part = secrets.token_urlsafe(32)
        raw_token = f"{prefix}_{random_part}"
        
        # Hash the token for storage
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        
        return raw_token, token_hash
    
    @classmethod
    def hash_token(cls, token: str) -> str:
        """Hash a token for comparison."""
        return hashlib.sha256(token.encode()).hexdigest()
    
    @classmethod
    def extract_suffix(cls, token: str) -> str:
        """Extract last 4 characters of token for identification."""
        return token[-4:] if len(token) >= 4 else token
    
    def is_valid(self) -> bool:
        """Check if token is valid for use."""
        if not self.is_active or self.status not in ['active', 'rotating']:
            return False
        
        # Check expiration
        if self.expires_at and self.expires_at < datetime.utcnow():
            return False
        
        # Check rotation grace period
        if self.status == 'rotating' and self.rotation_grace_period_ends:
            if self.rotation_grace_period_ends < datetime.utcnow():
                return False
        
        return True
    
    def is_expired(self) -> bool:
        """Check if token is expired."""
        if self.expires_at and self.expires_at < datetime.utcnow():
            return True
        return False
    
    def should_rotate(self, rotation_days: int = 90) -> bool:
        """Check if token should be rotated based on age."""
        if not self.created_at:
            return False
        
        age = datetime.utcnow() - self.created_at
        return age.days >= rotation_days
    
    def record_usage(self, ip_address: str = None, user_agent: str = None, error: bool = False) -> None:
        """Record token usage."""
        self.last_used_at = datetime.utcnow()
        if ip_address:
            self.last_used_ip = ip_address
        if user_agent:
            self.last_used_user_agent = user_agent
        
        self.total_requests += 1
        if error:
            self.total_errors += 1
        
        # Update daily usage
        today = datetime.utcnow().strftime("%Y-%m-%d")
        if not self.daily_usage:
            self.daily_usage = {}
        
        if today not in self.daily_usage:
            self.daily_usage[today] = {"requests": 0, "errors": 0}
        
        self.daily_usage[today]["requests"] += 1
        if error:
            self.daily_usage[today]["errors"] += 1
    
    def add_security_event(self, event_type: str, details: Dict[str, Any]) -> None:
        """Add a security event to the token's history."""
        if not self.security_events:
            self.security_events = []
        
        event = {
            "timestamp": datetime.utcnow().isoformat(),
            "type": event_type,
            "details": details
        }
        
        self.security_events.append(event)
        
        # Keep only last 100 events
        if len(self.security_events) > 100:
            self.security_events = self.security_events[-100:]
    
    def revoke(self, user_id: str = None, reason: str = None) -> None:
        """Revoke the token."""
        self.status = "revoked"
        self.is_active = False
        self.revoked_at = datetime.utcnow()
        if user_id:
            self.revoked_by = user_id
        if reason:
            self.revocation_reason = reason
        
        self.add_security_event("revoked", {
            "user_id": str(user_id) if user_id else None,
            "reason": reason
        })
    
    def start_rotation(self, grace_period_hours: int = 24) -> None:
        """Start token rotation with grace period."""
        self.status = "rotating"
        self.rotation_grace_period_ends = datetime.utcnow() + timedelta(hours=grace_period_hours)
        
        self.add_security_event("rotation_started", {
            "grace_period_hours": grace_period_hours,
            "grace_period_ends": self.rotation_grace_period_ends.isoformat()
        })
    
    def complete_rotation(self, new_token_id: str) -> None:
        """Complete token rotation."""
        self.status = "revoked"
        self.is_active = False
        self.rotated_to_id = new_token_id
        
        self.add_security_event("rotation_completed", {
            "new_token_id": str(new_token_id)
        })
    
    def get_effective_scopes(self) -> list:
        """Get effective scopes for this token."""
        # Token-specific scopes override service account scopes
        if self.scopes:
            return self.scopes
        # Otherwise use service account scopes
        if self.service_account and self.service_account.scopes:
            return self.service_account.scopes
        return []
    
    def get_effective_rate_limits(self) -> Dict[str, int]:
        """Get effective rate limits for this token."""
        # Start with service account defaults
        limits = {}
        if self.service_account:
            limits = {
                "per_minute": self.service_account.rate_limit_per_minute,
                "per_hour": self.service_account.rate_limit_per_hour,
                "per_day": self.service_account.rate_limit_per_day,
                "burst": self.service_account.burst_limit
            }
        
        # Apply token-specific overrides
        if self.rate_limit_override:
            limits.update(self.rate_limit_override)
        
        return limits
    
    def to_response_dict(self) -> Dict[str, Any]:
        """Convert to API response (safe fields only)."""
        return {
            "id": str(self.id),
            "name": self.name,
            "prefix": self.token_prefix,
            "suffix": self.token_suffix,
            "type": self.token_type,
            "status": self.status,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "total_requests": self.total_requests,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
    
    def __repr__(self) -> str:
        return f"<ServiceToken(id={self.id}, name='{self.name}', status='{self.status}', prefix='{self.token_prefix}...{self.token_suffix}')>"