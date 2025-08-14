"""Role model for role-based access control in the multi-tenant publishing platform."""

import uuid
from typing import List, Dict, Any, Optional

from sqlalchemy import (
    Column, String, Boolean, Integer, CheckConstraint, Index, UUID, Text,
    ForeignKey, UniqueConstraint, Table
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from .base import TimestampMixin
from src.core.database import Base


# Association table for role-permission many-to-many relationship
role_permissions_table = Table(
    'role_permissions_simple',
    Base.metadata,
    Column('role_id', UUID(as_uuid=True), ForeignKey('roles.id', ondelete='CASCADE'), primary_key=True),
    Column('permission_id', UUID(as_uuid=True), ForeignKey('permissions.id', ondelete='CASCADE'), primary_key=True),
    Index('idx_role_permissions_simple_role', 'role_id'),
    Index('idx_role_permissions_simple_permission', 'permission_id'),
    comment="Simple many-to-many relationship between roles and permissions"
)


class RolePermission(Base, TimestampMixin):
    """
    Role-Permission association model with additional metadata.
    
    This model tracks the relationship between roles and permissions
    with audit information about when and by whom permissions were granted.
    """
    
    __tablename__ = "role_permissions"
    
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Primary key UUID"
    )
    
    role_id = Column(
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False,
        comment="Role UUID"
    )
    
    permission_id = Column(
        UUID(as_uuid=True),
        ForeignKey("permissions.id", ondelete="CASCADE"),
        nullable=False,
        comment="Permission UUID"
    )
    
    granted_by = Column(
        UUID(as_uuid=True),
        nullable=True,
        comment="User who granted this permission to the role"
    )
    
    # Relationships
    role = relationship("Role", back_populates="role_permissions")
    permission = relationship("Permission", back_populates="role_permissions")
    
    __table_args__ = (
        UniqueConstraint('role_id', 'permission_id', name='uq_role_permission'),
        Index('idx_role_permissions_role_id', 'role_id'),
        Index('idx_role_permissions_permission_id', 'permission_id'),
    )


