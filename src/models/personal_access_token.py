"""PersonalAccessToken model for user-generated API tokens."""

import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import secrets
import hashlib

from sqlalchemy import (
    Column, String, Boolean, DateTime, CheckConstraint, 
    Index, UUID, Text, ForeignKey, func, Integer
)
from sqlalchemy.dialects.postgresql import JSONB, ARRAY, INET
from sqlalchemy.orm import relationship, validates

from .base import TimestampMixin
from src.core.database import Base


class PersonalAccessToken(Base, TimestampMixin):
    """
    PersonalAccessToken model for user-generated API tokens.
    
    This model handles:
    - User-generated tokens for automation, CI/CD, integrations
    - Scoped permissions inherited from or limited by user permissions
    - Token lifecycle management
    - Usage tracking and security monitoring
    
    Use Cases:
    - CI/CD pipeline authentication
    - Third-party application integration
    - Automation scripts and tools
    - Developer API access
    - Mobile/desktop application authentication
    
    Security Features:
    - Inherit user permissions but can be further restricted
    - Publisher-scoped tokens
    - Expiration dates
    - IP restrictions
    - Usage monitoring and alerts
    """
    
    __tablename__ = "personal_access_tokens"
    
    # Core Identity Fields
    id = Column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4,
        comment="Primary key UUID for personal access token"
    )
    
    # Foreign Key Relationships
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="User who owns this token"
    )
    
    publisher_id = Column(
        UUID(as_uuid=True),
        ForeignKey("publishers.id", ondelete="CASCADE"),
        nullable=True,
        comment="Publisher this token is scoped to (null for multi-publisher access)"
    )
    
    # Token Identity
    name = Column(
        String(100),
        nullable=False,
        comment="User-defined name for the token (e.g., 'CI/CD Pipeline', 'Mobile App')"
    )
    
    description = Column(
        Text,
        comment="Optional description of the token's purpose"
    )
    
    token_prefix = Column(
        String(10),
        nullable=False,
        default="pat",
        comment="Token prefix (e.g., 'pat_' for Personal Access Token)"
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
    
    # Status and Lifecycle
    status = Column(
        String(20),
        nullable=False,
        default="active",
        comment="Token status: active, expired, revoked, suspended"
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
        comment="Token expiration date"
    )
    
    # Permissions and Scopes
    scopes = Column(
        ARRAY(String),
        default=list,
        comment="Array of permission scopes this token can access"
    )
    
    # Scope can be more restrictive than user permissions but not more permissive
    inherit_user_permissions = Column(
        Boolean,
        default=True,
        comment="Whether to inherit all user permissions or use only specified scopes"
    )
    
    # Access Restrictions
    allowed_ips = Column(
        ARRAY(INET),
        default=list,
        comment="List of allowed IP addresses/ranges"
    )
    
    require_ip_allowlist = Column(
        Boolean,
        default=False,
        comment="Whether to enforce IP allowlist"
    )
    
    allowed_origins = Column(
        ARRAY(String),
        default=list,
        comment="Allowed CORS origins for browser-based requests"
    )
    
    # Rate Limiting (if different from user defaults)
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
    
    last_used_location = Column(
        String(100),
        comment="Geographic location of last usage"
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
    
    # Usage analytics
    daily_usage = Column(
        JSONB,
        default=dict,
        comment="Daily usage statistics"
    )
    
    endpoint_usage = Column(
        JSONB,
        default=dict,
        comment="Per-endpoint usage statistics"
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
    
    revocation_reason = Column(
        Text,
        comment="Reason for revocation"
    )
    
    # Metadata
    tags = Column(
        ARRAY(String),
        default=list,
        comment="Tags for categorization"
    )
    
    metadata = Column(
        JSONB,
        default=dict,
        comment="Additional metadata"
    )
    
    # Relationships
    user = relationship("User", back_populates="personal_access_tokens")
    publisher = relationship("Publisher")
    
    # Constraints
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'expired', 'revoked', 'suspended')",
            name="valid_pat_status"
        ),
        CheckConstraint(
            "total_requests >= 0",
            name="non_negative_pat_requests"
        ),
        CheckConstraint(
            "total_errors >= 0",
            name="non_negative_pat_errors"
        ),
        CheckConstraint(
            "length(name) >= 1",
            name="pat_name_not_empty"
        ),
        Index("idx_personal_access_tokens_user_id", "user_id"),
        Index("idx_personal_access_tokens_publisher_id", "publisher_id"),
        Index("idx_personal_access_tokens_token_hash", "token_hash", unique=True),
        Index("idx_personal_access_tokens_status", "status"),
        Index("idx_personal_access_tokens_expires_at", "expires_at"),
        Index("idx_personal_access_tokens_last_used_at", "last_used_at"),
        # Composite index for user + publisher tokens
        Index("idx_pat_user_publisher", "user_id", "publisher_id"),
    )
    
    @validates('name')
    def validate_name(self, key, value):
        """Validate token name."""
        if not value or len(value.strip()) < 1:
            raise ValueError("Token name cannot be empty")
        return value.strip()
    
    # Business Logic Methods
    
    @classmethod
    def generate_token(cls, prefix: str = "pat") -> tuple[str, str]:
        """
        Generate a new personal access token and its hash.
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
        if not self.is_active or self.status != 'active':
            return False
        
        # Check expiration
        if self.expires_at and self.expires_at < datetime.utcnow():
            return False
        
        return True
    
    def is_expired(self) -> bool:
        """Check if token is expired."""
        if self.expires_at and self.expires_at < datetime.utcnow():
            return True
        return False
    
    def can_access_publisher(self, publisher_id: str) -> bool:
        """Check if token can access a specific publisher."""
        # Multi-publisher tokens can access any publisher the user can access
        if not self.publisher_id:
            return True
        # Otherwise, must match the assigned publisher
        return str(self.publisher_id) == str(publisher_id)
    
    def has_scope(self, scope: str) -> bool:
        """Check if token has a specific scope."""
        # If inheriting user permissions and no specific scopes set
        if self.inherit_user_permissions and not self.scopes:
            # This would require checking user permissions in the context
            # For now, return True and let the service layer handle it
            return True
        
        if not self.scopes:
            return False
        
        # Check exact match
        if scope in self.scopes:
            return True
        
        # Check wildcard scopes
        resource = scope.split(':')[0] if ':' in scope else scope
        return f"{resource}:*" in self.scopes or "*" in self.scopes
    
    def is_ip_allowed(self, ip_address: str) -> bool:
        """Check if IP address is allowed to use this token."""
        if not self.require_ip_allowlist or not self.allowed_ips:
            return True
        
        # This would require proper IP address parsing and CIDR matching
        # For now, do simple string matching
        return ip_address in [str(ip) for ip in self.allowed_ips]
    
    def record_usage(self, ip_address: str = None, user_agent: str = None, 
                    endpoint: str = None, error: bool = False) -> None:
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
        
        # Track endpoint usage
        if endpoint:
            if not self.endpoint_usage:
                self.endpoint_usage = {}
            
            if endpoint not in self.endpoint_usage:
                self.endpoint_usage[endpoint] = {"requests": 0, "errors": 0}
            
            self.endpoint_usage[endpoint]["requests"] += 1
            if error:
                self.endpoint_usage[endpoint]["errors"] += 1
    
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
    
    def revoke(self, reason: str = None) -> None:
        """Revoke the token."""
        self.status = "revoked"
        self.is_active = False
        self.revoked_at = datetime.utcnow()
        if reason:
            self.revocation_reason = reason
        
        self.add_security_event("revoked", {
            "reason": reason,
            "revoked_by": "user"  # Could be enhanced to track who revoked it
        })
    
    def suspend(self, reason: str = None) -> None:
        """Suspend the token temporarily."""
        self.status = "suspended"
        self.is_active = False
        
        self.add_security_event("suspended", {
            "reason": reason
        })
    
    def reactivate(self) -> None:
        """Reactivate a suspended token."""
        if self.status == "suspended":
            self.status = "active"
            self.is_active = True
            
            self.add_security_event("reactivated", {})
    
    def get_effective_scopes(self) -> List[str]:
        """Get effective scopes for this token."""
        if self.inherit_user_permissions and not self.scopes:
            # In practice, this would fetch user permissions from the service layer
            return []  # Placeholder
        return self.scopes or []
    
    def get_usage_summary(self) -> Dict[str, Any]:
        """Get usage summary for analytics."""
        return {
            "total_requests": self.total_requests,
            "total_errors": self.total_errors,
            "error_rate": (self.total_errors / self.total_requests * 100) if self.total_requests > 0 else 0,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "days_since_last_use": (datetime.utcnow() - self.last_used_at).days if self.last_used_at else None,
            "daily_usage_count": len(self.daily_usage) if self.daily_usage else 0,
            "most_used_endpoints": self._get_top_endpoints(5) if self.endpoint_usage else []
        }
    
    def _get_top_endpoints(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Get top used endpoints."""
        if not self.endpoint_usage:
            return []
        
        # Sort by request count
        sorted_endpoints = sorted(
            self.endpoint_usage.items(),
            key=lambda x: x[1]["requests"],
            reverse=True
        )
        
        return [
            {
                "endpoint": endpoint,
                "requests": data["requests"],
                "errors": data["errors"]
            }
            for endpoint, data in sorted_endpoints[:limit]
        ]
    
    def to_token_claims(self) -> Dict[str, Any]:
        """Convert to JWT token claims."""
        return {
            "sub": str(self.user_id),
            "type": "pat",
            "token_id": str(self.id),
            "name": self.name,
            "publisher_id": str(self.publisher_id) if self.publisher_id else None,
            "scopes": self.get_effective_scopes(),
            "inherit_user_permissions": self.inherit_user_permissions
        }
    
    def to_response_dict(self) -> Dict[str, Any]:
        """Convert to API response (safe fields only)."""
        return {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "prefix": self.token_prefix,
            "suffix": self.token_suffix,
            "status": self.status,
            "publisher_id": str(self.publisher_id) if self.publisher_id else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "total_requests": self.total_requests,
            "scopes": self.scopes,
            "inherit_user_permissions": self.inherit_user_permissions,
            "tags": self.tags,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
    
    def __repr__(self) -> str:
        return f"<PersonalAccessToken(id={self.id}, user_id={self.user_id}, name='{self.name}', status='{self.status}')>"