"""User model for multi-tenant publishing platform authentication and identity management."""

import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from sqlalchemy import (
    Column, String, Boolean, Integer, DateTime, CheckConstraint, 
    Index, UUID, Text, func, Computed
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from .base import TimestampMixin
from src.core.database import Base


class User(Base, TimestampMixin):
    """
    User model representing individual users in the multi-tenant publishing platform.
    
    This model handles user identity, authentication, profile information, and security
    features for all users across all publishers/tenants. Users can be associated with
    multiple publishers through the UserPublisher relationship model.
    
    Key Features:
    - Multi-tenant aware through publisher relationships
    - Secure password hashing with bcrypt
    - External authentication support (OAuth, SSO)
    - Multi-factor authentication support
    - Account security features (lockout, password policies)
    - Profile and preference management
    - Session management integration
    - Email verification workflow
    - Comprehensive audit trail
    """
    
    __tablename__ = "users"
    
    # Core Identity Fields
    id = Column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4,
        comment="Primary key UUID for user identity"
    )
    
    email = Column(
        String(255), 
        nullable=False, 
        unique=True,
        comment="Primary email address, must be unique across platform"
    )
    
    username = Column(
        String(100),
        nullable=True,
        unique=True,
        comment="Optional unique username for user identification"
    )
    
    first_name = Column(
        String(100),
        nullable=False,
        comment="User's first name"
    )
    
    last_name = Column(
        String(100),
        nullable=False,
        comment="User's last name"
    )
    
    full_name = Column(
        String(255),
        Computed("first_name || ' ' || last_name"),
        comment="Computed full name from first and last name"
    )
    
    # Authentication Fields
    password_hash = Column(
        String(255),
        nullable=True,
        comment="Bcrypt hashed password (nullable for external auth users)"
    )
    
    is_external_auth = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="True if user authenticates via external provider (OAuth, SSO)"
    )
    
    external_auth_provider = Column(
        String(50),
        nullable=True,
        comment="External authentication provider name (google, microsoft, etc.)"
    )
    
    external_auth_id = Column(
        String(255),
        nullable=True,
        comment="User ID from external authentication provider"
    )
    
    # Profile Fields
    avatar_url = Column(
        String(500),
        nullable=True,
        comment="URL to user's profile avatar/photo"
    )
    
    phone_number = Column(
        String(50),
        nullable=True,
        comment="User's phone number in international format"
    )
    
    timezone = Column(
        String(100),
        nullable=False,
        default="UTC",
        comment="User's preferred timezone (IANA timezone identifier)"
    )
    
    language = Column(
        String(10),
        nullable=False,
        default="en",
        comment="User's preferred language code (ISO 639-1 format)"
    )
    
    # Status Fields
    status = Column(
        String(20),
        nullable=False,
        default="active",
        comment="User account status: active, suspended, deactivated, pending_verification"
    )
    
    is_verified = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="True if user has completed account verification process"
    )
    
    email_verified_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when email was verified"
    )
    
    last_login_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp of user's last successful login"
    )
    
    # Security Fields
    failed_login_attempts = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Count of consecutive failed login attempts"
    )
    
    locked_until = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Account lockout expiration timestamp"
    )
    
    password_changed_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when password was last changed"
    )
    
    mfa_enabled = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="True if multi-factor authentication is enabled"
    )
    
    mfa_secret = Column(
        String(255),
        nullable=True,
        comment="Encrypted MFA secret key for TOTP generation"
    )
    
    # Metadata Fields
    preferences = Column(
        JSONB,
        default=dict,
        comment="User preferences and settings in JSON format"
    )
    
    metadata = Column(
        JSONB,
        default=dict,
        comment="Additional user metadata and flexible attributes"
    )

    # Table-level constraints and indexes
    __table_args__ = (
        # Check constraints for enum-like fields
        CheckConstraint(
            "status IN ('active', 'suspended', 'deactivated', 'pending_verification')",
            name="valid_user_status"
        ),
        CheckConstraint(
            "external_auth_provider IS NULL OR external_auth_provider IN ('google', 'microsoft', 'okta', 'auth0', 'facebook', 'github')",
            name="valid_external_auth_provider"
        ),
        
        # Business rules constraints
        CheckConstraint(
            "length(first_name) >= 1",
            name="first_name_not_empty"
        ),
        CheckConstraint(
            "length(last_name) >= 1",
            name="last_name_not_empty"
        ),
        CheckConstraint(
            "email ~ '^[^@]+@[^@]+\\.[^@]+$'",
            name="valid_email_format"
        ),
        CheckConstraint(
            "username IS NULL OR (length(username) >= 3 AND username ~ '^[a-zA-Z0-9_-]+$')",
            name="valid_username_format"
        ),
        CheckConstraint(
            "phone_number IS NULL OR phone_number ~ '^\\+[1-9]\\d{1,14}$'",
            name="valid_phone_number_format"
        ),
        CheckConstraint(
            "language ~ '^[a-z]{2}(-[A-Z]{2})?$'",
            name="valid_language_code"
        ),
        CheckConstraint(
            "failed_login_attempts >= 0",
            name="non_negative_failed_attempts"
        ),
        
        # External auth constraints
        CheckConstraint(
            "(is_external_auth = false AND password_hash IS NOT NULL) OR (is_external_auth = true AND external_auth_provider IS NOT NULL AND external_auth_id IS NOT NULL)",
            name="valid_auth_configuration"
        ),
        CheckConstraint(
            "NOT is_external_auth OR (external_auth_provider IS NOT NULL AND external_auth_id IS NOT NULL)",
            name="external_auth_requires_provider_and_id"
        ),
        
        # Security constraints
        CheckConstraint(
            "NOT mfa_enabled OR mfa_secret IS NOT NULL",
            name="mfa_enabled_requires_secret"
        ),
        CheckConstraint(
            "locked_until IS NULL OR locked_until > created_at",
            name="valid_lockout_time"
        ),
        
        # Unique constraints
        CheckConstraint(
            "(external_auth_provider IS NULL AND external_auth_id IS NULL) OR (external_auth_provider IS NOT NULL AND external_auth_id IS NOT NULL)",
            name="external_auth_consistency"
        ),
        
        # Performance indexes
        Index("idx_users_email", "email"),
        Index("idx_users_username", "username"),
        Index("idx_users_status", "status"),
        Index("idx_users_external_auth", "external_auth_provider", "external_auth_id"),
        Index("idx_users_full_name", "full_name"),
        Index("idx_users_last_login", "last_login_at"),
        Index("idx_users_created_at", "created_at"),
        Index("idx_users_email_verified", "email_verified_at"),
        Index("idx_users_locked_until", "locked_until"),
        
        # Composite indexes for common query patterns
        Index("idx_users_status_verified", "status", "is_verified"),
        Index("idx_users_status_last_login", "status", "last_login_at"),
        Index("idx_users_auth_type_status", "is_external_auth", "status"),
    )

    # Relationships
    publisher_relationships = relationship("UserPublisher", back_populates="user", lazy="dynamic")
    sessions = relationship("UserSession", back_populates="user", lazy="dynamic")
    personal_access_tokens = relationship("PersonalAccessToken", back_populates="user", lazy="dynamic")

    def __init__(self, **kwargs):
        """
        Initialize User with default preferences and metadata.
        
        Sets up default user preferences, metadata structure,
        and initializes security settings for new user instances.
        """
        super().__init__(**kwargs)
        
        # Initialize default preferences if not provided
        if not self.preferences:
            self.preferences = {
                "notifications": {
                    "email_enabled": True,
                    "push_enabled": True,
                    "digest_frequency": "daily",
                    "marketing_emails": False
                },
                "ui": {
                    "theme": "light",
                    "sidebar_collapsed": False,
                    "items_per_page": 25,
                    "default_view": "list"
                },
                "privacy": {
                    "profile_visibility": "publishers",
                    "show_email": False,
                    "show_phone": False
                },
                "security": {
                    "require_password_change": False,
                    "session_timeout_minutes": 480,
                    "remember_me_enabled": True
                }
            }
        
        # Initialize default metadata if not provided
        if not self.metadata:
            self.metadata = {
                "registration_source": "direct",
                "onboarding_completed": False,
                "profile_completion_score": 0,
                "last_profile_update": None,
                "feature_flags": {}
            }

    @property
    def is_active(self) -> bool:
        """Check if user account is in active status."""
        return self.status == "active"
    
    @property
    def is_suspended(self) -> bool:
        """Check if user account is suspended."""
        return self.status == "suspended"
    
    @property
    def is_deactivated(self) -> bool:
        """Check if user account is deactivated."""
        return self.status == "deactivated"
    
    @property
    def is_pending_verification(self) -> bool:
        """Check if user account is pending email verification."""
        return self.status == "pending_verification"
    
    @property
    def is_locked(self) -> bool:
        """Check if user account is currently locked due to failed attempts."""
        if not self.locked_until:
            return False
        return datetime.utcnow() < self.locked_until
    
    @property
    def display_name(self) -> str:
        """Get display name for UI purposes."""
        return self.full_name or self.email
    
    @property
    def initials(self) -> str:
        """Get user initials from first and last name."""
        if self.first_name and self.last_name:
            return f"{self.first_name[0].upper()}{self.last_name[0].upper()}"
        elif self.first_name:
            return self.first_name[0].upper()
        return self.email[0].upper()

    def set_password(self, password: str) -> None:
        """
        Set user password with secure hashing using passlib.
        
        Args:
            password: Plain text password to hash and store
        """
        if self.is_external_auth:
            raise ValueError("Cannot set password for external auth users")
        
        try:
            from passlib.context import CryptContext
            pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
            self.password_hash = pwd_context.hash(password)
        except ImportError:
            # Fallback to hashlib for development (NOT SECURE for production)
            import hashlib
            import secrets
            salt = secrets.token_hex(16)
            hash_obj = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
            self.password_hash = f"pbkdf2_sha256${salt}${hash_obj.hex()}"
        
        self.password_changed_at = datetime.utcnow()
        
        # Reset failed login attempts when password is changed
        self.failed_login_attempts = 0
        self.locked_until = None

    def verify_password(self, password: str) -> bool:
        """
        Verify password against stored hash.
        
        Args:
            password: Plain text password to verify
            
        Returns:
            bool: True if password matches, False otherwise
        """
        if self.is_external_auth or not self.password_hash:
            return False
        
        try:
            from passlib.context import CryptContext
            pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
            return pwd_context.verify(password, self.password_hash)
        except ImportError:
            # Fallback verification for pbkdf2 hashes
            import hashlib
            if self.password_hash.startswith("pbkdf2_sha256$"):
                parts = self.password_hash.split("$")
                if len(parts) == 3:
                    salt = parts[1]
                    stored_hash = parts[2]
                    hash_obj = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
                    return hash_obj.hex() == stored_hash
            return False

    def record_login_attempt(self, success: bool, ip_address: Optional[str] = None) -> None:
        """
        Record login attempt and handle account locking logic.
        
        Args:
            success: Whether the login attempt was successful
            ip_address: IP address of the login attempt (for audit)
        """
        if success:
            self.failed_login_attempts = 0
            self.locked_until = None
            self.last_login_at = datetime.utcnow()
        else:
            self.failed_login_attempts += 1
            
            # Lock account after 5 failed attempts
            if self.failed_login_attempts >= 5:
                # Lock for 30 minutes
                self.locked_until = datetime.utcnow() + timedelta(minutes=30)

    def unlock_account(self) -> None:
        """Manually unlock user account and reset failed attempts."""
        self.failed_login_attempts = 0
        self.locked_until = None

    def verify_email(self) -> None:
        """Mark user email as verified and activate account if pending."""
        self.email_verified_at = datetime.utcnow()
        self.is_verified = True
        
        if self.status == "pending_verification":
            self.status = "active"

    def enable_mfa(self, secret: str) -> None:
        """
        Enable multi-factor authentication with provided secret.
        
        Args:
            secret: Base32 encoded TOTP secret
        """
        self.mfa_enabled = True
        self.mfa_secret = secret

    def disable_mfa(self) -> None:
        """Disable multi-factor authentication."""
        self.mfa_enabled = False
        self.mfa_secret = None

    def get_preference(self, key: str, default=None):
        """
        Get a specific preference value with fallback.
        
        Args:
            key: Preference key (supports dot notation for nested keys)
            default: Default value if key not found
            
        Returns:
            Preference value or default
        """
        if not self.preferences:
            return default
            
        # Support dot notation for nested keys (e.g., "notifications.email_enabled")
        keys = key.split('.')
        value = self.preferences
        
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default

    def update_preference(self, key: str, value) -> None:
        """
        Update a specific preference value.
        
        Args:
            key: Preference key (supports dot notation for nested keys)
            value: New value to set
        """
        if not self.preferences:
            self.preferences = {}
            
        # Support dot notation for nested keys
        keys = key.split('.')
        current = self.preferences
        
        # Navigate to parent of final key
        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]
        
        # Set final value
        current[keys[-1]] = value

    def get_metadata(self, key: str, default=None):
        """
        Get a specific metadata value with fallback.
        
        Args:
            key: Metadata key (supports dot notation for nested keys)
            default: Default value if key not found
            
        Returns:
            Metadata value or default
        """
        if not self.metadata:
            return default
            
        # Support dot notation for nested keys
        keys = key.split('.')
        value = self.metadata
        
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default

    def update_metadata(self, key: str, value) -> None:
        """
        Update a specific metadata value.
        
        Args:
            key: Metadata key (supports dot notation for nested keys)
            value: New value to set
        """
        if not self.metadata:
            self.metadata = {}
            
        # Support dot notation for nested keys
        keys = key.split('.')
        current = self.metadata
        
        # Navigate to parent of final key
        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]
        
        # Set final value
        current[keys[-1]] = value

    def calculate_profile_completion(self) -> int:
        """
        Calculate profile completion percentage.
        
        Returns:
            int: Profile completion percentage (0-100)
        """
        total_fields = 10
        completed_fields = 0
        
        # Check required profile fields
        if self.first_name and len(self.first_name.strip()) > 0:
            completed_fields += 1
        if self.last_name and len(self.last_name.strip()) > 0:
            completed_fields += 1
        if self.email and self.is_verified:
            completed_fields += 1
        if self.avatar_url:
            completed_fields += 1
        if self.phone_number:
            completed_fields += 1
        if self.timezone and self.timezone != "UTC":
            completed_fields += 1
        if self.language and self.language != "en":
            completed_fields += 1
        
        # Check preferences completion
        if self.get_preference("notifications.email_enabled") is not None:
            completed_fields += 1
        if self.get_preference("ui.theme") and self.get_preference("ui.theme") != "light":
            completed_fields += 1
        if self.mfa_enabled:
            completed_fields += 1
        
        completion_percentage = int((completed_fields / total_fields) * 100)
        
        # Update metadata with calculated score
        self.update_metadata("profile_completion_score", completion_percentage)
        
        return completion_percentage

    def can_login(self) -> tuple[bool, Optional[str]]:
        """
        Check if user can login and return reason if not.
        
        Returns:
            tuple: (can_login: bool, reason: Optional[str])
        """
        if not self.is_active:
            return False, f"Account is {self.status}"
        
        if self.is_locked:
            return False, "Account is temporarily locked due to failed login attempts"
        
        if not self.is_verified and self.status == "pending_verification":
            return False, "Account email verification is required"
        
        return True, None

    def has_publisher_access(self, publisher_id: uuid.UUID) -> bool:
        """
        Check if user has access to a specific publisher.
        
        Note: This method requires UserPublisher relationship to be loaded
        or should be implemented at the service level with proper queries.
        
        Args:
            publisher_id: UUID of the publisher to check access for
            
        Returns:
            bool: True if user has access to the publisher
        """
        # This would typically be implemented at the service level
        # with a proper query to the UserPublisher table
        # Placeholder implementation for interface definition
        return True

    def __repr__(self) -> str:
        """String representation of the User."""
        return (f"<User(id={self.id}, email='{self.email}', "
                f"name='{self.full_name}', status='{self.status}', "
                f"is_external_auth={self.is_external_auth})>")

    def __str__(self) -> str:
        """Human-readable string representation."""
        return f"{self.display_name} ({self.email})"