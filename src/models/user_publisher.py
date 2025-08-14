"""UserPublisher model for managing user-publisher relationships and permissions."""

import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy import (
    Column, String, Boolean, DateTime, CheckConstraint, 
    Index, UUID, Text, ForeignKey, func, Integer, UniqueConstraint
)
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from .base import TimestampMixin
from src.core.database import Base


class UserPublisher(Base, TimestampMixin):
    """
    UserPublisher model managing the many-to-many relationship between users and publishers.
    
    This model handles:
    - User-publisher association and role assignment
    - Permission management per publisher
    - Invitation and onboarding workflow
    - Access control and restrictions
    - Publisher-specific user settings
    - Audit trail for user access changes
    
    The model supports various roles and permission levels:
    - Owner: Full administrative access to publisher
    - Admin: Administrative access with some restrictions
    - Manager: Content and user management capabilities
    - Editor: Content creation and editing permissions
    - Viewer: Read-only access to publisher content
    - External: Limited access for external collaborators
    
    Business Rules:
    - Each user can have different roles across different publishers
    - Only owners and admins can invite new users
    - Users can be temporarily suspended from a publisher
    - Invitation workflow tracks the complete user onboarding process
    """
    
    __tablename__ = "user_publishers"
    
    # Core Identity Fields
    id = Column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4,
        comment="Primary key UUID for user-publisher relationship"
    )
    
    # Foreign Key Relationships
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="Reference to user in the relationship"
    )
    
    publisher_id = Column(
        UUID(as_uuid=True),
        ForeignKey("publishers.id", ondelete="CASCADE"),
        nullable=False,
        comment="Reference to publisher in the relationship"
    )
    
    # Role and Permissions
    role_id = Column(
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="SET NULL"),
        nullable=True,
        comment="Reference to role assigned to user for this publisher"
    )
    
    # Legacy role field for backward compatibility during migration
    legacy_role = Column(
        String(20),
        nullable=True,
        comment="Legacy role field (deprecated - use role_id): owner, admin, manager, editor, viewer, external"
    )
    
    permissions = Column(
        JSONB,
        default=dict,
        comment="Specific permissions and restrictions for this user-publisher relationship"
    )
    
    restrictions = Column(
        JSONB,
        default=dict,
        comment="Access restrictions and limitations specific to this relationship"
    )
    
    # Status and Access Control
    status = Column(
        String(20),
        nullable=False,
        default="active",
        comment="Relationship status: active, suspended, invited, expired, revoked"
    )
    
    is_primary = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="True if this is the user's primary/default publisher relationship"
    )
    
    # Invitation and Onboarding
    invited_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
        comment="User who sent the invitation (null for direct assignments)"
    )
    
    invited_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when invitation was sent"
    )
    
    invitation_token = Column(
        String(255),
        nullable=True,
        comment="Unique token for invitation acceptance (hashed for security)"
    )
    
    invitation_expires_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Expiration timestamp for invitation"
    )
    
    joined_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when user accepted invitation and joined publisher"
    )
    
    # Activity Tracking
    last_accessed_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp of user's last access to this publisher"
    )
    
    access_count = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Total number of times user has accessed this publisher"
    )
    
    # Publisher-Specific Settings
    settings = Column(
        JSONB,
        default=dict,
        comment="User preferences specific to this publisher relationship"
    )
    
    # Additional Metadata
    metadata = Column(
        JSONB,
        default=dict,
        comment="Additional relationship metadata and flexible attributes"
    )

    # Table-level constraints and indexes
    __table_args__ = (
        # Check constraints for enum-like fields
        CheckConstraint(
            "legacy_role IS NULL OR legacy_role IN ('owner', 'admin', 'manager', 'editor', 'viewer', 'external')",
            name="valid_legacy_role"
        ),
        CheckConstraint(
            "status IN ('active', 'suspended', 'invited', 'expired', 'revoked')",
            name="valid_user_publisher_status"
        ),
        
        # Business rules constraints
        CheckConstraint(
            "access_count >= 0",
            name="non_negative_access_count"
        ),
        CheckConstraint(
            "(status = 'invited' AND invited_by IS NOT NULL AND invited_at IS NOT NULL) OR status != 'invited'",
            name="invited_status_requires_invitation_data"
        ),
        CheckConstraint(
            "(invitation_token IS NOT NULL AND invitation_expires_at IS NOT NULL) OR invitation_token IS NULL",
            name="invitation_token_requires_expiration"
        ),
        CheckConstraint(
            "joined_at IS NULL OR joined_at >= invited_at",
            name="joined_after_invited"
        ),
        CheckConstraint(
            "invitation_expires_at IS NULL OR invitation_expires_at > invited_at",
            name="invitation_expires_after_sent"
        ),
        
        # Unique constraints
        # Each user can only have one relationship per publisher
        UniqueConstraint("user_id", "publisher_id", name="unique_user_publisher"),
        
        # Only one primary relationship per user
        # Note: This would be implemented as a partial unique index in PostgreSQL
        # UNIQUE (user_id) WHERE is_primary = true
        
        # Performance indexes
        Index("idx_user_publishers_user_id", "user_id"),
        Index("idx_user_publishers_publisher_id", "publisher_id"),
        Index("idx_user_publishers_role", "role"),
        Index("idx_user_publishers_status", "status"),
        Index("idx_user_publishers_invited_by", "invited_by"),
        Index("idx_user_publishers_is_primary", "is_primary"),
        Index("idx_user_publishers_invitation_token", "invitation_token"),
        Index("idx_user_publishers_joined_at", "joined_at"),
        Index("idx_user_publishers_last_accessed", "last_accessed_at"),
        Index("idx_user_publishers_created_at", "created_at"),
        
        # Composite indexes for common query patterns
        Index("idx_user_publishers_user_status", "user_id", "status"),
        Index("idx_user_publishers_publisher_status", "publisher_id", "status"),
        Index("idx_user_publishers_user_role", "user_id", "role"),
        Index("idx_user_publishers_publisher_role", "publisher_id", "role"),
        Index("idx_user_publishers_status_invited", "status", "invited_at"),
        Index("idx_user_publishers_status_expires", "status", "invitation_expires_at"),
    )

    # Relationships
    user = relationship("User", foreign_keys=[user_id], back_populates="publisher_relationships")
    publisher = relationship("Publisher", back_populates="user_relationships")
    role = relationship("Role", back_populates="user_publisher_relationships")
    inviter = relationship("User", foreign_keys=[invited_by])

    def __init__(self, **kwargs):
        """
        Initialize UserPublisher with default permissions and settings.
        
        Sets up role-based default permissions, publisher-specific settings,
        and metadata structure for new user-publisher relationships.
        """
        super().__init__(**kwargs)
        
        # Initialize default permissions based on role
        if not self.permissions:
            self.permissions = self._get_default_permissions_for_role(self.role_name)
        
        # Initialize default restrictions
        if not self.restrictions:
            self.restrictions = {
                "ip_whitelist": [],
                "allowed_features": [],
                "denied_features": [],
                "time_restrictions": {},
                "data_access_level": "full"
            }
        
        # Initialize default settings
        if not self.settings:
            self.settings = {
                "dashboard_layout": "default",
                "default_catalog_view": "list",
                "notifications": {
                    "new_works": True,
                    "royalty_reports": True,
                    "system_updates": False
                },
                "email_frequency": "immediate",
                "timezone_override": None
            }
        
        # Initialize default metadata
        if not self.metadata:
            self.metadata = {
                "invitation_source": "direct",
                "onboarding_completed": False,
                "training_completed": False,
                "last_role_change": None,
                "performance_metrics": {}
            }

    @property
    def is_active(self) -> bool:
        """Check if relationship is in active status."""
        return self.status == "active"
    
    @property
    def is_suspended(self) -> bool:
        """Check if relationship is suspended."""
        return self.status == "suspended"
    
    @property
    def is_invited(self) -> bool:
        """Check if user is invited but hasn't joined yet."""
        return self.status == "invited"
    
    @property
    def role_name(self) -> str:
        """Get current role name (from role or legacy role)."""
        if self.role:
            return self.role.name
        return self.legacy_role or "viewer"
    
    @property
    def is_owner(self) -> bool:
        """Check if user has owner role."""
        return self.role_name == "owner"
    
    @property
    def is_admin(self) -> bool:
        """Check if user has admin role."""
        return self.role_name == "admin"
    
    @property
    def can_manage_users(self) -> bool:
        """Check if user can manage other users."""
        if self.role:
            return self.role.has_permission("users:manage")
        return self.role_name in ["owner", "admin", "manager"]
    
    @property
    def can_invite_users(self) -> bool:
        """Check if user can invite new users."""
        if self.role:
            return self.role.has_permission("users:invite")
        return self.role_name in ["owner", "admin"]
    
    @property
    def invitation_is_expired(self) -> bool:
        """Check if invitation has expired."""
        if not self.invitation_expires_at:
            return False
        return datetime.utcnow() > self.invitation_expires_at
    
    @property
    def days_since_last_access(self) -> Optional[int]:
        """Get number of days since last access."""
        if not self.last_accessed_at:
            return None
        return (datetime.utcnow() - self.last_accessed_at).days

    def _get_default_permissions_for_role(self, role: str) -> Dict[str, Any]:
        """
        Get default permissions structure based on role.
        
        Args:
            role: User role
            
        Returns:
            dict: Default permissions for the role
        """
        permission_templates = {
            "owner": {
                "catalog": {"read": True, "write": True, "delete": True, "admin": True},
                "users": {"read": True, "write": True, "delete": True, "invite": True},
                "reports": {"read": True, "write": True, "export": True, "admin": True},
                "settings": {"read": True, "write": True, "billing": True, "integrations": True},
                "api": {"read": True, "write": True, "admin": True},
                "system": {"backup": True, "audit": True, "support": True}
            },
            "admin": {
                "catalog": {"read": True, "write": True, "delete": True, "admin": False},
                "users": {"read": True, "write": True, "delete": False, "invite": True},
                "reports": {"read": True, "write": True, "export": True, "admin": False},
                "settings": {"read": True, "write": True, "billing": False, "integrations": True},
                "api": {"read": True, "write": True, "admin": False},
                "system": {"backup": False, "audit": True, "support": False}
            },
            "manager": {
                "catalog": {"read": True, "write": True, "delete": False, "admin": False},
                "users": {"read": True, "write": False, "delete": False, "invite": False},
                "reports": {"read": True, "write": False, "export": True, "admin": False},
                "settings": {"read": True, "write": False, "billing": False, "integrations": False},
                "api": {"read": True, "write": True, "admin": False},
                "system": {"backup": False, "audit": False, "support": False}
            },
            "editor": {
                "catalog": {"read": True, "write": True, "delete": False, "admin": False},
                "users": {"read": True, "write": False, "delete": False, "invite": False},
                "reports": {"read": True, "write": False, "export": False, "admin": False},
                "settings": {"read": True, "write": False, "billing": False, "integrations": False},
                "api": {"read": True, "write": False, "admin": False},
                "system": {"backup": False, "audit": False, "support": False}
            },
            "viewer": {
                "catalog": {"read": True, "write": False, "delete": False, "admin": False},
                "users": {"read": True, "write": False, "delete": False, "invite": False},
                "reports": {"read": True, "write": False, "export": False, "admin": False},
                "settings": {"read": True, "write": False, "billing": False, "integrations": False},
                "api": {"read": True, "write": False, "admin": False},
                "system": {"backup": False, "audit": False, "support": False}
            },
            "external": {
                "catalog": {"read": True, "write": False, "delete": False, "admin": False},
                "users": {"read": False, "write": False, "delete": False, "invite": False},
                "reports": {"read": False, "write": False, "export": False, "admin": False},
                "settings": {"read": False, "write": False, "billing": False, "integrations": False},
                "api": {"read": True, "write": False, "admin": False},
                "system": {"backup": False, "audit": False, "support": False}
            }
        }
        
        return permission_templates.get(role, permission_templates["viewer"])

    def has_permission(self, area: str, action: str) -> bool:
        """
        Check if user has specific permission.
        
        Args:
            area: Permission area (e.g., "catalog", "users", "reports")
            action: Action within area (e.g., "read", "write", "delete")
            
        Returns:
            bool: True if user has permission
        """
        if not self.is_active:
            return False
        
        if not self.permissions or area not in self.permissions:
            return False
        
        area_permissions = self.permissions[area]
        return area_permissions.get(action, False)

    def can_access_feature(self, feature: str) -> bool:
        """
        Check if user can access a specific feature.
        
        Args:
            feature: Feature name to check
            
        Returns:
            bool: True if feature is accessible
        """
        if not self.is_active:
            return False
        
        # Check denied features first
        denied_features = self.restrictions.get("denied_features", [])
        if feature in denied_features:
            return False
        
        # Check allowed features (empty list means all features allowed)
        allowed_features = self.restrictions.get("allowed_features", [])
        if allowed_features and feature not in allowed_features:
            return False
        
        return True

    def update_role(self, new_role_id: uuid.UUID, updated_by: uuid.UUID) -> None:
        """
        Update user role and refresh permissions.
        
        Args:
            new_role_id: UUID of new role to assign
            updated_by: UUID of user making the change
        """
        old_role_name = self.role_name
        self.role_id = new_role_id
        
        # Clear legacy role when updating to new role system
        self.legacy_role = None
        
        # Update metadata
        self.update_metadata("last_role_change", {
            "from": old_role_name,
            "to": self.role_name if self.role else "unknown",
            "updated_by": str(updated_by),
            "updated_at": datetime.utcnow().isoformat()
        })

    def update_legacy_role(self, new_role: str, updated_by: uuid.UUID) -> None:
        """
        Update legacy role (for backward compatibility during migration).
        
        Args:
            new_role: New legacy role string to assign
            updated_by: UUID of user making the change
        """
        old_role = self.legacy_role
        self.legacy_role = new_role
        self.permissions = self._get_default_permissions_for_role(new_role)
        
        # Update metadata
        self.update_metadata("last_role_change", {
            "from": old_role,
            "to": new_role,
            "updated_by": str(updated_by),
            "updated_at": datetime.utcnow().isoformat(),
            "migration_note": "Updated using legacy role system"
        })

    def suspend_access(self, reason: str, suspended_by: uuid.UUID) -> None:
        """
        Suspend user access to publisher.
        
        Args:
            reason: Reason for suspension
            suspended_by: UUID of user performing suspension
        """
        self.status = "suspended"
        
        # Update metadata
        self.update_metadata("suspension", {
            "reason": reason,
            "suspended_by": str(suspended_by),
            "suspended_at": datetime.utcnow().isoformat(),
            "previous_status": "active"
        })

    def reactivate_access(self, reactivated_by: uuid.UUID) -> None:
        """
        Reactivate suspended user access.
        
        Args:
            reactivated_by: UUID of user performing reactivation
        """
        self.status = "active"
        
        # Update metadata
        suspension_data = self.get_metadata("suspension", {})
        self.update_metadata("reactivation", {
            "reactivated_by": str(reactivated_by),
            "reactivated_at": datetime.utcnow().isoformat(),
            "was_suspended_for": suspension_data.get("reason")
        })

    def record_access(self) -> None:
        """Record user access to this publisher."""
        self.last_accessed_at = datetime.utcnow()
        self.access_count += 1

    def generate_invitation_token(self) -> str:
        """
        Generate secure invitation token.
        
        Returns:
            str: Secure invitation token
        """
        import secrets
        import hashlib
        
        # Generate random token
        raw_token = secrets.token_urlsafe(32)
        
        # Hash for storage (store hash, return raw token)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        self.invitation_token = token_hash
        
        # Set expiration (7 days)
        from datetime import timedelta
        self.invitation_expires_at = datetime.utcnow() + timedelta(days=7)
        
        return raw_token

    def verify_invitation_token(self, token: str) -> bool:
        """
        Verify invitation token.
        
        Args:
            token: Raw invitation token to verify
            
        Returns:
            bool: True if token is valid and not expired
        """
        import hashlib
        
        if not self.invitation_token or not token:
            return False
        
        if self.invitation_is_expired:
            return False
        
        # Hash provided token and compare
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        return token_hash == self.invitation_token

    def accept_invitation(self) -> None:
        """Accept invitation and activate relationship."""
        if not self.is_invited:
            raise ValueError("No pending invitation to accept")
        
        if self.invitation_is_expired:
            raise ValueError("Invitation has expired")
        
        self.status = "active"
        self.joined_at = datetime.utcnow()
        self.invitation_token = None
        self.invitation_expires_at = None
        
        # Update metadata
        self.update_metadata("onboarding_completed", True)

    def get_setting(self, key: str, default=None):
        """
        Get a specific setting value with fallback.
        
        Args:
            key: Setting key (supports dot notation for nested keys)
            default: Default value if key not found
            
        Returns:
            Setting value or default
        """
        if not self.settings:
            return default
            
        # Support dot notation for nested keys
        keys = key.split('.')
        value = self.settings
        
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default

    def update_setting(self, key: str, value) -> None:
        """
        Update a specific setting value.
        
        Args:
            key: Setting key (supports dot notation for nested keys)
            value: New value to set
        """
        if not self.settings:
            self.settings = {}
            
        # Support dot notation for nested keys
        keys = key.split('.')
        current = self.settings
        
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

    def get_effective_permissions(self) -> Dict[str, Any]:
        """
        Get effective permissions considering role, restrictions, and publisher settings.
        
        Returns:
            dict: Complete effective permissions
        """
        effective_permissions = self.permissions.copy() if self.permissions else {}
        
        # Apply restrictions
        if self.restrictions:
            # Apply feature restrictions
            denied_features = self.restrictions.get("denied_features", [])
            for feature in denied_features:
                if feature in effective_permissions:
                    # Set all actions to False for denied features
                    for action in effective_permissions[feature]:
                        effective_permissions[feature][action] = False
        
        return effective_permissions

    def __repr__(self) -> str:
        """String representation of the UserPublisher."""
        return (f"<UserPublisher(id={self.id}, user_id={self.user_id}, "
                f"publisher_id={self.publisher_id}, role='{self.role_name}', "
                f"status='{self.status}', is_primary={self.is_primary})>")

    def __str__(self) -> str:
        """Human-readable string representation."""
        return f"User-Publisher Relationship ({self.role_name}, {self.status})"