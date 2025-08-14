"""UserSession model for managing user authentication sessions."""

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
from sqlalchemy.orm import relationship

from .base import TimestampMixin
from src.core.database import Base


class UserSession(Base, TimestampMixin):
    """
    UserSession model for managing user authentication sessions and security.
    
    This model handles:
    - Session creation and validation
    - Token management (access, refresh, remember-me)
    - Security tracking (IP, user agent, device fingerprinting)
    - Session expiration and cleanup
    - Multi-device session management
    - Security event logging
    - Publisher context for multi-tenant sessions
    
    Features:
    - Secure token generation and validation
    - IP address and user agent tracking
    - Device fingerprinting for security
    - Automatic session expiration
    - Remember-me functionality
    - Publisher-specific session context
    - Activity tracking and analytics
    - Concurrent session limits
    
    Security Features:
    - Token rotation on access
    - Suspicious activity detection
    - Geographic location tracking
    - Device change notifications
    - Session hijacking protection
    """
    
    __tablename__ = "user_sessions"
    
    # Core Identity Fields
    id = Column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4,
        comment="Primary key UUID for session"
    )
    
    # Foreign Key Relationships
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="Reference to user who owns this session"
    )
    
    publisher_id = Column(
        UUID(as_uuid=True),
        ForeignKey("publishers.id", ondelete="CASCADE"),
        nullable=True,
        comment="Current publisher context for this session (nullable for multi-publisher access)"
    )
    
    # Token Management
    access_token_hash = Column(
        String(255),
        nullable=False,
        unique=True,
        comment="SHA-256 hash of access token for validation"
    )
    
    refresh_token_hash = Column(
        String(255),
        nullable=True,
        comment="SHA-256 hash of refresh token for session renewal"
    )
    
    remember_token_hash = Column(
        String(255),
        nullable=True,
        comment="SHA-256 hash of remember-me token for extended sessions"
    )
    
    # Session Metadata
    session_type = Column(
        String(20),
        nullable=False,
        default="web",
        comment="Type of session: web, mobile, api, service"
    )
    
    device_id = Column(
        String(255),
        nullable=True,
        comment="Unique device identifier for session tracking"
    )
    
    device_name = Column(
        String(255),
        nullable=True,
        comment="Human-readable device name (e.g., 'iPhone 13', 'Chrome on MacBook')"
    )
    
    # Network and Security Information
    ip_address = Column(
        INET,
        nullable=True,
        comment="IP address from which session was created"
    )
    
    user_agent = Column(
        Text,
        nullable=True,
        comment="User agent string from client"
    )
    
    browser_fingerprint = Column(
        String(255),
        nullable=True,
        comment="Browser fingerprint hash for additional security"
    )
    
    # Geographic Information
    country_code = Column(
        String(2),
        nullable=True,
        comment="ISO country code derived from IP address"
    )
    
    city = Column(
        String(100),
        nullable=True,
        comment="City derived from IP address"
    )
    
    timezone_detected = Column(
        String(100),
        nullable=True,
        comment="Timezone detected from client"
    )
    
    # Session Timing
    expires_at = Column(
        DateTime(timezone=True),
        nullable=False,
        comment="Session expiration timestamp"
    )
    
    last_activity_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        comment="Timestamp of last session activity"
    )
    
    remember_expires_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Remember-me token expiration (longer than regular session)"
    )
    
    # Status and Control
    status = Column(
        String(20),
        nullable=False,
        default="active",
        comment="Session status: active, expired, revoked, suspicious"
    )
    
    is_remember_me = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="True if this is a remember-me session with extended duration"
    )
    
    is_mobile = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="True if session is from mobile device"
    )
    
    # Activity Tracking
    login_method = Column(
        String(50),
        nullable=False,
        default="password",
        comment="Method used to create session: password, oauth, sso, mfa, api_key"
    )
    
    activity_count = Column(
        Integer,
        nullable=False,
        default=1,
        comment="Number of activities/requests in this session"
    )
    
    # Security Events
    security_events = Column(
        JSONB,
        default=list,
        comment="List of security events for this session"
    )
    
    # Additional Metadata
    metadata = Column(
        JSONB,
        default=dict,
        comment="Additional session metadata and client information"
    )

    # Table-level constraints and indexes
    __table_args__ = (
        # Check constraints for enum-like fields
        CheckConstraint(
            "session_type IN ('web', 'mobile', 'api', 'service', 'cli')",
            name="valid_session_type"
        ),
        CheckConstraint(
            "status IN ('active', 'expired', 'revoked', 'suspicious')",
            name="valid_session_status"
        ),
        CheckConstraint(
            "login_method IN ('password', 'oauth', 'sso', 'mfa', 'api_key', 'refresh_token')",
            name="valid_login_method"
        ),
        
        # Business rules constraints
        CheckConstraint(
            "activity_count > 0",
            name="positive_activity_count"
        ),
        CheckConstraint(
            "expires_at > created_at",
            name="expires_after_created"
        ),
        CheckConstraint(
            "last_activity_at >= created_at",
            name="last_activity_after_created"
        ),
        CheckConstraint(
            "remember_expires_at IS NULL OR remember_expires_at > expires_at",
            name="remember_expires_after_regular"
        ),
        CheckConstraint(
            "(is_remember_me = false) OR (is_remember_me = true AND remember_token_hash IS NOT NULL AND remember_expires_at IS NOT NULL)",
            name="remember_me_requires_token_and_expiry"
        ),
        CheckConstraint(
            "country_code IS NULL OR length(country_code) = 2",
            name="valid_country_code_length"
        ),
        
        # Performance indexes
        Index("idx_user_sessions_user_id", "user_id"),
        Index("idx_user_sessions_publisher_id", "publisher_id"),
        Index("idx_user_sessions_access_token", "access_token_hash"),
        Index("idx_user_sessions_refresh_token", "refresh_token_hash"),
        Index("idx_user_sessions_remember_token", "remember_token_hash"),
        Index("idx_user_sessions_status", "status"),
        Index("idx_user_sessions_session_type", "session_type"),
        Index("idx_user_sessions_device_id", "device_id"),
        Index("idx_user_sessions_ip_address", "ip_address"),
        Index("idx_user_sessions_expires_at", "expires_at"),
        Index("idx_user_sessions_last_activity", "last_activity_at"),
        Index("idx_user_sessions_created_at", "created_at"),
        Index("idx_user_sessions_country", "country_code"),
        
        # Composite indexes for common query patterns
        Index("idx_user_sessions_user_status", "user_id", "status"),
        Index("idx_user_sessions_user_active", "user_id", "status", "expires_at"),
        Index("idx_user_sessions_user_publisher", "user_id", "publisher_id"),
        Index("idx_user_sessions_device_user", "device_id", "user_id"),
        Index("idx_user_sessions_cleanup", "status", "expires_at"),
        Index("idx_user_sessions_security", "ip_address", "user_agent"),
    )

    # Relationships
    user = relationship("User", back_populates="sessions")
    publisher = relationship("Publisher")

    def __init__(self, **kwargs):
        """
        Initialize UserSession with security defaults and metadata.
        
        Sets up default security events list, metadata structure,
        and session timing for new session instances.
        """
        super().__init__(**kwargs)
        
        # Initialize default security events if not provided
        if not self.security_events:
            self.security_events = []
        
        # Initialize default metadata if not provided
        if not self.metadata:
            self.metadata = {
                "client_info": {},
                "browser_info": {},
                "screen_resolution": None,
                "platform": None,
                "referrer": None,
                "initial_page": None
            }
        
        # Set default expiration if not provided (8 hours for regular sessions)
        if not self.expires_at:
            self.expires_at = datetime.utcnow() + timedelta(hours=8)

    @property
    def is_active(self) -> bool:
        """Check if session is active and not expired."""
        return self.status == "active" and not self.is_expired
    
    @property
    def is_expired(self) -> bool:
        """Check if session has expired."""
        return datetime.utcnow() > self.expires_at
    
    @property
    def is_revoked(self) -> bool:
        """Check if session was revoked."""
        return self.status == "revoked"
    
    @property
    def is_suspicious(self) -> bool:
        """Check if session is marked as suspicious."""
        return self.status == "suspicious"
    
    @property
    def time_since_last_activity(self) -> timedelta:
        """Get time elapsed since last activity."""
        return datetime.utcnow() - self.last_activity_at
    
    @property
    def minutes_until_expiry(self) -> int:
        """Get minutes until session expires."""
        if self.is_expired:
            return 0
        delta = self.expires_at - datetime.utcnow()
        return max(0, int(delta.total_seconds() / 60))
    
    @property
    def session_duration(self) -> timedelta:
        """Get total session duration so far."""
        return self.last_activity_at - self.created_at
    
    @property
    def is_long_running(self) -> bool:
        """Check if session has been active for more than 24 hours."""
        return self.session_duration.total_seconds() > 86400  # 24 hours

    @classmethod
    def generate_token(cls) -> str:
        """
        Generate a cryptographically secure token.
        
        Returns:
            str: Secure random token
        """
        return secrets.token_urlsafe(32)
    
    @classmethod
    def hash_token(cls, token: str) -> str:
        """
        Hash a token for secure storage.
        
        Args:
            token: Plain text token to hash
            
        Returns:
            str: SHA-256 hash of token
        """
        return hashlib.sha256(token.encode()).hexdigest()

    def create_access_token(self) -> str:
        """
        Create and store new access token.
        
        Returns:
            str: Plain text access token (store hash)
        """
        token = self.generate_token()
        self.access_token_hash = self.hash_token(token)
        return token

    def create_refresh_token(self) -> Optional[str]:
        """
        Create and store new refresh token.
        
        Returns:
            Optional[str]: Plain text refresh token if refresh is enabled
        """
        token = self.generate_token()
        self.refresh_token_hash = self.hash_token(token)
        return token

    def create_remember_token(self, duration_days: int = 30) -> str:
        """
        Create remember-me token with extended expiration.
        
        Args:
            duration_days: Number of days for remember-me token validity
            
        Returns:
            str: Plain text remember-me token
        """
        token = self.generate_token()
        self.remember_token_hash = self.hash_token(token)
        self.remember_expires_at = datetime.utcnow() + timedelta(days=duration_days)
        self.is_remember_me = True
        return token

    def verify_access_token(self, token: str) -> bool:
        """
        Verify access token against stored hash.
        
        Args:
            token: Plain text token to verify
            
        Returns:
            bool: True if token is valid
        """
        if not self.access_token_hash or not token:
            return False
        return self.hash_token(token) == self.access_token_hash

    def verify_refresh_token(self, token: str) -> bool:
        """
        Verify refresh token against stored hash.
        
        Args:
            token: Plain text token to verify
            
        Returns:
            bool: True if token is valid
        """
        if not self.refresh_token_hash or not token:
            return False
        return self.hash_token(token) == self.refresh_token_hash

    def verify_remember_token(self, token: str) -> bool:
        """
        Verify remember-me token against stored hash.
        
        Args:
            token: Plain text token to verify
            
        Returns:
            bool: True if token is valid and not expired
        """
        if not self.remember_token_hash or not token or not self.remember_expires_at:
            return False
        
        if datetime.utcnow() > self.remember_expires_at:
            return False
        
        return self.hash_token(token) == self.remember_token_hash

    def update_activity(self, publisher_id: Optional[uuid.UUID] = None) -> None:
        """
        Update session activity timestamp and context.
        
        Args:
            publisher_id: Current publisher context (optional)
        """
        self.last_activity_at = datetime.utcnow()
        self.activity_count += 1
        
        if publisher_id:
            self.publisher_id = publisher_id

    def extend_session(self, minutes: int = 480) -> None:
        """
        Extend session expiration time.
        
        Args:
            minutes: Number of minutes to extend session
        """
        new_expiry = datetime.utcnow() + timedelta(minutes=minutes)
        
        # Don't reduce session time if current expiry is later
        if new_expiry > self.expires_at:
            self.expires_at = new_expiry

    def revoke(self, reason: str = "user_logout") -> None:
        """
        Revoke session immediately.
        
        Args:
            reason: Reason for revocation
        """
        self.status = "revoked"
        self.add_security_event("session_revoked", {
            "reason": reason,
            "revoked_at": datetime.utcnow().isoformat()
        })

    def mark_suspicious(self, reason: str, details: Optional[Dict] = None) -> None:
        """
        Mark session as suspicious.
        
        Args:
            reason: Reason for marking suspicious
            details: Additional details about the suspicion
        """
        self.status = "suspicious"
        self.add_security_event("session_marked_suspicious", {
            "reason": reason,
            "details": details or {},
            "marked_at": datetime.utcnow().isoformat()
        })

    def add_security_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """
        Add security event to session history.
        
        Args:
            event_type: Type of security event
            data: Event data and details
        """
        if not self.security_events:
            self.security_events = []
        
        event = {
            "type": event_type,
            "timestamp": datetime.utcnow().isoformat(),
            "data": data
        }
        
        self.security_events.append(event)
        
        # Keep only last 50 events to prevent unbounded growth
        if len(self.security_events) > 50:
            self.security_events = self.security_events[-50:]

    def detect_suspicious_activity(self, current_ip: str, current_user_agent: str) -> bool:
        """
        Detect potentially suspicious activity based on session changes.
        
        Args:
            current_ip: Current request IP address
            current_user_agent: Current request user agent
            
        Returns:
            bool: True if suspicious activity detected
        """
        suspicious = False
        
        # Check for IP address change
        if self.ip_address and str(self.ip_address) != current_ip:
            self.add_security_event("ip_address_changed", {
                "old_ip": str(self.ip_address),
                "new_ip": current_ip
            })
            suspicious = True
        
        # Check for user agent change
        if self.user_agent and self.user_agent != current_user_agent:
            self.add_security_event("user_agent_changed", {
                "old_user_agent": self.user_agent,
                "new_user_agent": current_user_agent
            })
            suspicious = True
        
        # Check for unusual activity patterns
        if self.activity_count > 1000:  # Very high activity count
            self.add_security_event("high_activity_count", {
                "activity_count": self.activity_count
            })
            suspicious = True
        
        return suspicious

    def get_client_info(self) -> Dict[str, Any]:
        """
        Get comprehensive client information.
        
        Returns:
            dict: Client information including device, location, etc.
        """
        return {
            "device_id": self.device_id,
            "device_name": self.device_name,
            "ip_address": str(self.ip_address) if self.ip_address else None,
            "user_agent": self.user_agent,
            "browser_fingerprint": self.browser_fingerprint,
            "country_code": self.country_code,
            "city": self.city,
            "timezone_detected": self.timezone_detected,
            "is_mobile": self.is_mobile,
            "session_type": self.session_type,
            "metadata": self.metadata
        }

    def cleanup_expired_tokens(self) -> None:
        """Remove expired tokens from session."""
        now = datetime.utcnow()
        
        # Clear remember token if expired
        if self.remember_expires_at and now > self.remember_expires_at:
            self.remember_token_hash = None
            self.remember_expires_at = None
            self.is_remember_me = False

    @classmethod
    def cleanup_expired_sessions(cls, session_db) -> int:
        """
        Clean up expired sessions from database.
        
        Args:
            session_db: Database session
            
        Returns:
            int: Number of sessions cleaned up
        """
        from sqlalchemy import and_
        
        # Mark expired sessions
        expired_count = session_db.query(cls).filter(
            and_(
                cls.status == "active",
                cls.expires_at < datetime.utcnow()
            )
        ).update(
            {"status": "expired"},
            synchronize_session=False
        )
        
        # Delete old expired sessions (older than 30 days)
        old_cutoff = datetime.utcnow() - timedelta(days=30)
        deleted_count = session_db.query(cls).filter(
            and_(
                cls.status == "expired",
                cls.expires_at < old_cutoff
            )
        ).delete(synchronize_session=False)
        
        session_db.commit()
        return expired_count + deleted_count

    def __repr__(self) -> str:
        """String representation of the UserSession."""
        return (f"<UserSession(id={self.id}, user_id={self.user_id}, "
                f"session_type='{self.session_type}', status='{self.status}', "
                f"expires_at='{self.expires_at}', ip='{self.ip_address}')>")

    def __str__(self) -> str:
        """Human-readable string representation."""
        device = self.device_name or f"{self.session_type} session"
        return f"Session: {device} ({self.status})"