class Role(Base, TimestampMixin):
    """
    Role model representing user roles with permission sets in the multi-tenant platform.
    
    This model defines roles that can be assigned to users within publishers/tenants.
    Roles contain collections of permissions and define what actions users can perform.
    
    Role Types:
    - System: Built-in roles that are available to all publishers
    - Publisher: Custom roles created by individual publishers
    - Template: Role templates that can be used to create new roles
    
    Standard System Roles:
    - Super Admin: Full system access (system-wide)
    - Publisher Admin: Full publisher management access
    - Manager: General management access with some restrictions
    - Editor: Content creation and editing access
    - Viewer: Read-only access to most data
    - API User: Programmatic access via API
    
    Role Features:
    - Hierarchical structure with parent-child relationships
    - Permission inheritance from parent roles
    - Dynamic permission assignment and removal
    - Usage tracking and analytics
    - Active/inactive status management
    - Publisher-specific customization
    """
    
    __tablename__ = "roles"
    
    # Core Identity Fields
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Primary key UUID for role identity"
    )
    
    name = Column(
        String(100),
        nullable=False,
        comment="Role name unique within publisher context"
    )
    
    display_name = Column(
        String(200),
        nullable=False,
        comment="Human-readable role name for UI display"
    )
    
    description = Column(
        Text,
        nullable=True,
        comment="Detailed description of role purpose and capabilities"
    )
    
    # Publisher Association
    publisher_id = Column(
        UUID(as_uuid=True),
        ForeignKey("publishers.id", ondelete="CASCADE"),
        nullable=True,
        comment="Publisher UUID (null for system roles)"
    )
    
    # Role Classification
    role_type = Column(
        String(20),
        nullable=False,
        default="publisher",
        comment="Role type: system, publisher, template"
    )
    
    category = Column(
        String(50),
        nullable=False,
        default="general",
        comment="Role category for organization (admin, content, finance, etc.)"
    )
    
    # Hierarchy and Inheritance
    parent_role_id = Column(
        UUID(as_uuid=True),
        ForeignKey("roles.id"),
        nullable=True,
        comment="Parent role ID for hierarchical roles"
    )
    
    inherit_permissions = Column(
        Boolean,
        nullable=False,
        default=True,
        comment="Whether to inherit permissions from parent role"
    )
    
    hierarchy_level = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Hierarchy level (0 = top level, higher numbers = deeper)"
    )
    
    # Status and Configuration
    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        comment="Whether this role is currently active and assignable"
    )
    
    is_default = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Whether this is a default role for new users"
    )
    
    is_system_role = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Whether this is a built-in system role"
    )
    
    is_assignable = Column(
        Boolean,
        nullable=False,
        default=True,
        comment="Whether this role can be assigned to users"
    )
    
    # Usage and Analytics
    user_count = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Current number of users with this role"
    )
    
    max_users = Column(
        Integer,
        nullable=True,
        comment="Maximum number of users that can have this role (null for unlimited)"
    )
    
    # Role Configuration
    permissions_locked = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Whether permissions for this role are locked from modification"
    )
    
    auto_assign_conditions = Column(
        JSONB,
        default=dict,
        comment="Conditions for automatic role assignment"
    )
    
    role_settings = Column(
        JSONB,
        default=dict,
        comment="Role-specific settings and configuration"
    )
    
    # Metadata Fields
    metadata = Column(
        JSONB,
        default=dict,
        comment="Additional role metadata and attributes"
    )
    
    # Table-level constraints and indexes
    __table_args__ = (
        # Unique constraints
        UniqueConstraint('publisher_id', 'name', name='uq_role_name_per_publisher'),
        
        # Check constraints for enum-like fields
        CheckConstraint(
            "role_type IN ('system', 'publisher', 'template')",
            name="valid_role_type"
        ),
        CheckConstraint(
            "category IN ('admin', 'content', 'finance', 'reporting', 'api', 'general')",
            name="valid_role_category"
        ),
        
        # Business rules constraints
        CheckConstraint(
            "length(name) >= 2",
            name="role_name_min_length"
        ),
        CheckConstraint(
            "name ~ '^[a-zA-Z0-9_\\-\\s]+$'",
            name="valid_role_name_format"
        ),
        CheckConstraint(
            "length(display_name) >= 2",
            name="display_name_min_length"
        ),
        CheckConstraint(
            "user_count >= 0",
            name="non_negative_user_count"
        ),
        CheckConstraint(
            "max_users IS NULL OR max_users > 0",
            name="positive_max_users"
        ),
        CheckConstraint(
            "hierarchy_level >= 0 AND hierarchy_level <= 10",
            name="valid_hierarchy_level"
        ),
        
        # System role constraints
        CheckConstraint(
            "NOT is_system_role OR publisher_id IS NULL",
            name="system_roles_no_publisher"
        ),
        CheckConstraint(
            "is_system_role OR publisher_id IS NOT NULL",
            name="publisher_roles_require_publisher"
        ),
        
        # Performance indexes
        Index("idx_roles_name", "name"),
        Index("idx_roles_publisher_id", "publisher_id"),
        Index("idx_roles_role_type", "role_type"),
        Index("idx_roles_category", "category"),
        Index("idx_roles_is_active", "is_active"),
        Index("idx_roles_is_default", "is_default"),
        Index("idx_roles_is_system", "is_system_role"),
        Index("idx_roles_parent_role", "parent_role_id"),
        Index("idx_roles_hierarchy_level", "hierarchy_level"),
        
        # Composite indexes for common query patterns
        Index("idx_roles_publisher_active", "publisher_id", "is_active"),
        Index("idx_roles_publisher_type", "publisher_id", "role_type"),
        Index("idx_roles_type_active", "role_type", "is_active"),
        Index("idx_roles_category_active", "category", "is_active"),
    )

    # Relationships
    publisher = relationship("Publisher", back_populates="roles")
    parent_role = relationship("Role", remote_side=[id], back_populates="child_roles")
    child_roles = relationship("Role", back_populates="parent_role")
    role_permissions = relationship("RolePermission", back_populates="role", lazy="dynamic")
    permissions = relationship("Permission", secondary=role_permissions_table, lazy="dynamic")
    user_publisher_relationships = relationship("UserPublisher", back_populates="role", lazy="dynamic")

    def __init__(self, **kwargs):
        """
        Initialize Role with default settings and metadata.
        
        Sets up default role settings, auto-assignment conditions,
        and metadata structure for new role instances.
        """
        super().__init__(**kwargs)
        
        # Initialize default auto assign conditions if not provided
        if not self.auto_assign_conditions:
            self.auto_assign_conditions = {
                "new_user_default": self.is_default,
                "email_domains": [],
                "user_attributes": {},
                "publisher_settings": {}
            }
        
        # Initialize default role settings if not provided
        if not self.role_settings:
            self.role_settings = {
                "session_timeout_minutes": None,  # Use publisher default
                "require_mfa": False,
                "allowed_ip_ranges": [],
                "api_access_enabled": False,
                "ui_restrictions": {},
                "feature_access": {}
            }
        
        # Initialize default metadata if not provided
        if not self.metadata:
            self.metadata = {
                "created_from_template": None,
                "template_version": None,
                "last_permission_update": None,
                "usage_analytics": {
                    "assignments_this_month": 0,
                    "most_used_permissions": [],
                    "avg_session_duration": None
                },
                "documentation": {
                    "purpose": None,
                    "guidelines": None,
                    "training_materials": []
                }
            }

    @property
    def is_system(self) -> bool:
        """Check if this is a system role."""
        return self.is_system_role
    
    @property
    def is_publisher_role(self) -> bool:
        """Check if this is a publisher-specific role."""
        return self.role_type == "publisher" and self.publisher_id is not None
    
    @property
    def is_template_role(self) -> bool:
        """Check if this is a template role."""
        return self.role_type == "template"
    
    @property
    def can_be_assigned(self) -> bool:
        """Check if role can be assigned to users."""
        return self.is_active and self.is_assignable
    
    @property
    def has_user_limit(self) -> bool:
        """Check if role has a user limit."""
        return self.max_users is not None
    
    @property
    def users_available(self) -> int:
        """Get number of available user slots."""
        if not self.has_user_limit:
            return float('inf')
        return max(0, self.max_users - self.user_count)
    
    @property
    def is_at_capacity(self) -> bool:
        """Check if role is at user capacity."""
        return self.has_user_limit and self.user_count >= self.max_users
    
    @property
    def permission_count(self) -> int:
        """Get total number of permissions assigned to this role."""
        return self.permissions.count()

    @classmethod
    def create_role(
        cls,
        name: str,
        display_name: str,
        publisher_id: uuid.UUID = None,
        role_type: str = "publisher",
        category: str = "general",
        description: str = None,
        parent_role_id: uuid.UUID = None,
        is_default: bool = False,
        permissions: List[str] = None
    ) -> "Role":
        """
        Create a new role with validation.
        
        Args:
            name: Role name (unique within publisher)
            display_name: Human-readable display name
            publisher_id: Publisher UUID (required for publisher roles)
            role_type: Type of role (system, publisher, template)
            category: Role category
            description: Optional role description
            parent_role_id: Parent role for hierarchy
            is_default: Whether this is a default role for new users
            permissions: List of permission names to assign
            
        Returns:
            Role: New role instance
        """
        # Validation
        if role_type == "publisher" and not publisher_id:
            raise ValueError("Publisher roles must have a publisher_id")
        
        if role_type == "system" and publisher_id:
            raise ValueError("System roles cannot have a publisher_id")
        
        role = cls(
            name=name,
            display_name=display_name,
            description=description,
            publisher_id=publisher_id,
            role_type=role_type,
            category=category,
            parent_role_id=parent_role_id,
            is_default=is_default,
            is_system_role=(role_type == "system")
        )
        
        return role

    def add_permission(self, permission_name: str, granted_by: uuid.UUID = None) -> bool:
        """
        Add a permission to this role.
        
        Args:
            permission_name: Name of permission to add
            granted_by: User who granted the permission
            
        Returns:
            bool: True if permission was added, False if already present
        """
        # This would typically be implemented at the service level
        # with proper permission validation and database operations
        pass

    def remove_permission(self, permission_name: str) -> bool:
        """
        Remove a permission from this role.
        
        Args:
            permission_name: Name of permission to remove
            
        Returns:
            bool: True if permission was removed, False if not present
        """
        # This would typically be implemented at the service level
        pass

    def has_permission(self, permission_name: str, include_inherited: bool = True) -> bool:
        """
        Check if role has a specific permission.
        
        Args:
            permission_name: Permission name to check
            include_inherited: Whether to check inherited permissions
            
        Returns:
            bool: True if role has the permission
        """
        # Direct permission check would be implemented at service level
        # This is a placeholder for the interface
        return True

    def get_all_permissions(self, include_inherited: bool = True) -> List[str]:
        """
        Get all permissions for this role.
        
        Args:
            include_inherited: Whether to include inherited permissions
            
        Returns:
            List[str]: List of permission names
        """
        permissions = []
        
        # Add direct permissions (implemented at service level)
        # permissions.extend([p.name for p in self.permissions])
        
        # Add inherited permissions if requested
        if include_inherited and self.inherit_permissions and self.parent_role:
            parent_permissions = self.parent_role.get_all_permissions(include_inherited=True)
            permissions.extend(parent_permissions)
        
        return list(set(permissions))  # Remove duplicates

    def get_effective_permissions(self) -> List[str]:
        """
        Get effective permissions including inheritance and implications.
        
        Returns:
            List[str]: List of effective permission names
        """
        return self.get_all_permissions(include_inherited=True)

    def clone_role(
        self,
        new_name: str,
        new_display_name: str,
        publisher_id: uuid.UUID = None,
        copy_permissions: bool = True
    ) -> "Role":
        """
        Clone this role to create a new role.
        
        Args:
            new_name: Name for the new role
            new_display_name: Display name for the new role
            publisher_id: Publisher for the new role (defaults to same as source)
            copy_permissions: Whether to copy permissions from source role
            
        Returns:
            Role: New cloned role instance
        """
        new_role = Role(
            name=new_name,
            display_name=new_display_name,
            description=f"Cloned from {self.display_name}",
            publisher_id=publisher_id or self.publisher_id,
            role_type="publisher",  # Cloned roles are always publisher roles
            category=self.category,
            parent_role_id=self.parent_role_id,
            inherit_permissions=self.inherit_permissions,
            role_settings=self.role_settings.copy() if self.role_settings else {},
            metadata={
                **(self.metadata.copy() if self.metadata else {}),
                "cloned_from_role_id": str(self.id),
                "cloned_at": str(uuid.uuid4())  # Would use datetime in real implementation
            }
        )
        
        return new_role

    def update_user_count(self, delta: int) -> None:
        """
        Update the user count for this role.
        
        Args:
            delta: Change in user count (+1 for add, -1 for remove)
        """
        self.user_count = max(0, self.user_count + delta)

    def can_assign_to_user(self) -> tuple[bool, Optional[str]]:
        """
        Check if role can be assigned to a new user.
        
        Returns:
            tuple: (can_assign: bool, reason: Optional[str])
        """
        if not self.is_active:
            return False, "Role is not active"
        
        if not self.is_assignable:
            return False, "Role is not assignable"
        
        if self.is_at_capacity:
            return False, f"Role is at maximum capacity ({self.max_users} users)"
        
        return True, None

    def matches_auto_assign_conditions(self, user_data: Dict[str, Any]) -> bool:
        """
        Check if a user matches auto-assignment conditions for this role.
        
        Args:
            user_data: User data to check against conditions
            
        Returns:
            bool: True if user matches auto-assign conditions
        """
        if not self.auto_assign_conditions or not self.is_default:
            return False
        
        conditions = self.auto_assign_conditions
        
        # Check email domain conditions
        if conditions.get("email_domains"):
            user_email = user_data.get("email", "")
            user_domain = user_email.split("@")[-1] if "@" in user_email else ""
            if user_domain not in conditions["email_domains"]:
                return False
        
        # Check user attribute conditions
        if conditions.get("user_attributes"):
            for attr, expected_value in conditions["user_attributes"].items():
                if user_data.get(attr) != expected_value:
                    return False
        
        return True

    def get_role_summary(self) -> Dict[str, Any]:
        """
        Get comprehensive role summary.
        
        Returns:
            Dict: Complete role information
        """
        return {
            "id": str(self.id),
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "role_type": self.role_type,
            "category": self.category,
            "is_active": self.is_active,
            "is_default": self.is_default,
            "is_system": self.is_system_role,
            "user_count": self.user_count,
            "max_users": self.max_users,
            "hierarchy": {
                "level": self.hierarchy_level,
                "parent_role_id": str(self.parent_role_id) if self.parent_role_id else None,
                "inherit_permissions": self.inherit_permissions
            },
            "permissions": {
                "count": self.permission_count,
                "locked": self.permissions_locked
            },
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }

    def __repr__(self) -> str:
        """String representation of the Role."""
        return (f"<Role(id={self.id}, name='{self.name}', "
                f"type='{self.role_type}', category='{self.category}', "
                f"users={self.user_count}, active={self.is_active})>")

    def __str__(self) -> str:
        """Human-readable string representation."""
        return f"{self.display_name} ({self.role_type.title()} Role)"


# Define standard system roles
SYSTEM_ROLES = [
    {
        "name": "super_admin",
        "display_name": "Super Administrator",
        "description": "Full system access across all publishers and system settings",
        "category": "admin",
        "permissions": ["*:*:system"]  # All permissions at system level
    },
    {
        "name": "publisher_admin",
        "display_name": "Publisher Administrator", 
        "description": "Full administrative access within publisher organization",
        "category": "admin",
        "permissions": [
            "users:*", "roles:*", "settings:*", "works:*", "songwriters:*", 
            "recordings:*", "reports:*", "integrations:*"
        ]
    },
    {
        "name": "manager",
        "display_name": "Manager",
        "description": "General management access with content and user management capabilities",
        "category": "content",
        "permissions": [
            "users:read", "users:invite", "works:*", "songwriters:*", 
            "recordings:*", "reports:read", "reports:export"
        ]
    },
    {
        "name": "editor",
        "display_name": "Content Editor",
        "description": "Content creation and editing access for catalog management",
        "category": "content",
        "permissions": [
            "works:create", "works:read", "works:update", "works:list",
            "songwriters:create", "songwriters:read", "songwriters:update", "songwriters:list",
            "recordings:create", "recordings:read", "recordings:update", "recordings:list"
        ]
    },
    {
        "name": "viewer",
        "display_name": "Viewer",
        "description": "Read-only access to catalog and basic reporting",
        "category": "general",
        "permissions": [
            "works:read", "works:list", "songwriters:read", "songwriters:list",
            "recordings:read", "recordings:list", "reports:read"
        ]
    },
    {
        "name": "api_user",
        "display_name": "API User",
        "description": "Programmatic access via API endpoints",
        "category": "api",
        "permissions": [
            "api:read", "api:write", "works:*", "songwriters:*", "recordings:*"
        ]
    },
    {
        "name": "financial_admin",
        "display_name": "Financial Administrator",
        "description": "Full access to financial data, royalties, and statements",
        "category": "finance",
        "permissions": [
            "royalties:*", "statements:*", "reports:*", "works:read", 
            "songwriters:read", "recordings:read"
        ]
    }
]


def create_system_roles() -> List[Role]:
    """
    Create all standard system roles.
    
    Returns:
        List[Role]: List of system role objects
    """
    roles = []
    
    for role_data in SYSTEM_ROLES:
        role = Role.create_role(
            name=role_data["name"],
            display_name=role_data["display_name"],
            role_type="system",
            category=role_data["category"],
            description=role_data["description"]
        )
        roles.append(role)
    
    return roles