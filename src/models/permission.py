"""Permission model for granular access control in the multi-tenant publishing platform."""

import uuid
from typing import List, Dict, Any, Optional

from sqlalchemy import (
    Column, String, Boolean, CheckConstraint, Index, UUID, Text
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from .base import TimestampMixin
from src.core.database import Base


class Permission(Base, TimestampMixin):
    """
    Permission model representing granular access control capabilities.
    
    This model defines individual permissions that can be assigned to roles
    and users within the multi-tenant publishing platform. Permissions follow
    a resource:action pattern for clear, predictable access control.
    
    Permission Structure:
    - Resource: The entity being accessed (works, songwriters, recordings, etc.)
    - Action: The operation being performed (create, read, update, delete, list, etc.)
    - Scope: The data scope (own, publisher, system)
    
    Examples:
    - "works:create" - Can create new works
    - "songwriters:read" - Can view songwriter information
    - "recordings:update:own" - Can update own recordings only
    - "users:manage:publisher" - Can manage users within publisher
    - "reports:export" - Can export report data
    - "settings:admin" - Can access admin settings
    
    Permission Types:
    - System: Built-in permissions that apply across all tenants
    - Custom: Publisher-specific permissions for custom features
    - API: Permissions for API access and operations
    - Feature: Permissions for specific platform features
    """
    
    __tablename__ = "permissions"
    
    # Core Identity Fields
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Primary key UUID for permission identity"
    )
    
    name = Column(
        String(100),
        nullable=False,
        unique=True,
        comment="Unique permission name in resource:action format (e.g., 'works:create')"
    )
    
    display_name = Column(
        String(200),
        nullable=False,
        comment="Human-readable permission name for UI display"
    )
    
    description = Column(
        Text,
        nullable=True,
        comment="Detailed description of what this permission allows"
    )
    
    # Permission Structure
    resource = Column(
        String(50),
        nullable=False,
        comment="Resource/entity this permission applies to (e.g., 'works', 'users')"
    )
    
    action = Column(
        String(50),
        nullable=False,
        comment="Action/operation this permission allows (e.g., 'create', 'read', 'update')"
    )
    
    scope = Column(
        String(20),
        nullable=False,
        default="publisher",
        comment="Data scope: own, publisher, system"
    )
    
    # Permission Classification
    permission_type = Column(
        String(20),
        nullable=False,
        default="system",
        comment="Permission type: system, custom, api, feature"
    )
    
    category = Column(
        String(50),
        nullable=False,
        comment="Permission category for organization (e.g., 'catalog', 'user_management', 'reporting')"
    )
    
    # Status and Configuration
    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        comment="Whether this permission is currently active and available"
    )
    
    is_dangerous = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="True for permissions that can cause data loss or security risks"
    )
    
    requires_admin = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="True if permission requires admin-level approval to grant"
    )
    
    # Hierarchy and Dependencies
    parent_permission_id = Column(
        UUID(as_uuid=True),
        nullable=True,
        comment="Parent permission ID for hierarchical permissions"
    )
    
    dependencies = Column(
        JSONB,
        default=list,
        comment="List of permission names that this permission depends on"
    )
    
    # Feature and Plan Restrictions
    required_plan_types = Column(
        JSONB,
        default=list,
        comment="List of plan types that can use this permission"
    )
    
    feature_flags = Column(
        JSONB,
        default=list,
        comment="List of feature flags required to enable this permission"
    )
    
    # Metadata Fields
    metadata = Column(
        JSONB,
        default=dict,
        comment="Additional permission metadata and configuration"
    )
    
    # Table-level constraints and indexes
    __table_args__ = (
        # Check constraints for enum-like fields
        CheckConstraint(
            "scope IN ('own', 'publisher', 'system')",
            name="valid_permission_scope"
        ),
        CheckConstraint(
            "permission_type IN ('system', 'custom', 'api', 'feature')",
            name="valid_permission_type"
        ),
        CheckConstraint(
            "category IN ('catalog', 'user_management', 'reporting', 'financial', 'settings', 'integrations', 'api', 'admin')",
            name="valid_permission_category"
        ),
        
        # Business rules constraints
        CheckConstraint(
            "length(name) >= 3",
            name="permission_name_min_length"
        ),
        CheckConstraint(
            "name ~ '^[a-z][a-z0-9_]*:[a-z][a-z0-9_]*(:.*)?$'",
            name="valid_permission_name_format"
        ),
        CheckConstraint(
            "length(display_name) >= 3",
            name="display_name_min_length"
        ),
        CheckConstraint(
            "length(resource) >= 2",
            name="resource_min_length"
        ),
        CheckConstraint(
            "resource ~ '^[a-z][a-z0-9_]*$'",
            name="valid_resource_format"
        ),
        CheckConstraint(
            "length(action) >= 2",
            name="action_min_length"
        ),
        CheckConstraint(
            "action ~ '^[a-z][a-z0-9_]*$'",
            name="valid_action_format"
        ),
        
        # Performance indexes
        Index("idx_permissions_name", "name"),
        Index("idx_permissions_resource", "resource"),
        Index("idx_permissions_action", "action"),
        Index("idx_permissions_scope", "scope"),
        Index("idx_permissions_type", "permission_type"),
        Index("idx_permissions_category", "category"),
        Index("idx_permissions_active", "is_active"),
        Index("idx_permissions_dangerous", "is_dangerous"),
        Index("idx_permissions_requires_admin", "requires_admin"),
        Index("idx_permissions_parent", "parent_permission_id"),
        
        # Composite indexes for common query patterns
        Index("idx_permissions_resource_action", "resource", "action"),
        Index("idx_permissions_category_active", "category", "is_active"),
        Index("idx_permissions_type_active", "permission_type", "is_active"),
        Index("idx_permissions_scope_active", "scope", "is_active"),
    )

    # Relationships  
    role_permissions = relationship("RolePermission", back_populates="permission", lazy="dynamic")

    def __init__(self, **kwargs):
        """
        Initialize Permission with default metadata.
        
        Parses permission name to extract resource and action if not provided,
        and sets up default metadata structure.
        """
        super().__init__(**kwargs)
        
        # Parse resource and action from name if not explicitly provided
        if self.name and not (self.resource and self.action):
            parts = self.name.split(":")
            if len(parts) >= 2:
                if not self.resource:
                    self.resource = parts[0]
                if not self.action:
                    self.action = parts[1]
        
        # Initialize default metadata if not provided
        if not self.metadata:
            self.metadata = {
                "created_by_system": True,
                "last_modified_by": None,
                "usage_count": 0,
                "related_features": [],
                "documentation_url": None
            }
        
        # Ensure dependencies and feature flags are lists
        if self.dependencies is None:
            self.dependencies = []
        if self.required_plan_types is None:
            self.required_plan_types = []
        if self.feature_flags is None:
            self.feature_flags = []

    @property
    def full_name(self) -> str:
        """Get full permission name including scope if applicable."""
        base_name = f"{self.resource}:{self.action}"
        if self.scope != "publisher":  # Only show non-default scopes
            return f"{base_name}:{self.scope}"
        return base_name
    
    @property
    def is_system_permission(self) -> bool:
        """Check if this is a system-level permission."""
        return self.permission_type == "system"
    
    @property
    def is_custom_permission(self) -> bool:
        """Check if this is a custom publisher permission."""
        return self.permission_type == "custom"
    
    @property
    def is_api_permission(self) -> bool:
        """Check if this is an API access permission."""
        return self.permission_type == "api"
    
    @property
    def is_feature_permission(self) -> bool:
        """Check if this is a feature-gated permission."""
        return self.permission_type == "feature"
    
    @property
    def requires_dependencies(self) -> bool:
        """Check if permission has dependencies."""
        return bool(self.dependencies)
    
    @property
    def has_plan_restrictions(self) -> bool:
        """Check if permission is restricted to specific plans."""
        return bool(self.required_plan_types)
    
    @property
    def has_feature_restrictions(self) -> bool:
        """Check if permission requires feature flags."""
        return bool(self.feature_flags)

    @classmethod
    def create_permission(
        cls,
        name: str,
        display_name: str,
        description: str = None,
        category: str = "catalog",
        scope: str = "publisher",
        permission_type: str = "system",
        is_dangerous: bool = False,
        requires_admin: bool = False,
        dependencies: List[str] = None,
        required_plan_types: List[str] = None,
        feature_flags: List[str] = None
    ) -> "Permission":
        """
        Create a new permission with validation.
        
        Args:
            name: Permission name in resource:action format
            display_name: Human-readable name
            description: Optional description
            category: Permission category
            scope: Permission scope (own, publisher, system)
            permission_type: Type of permission
            is_dangerous: Whether permission is dangerous
            requires_admin: Whether permission requires admin approval
            dependencies: List of dependent permission names
            required_plan_types: List of required plan types
            feature_flags: List of required feature flags
            
        Returns:
            Permission: New permission instance
        """
        # Parse resource and action from name
        parts = name.split(":")
        if len(parts) < 2:
            raise ValueError("Permission name must be in format 'resource:action'")
        
        resource = parts[0]
        action = parts[1]
        
        return cls(
            name=name,
            display_name=display_name,
            description=description,
            resource=resource,
            action=action,
            scope=scope,
            permission_type=permission_type,
            category=category,
            is_dangerous=is_dangerous,
            requires_admin=requires_admin,
            dependencies=dependencies or [],
            required_plan_types=required_plan_types or [],
            feature_flags=feature_flags or []
        )

    def implies_permission(self, other_permission: str) -> bool:
        """
        Check if this permission implies another permission.
        
        Args:
            other_permission: Permission name to check
            
        Returns:
            bool: True if this permission implies the other
        """
        # Admin permissions typically imply read permissions
        if self.action == "admin" and other_permission.endswith(":read"):
            return self.resource == other_permission.split(":")[0]
        
        # Update permissions typically imply read permissions
        if self.action == "update" and other_permission.endswith(":read"):
            return self.resource == other_permission.split(":")[0]
        
        # Delete permissions typically imply update and read permissions
        if self.action == "delete":
            other_parts = other_permission.split(":")
            if len(other_parts) >= 2 and other_parts[0] == self.resource:
                return other_parts[1] in ["read", "update"]
        
        # System scope typically implies publisher and own scopes
        if self.scope == "system":
            if other_permission.startswith(f"{self.resource}:{self.action}"):
                return True
        
        # Publisher scope typically implies own scope
        if self.scope == "publisher" and other_permission.endswith(":own"):
            base_permission = other_permission.replace(":own", "")
            return self.name == base_permission
        
        return False

    def check_dependencies(self, granted_permissions: List[str]) -> tuple[bool, List[str]]:
        """
        Check if all required dependencies are met.
        
        Args:
            granted_permissions: List of currently granted permission names
            
        Returns:
            tuple: (all_met: bool, missing_permissions: List[str])
        """
        if not self.dependencies:
            return True, []
        
        missing = []
        for dep in self.dependencies:
            if dep not in granted_permissions:
                missing.append(dep)
        
        return len(missing) == 0, missing

    def is_available_for_plan(self, plan_type: str) -> bool:
        """
        Check if permission is available for a specific plan type.
        
        Args:
            plan_type: Plan type to check
            
        Returns:
            bool: True if available for the plan
        """
        if not self.required_plan_types:
            return True  # Available for all plans
        
        return plan_type in self.required_plan_types

    def is_available_with_features(self, enabled_features: List[str]) -> bool:
        """
        Check if permission is available with enabled features.
        
        Args:
            enabled_features: List of enabled feature flags
            
        Returns:
            bool: True if all required features are enabled
        """
        if not self.feature_flags:
            return True  # No feature requirements
        
        for flag in self.feature_flags:
            if flag not in enabled_features:
                return False
        
        return True

    def get_related_permissions(self) -> List[str]:
        """
        Get list of permissions that this permission relates to.
        
        Returns:
            List[str]: Related permission names
        """
        related = []
        
        # Add permissions this one implies
        base_name = f"{self.resource}:"
        if self.action in ["admin", "manage"]:
            related.extend([
                f"{base_name}create",
                f"{base_name}read", 
                f"{base_name}update",
                f"{base_name}delete",
                f"{base_name}list"
            ])
        elif self.action == "update":
            related.append(f"{base_name}read")
        elif self.action == "delete":
            related.extend([f"{base_name}read", f"{base_name}update"])
        
        # Add scope variations
        if self.scope == "system":
            related.extend([
                f"{self.resource}:{self.action}:publisher",
                f"{self.resource}:{self.action}:own"
            ])
        elif self.scope == "publisher":
            related.append(f"{self.resource}:{self.action}:own")
        
        return [p for p in related if p != self.name]

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert permission to dictionary representation.
        
        Returns:
            Dict: Permission data as dictionary
        """
        return {
            "id": str(self.id),
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "resource": self.resource,
            "action": self.action,
            "scope": self.scope,
            "permission_type": self.permission_type,
            "category": self.category,
            "is_active": self.is_active,
            "is_dangerous": self.is_dangerous,
            "requires_admin": self.requires_admin,
            "dependencies": self.dependencies,
            "required_plan_types": self.required_plan_types,
            "feature_flags": self.feature_flags,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }

    def __repr__(self) -> str:
        """String representation of the Permission."""
        return (f"<Permission(id={self.id}, name='{self.name}', "
                f"resource='{self.resource}', action='{self.action}', "
                f"scope='{self.scope}', type='{self.permission_type}')>")

    def __str__(self) -> str:
        """Human-readable string representation."""
        return f"{self.display_name} ({self.name})"


# Define standard system permissions
SYSTEM_PERMISSIONS = [
    # Catalog Management
    ("works:create", "Create Works", "Create new musical works", "catalog"),
    ("works:read", "View Works", "View work details and metadata", "catalog"),
    ("works:update", "Edit Works", "Update work information", "catalog"),
    ("works:delete", "Delete Works", "Delete works from catalog", "catalog", True),
    ("works:list", "List Works", "View works in catalog", "catalog"),
    ("works:import", "Import Works", "Import works from external sources", "catalog"),
    ("works:export", "Export Works", "Export work data", "catalog"),
    
    # Songwriter Management
    ("songwriters:create", "Create Songwriters", "Add new songwriters", "catalog"),
    ("songwriters:read", "View Songwriters", "View songwriter profiles", "catalog"),
    ("songwriters:update", "Edit Songwriters", "Update songwriter information", "catalog"),
    ("songwriters:delete", "Delete Songwriters", "Remove songwriters", "catalog", True),
    ("songwriters:list", "List Songwriters", "View songwriter directory", "catalog"),
    
    # Recording Management
    ("recordings:create", "Create Recordings", "Add new recordings", "catalog"),
    ("recordings:read", "View Recordings", "View recording details", "catalog"),
    ("recordings:update", "Edit Recordings", "Update recording information", "catalog"),
    ("recordings:delete", "Delete Recordings", "Delete recordings", "catalog", True),
    ("recordings:list", "List Recordings", "View recordings catalog", "catalog"),
    
    # User Management
    ("users:create", "Create Users", "Add new users to publisher", "user_management"),
    ("users:read", "View Users", "View user profiles and information", "user_management"),
    ("users:update", "Edit Users", "Update user information", "user_management"),
    ("users:delete", "Delete Users", "Remove users from publisher", "user_management", True),
    ("users:list", "List Users", "View user directory", "user_management"),
    ("users:invite", "Invite Users", "Send user invitations", "user_management"),
    
    # Role Management
    ("roles:create", "Create Roles", "Create new user roles", "user_management"),
    ("roles:read", "View Roles", "View role definitions", "user_management"),
    ("roles:update", "Edit Roles", "Modify role permissions", "user_management"),
    ("roles:delete", "Delete Roles", "Remove custom roles", "user_management", True),
    ("roles:list", "List Roles", "View available roles", "user_management"),
    ("roles:assign", "Assign Roles", "Assign roles to users", "user_management"),
    
    # Reporting
    ("reports:create", "Create Reports", "Generate custom reports", "reporting"),
    ("reports:read", "View Reports", "Access existing reports", "reporting"),
    ("reports:export", "Export Reports", "Export report data", "reporting"),
    ("reports:schedule", "Schedule Reports", "Set up automated reports", "reporting"),
    
    # Financial
    ("royalties:read", "View Royalties", "Access royalty information", "financial"),
    ("royalties:calculate", "Calculate Royalties", "Run royalty calculations", "financial"),
    ("royalties:distribute", "Distribute Royalties", "Process royalty payments", "financial"),
    ("statements:read", "View Statements", "Access financial statements", "financial"),
    ("statements:generate", "Generate Statements", "Create financial statements", "financial"),
    
    # Settings and Administration
    ("settings:read", "View Settings", "View publisher settings", "settings"),
    ("settings:update", "Edit Settings", "Modify publisher settings", "settings"),
    ("settings:admin", "Admin Settings", "Access administrative settings", "admin", True, True),
    
    # Integrations
    ("integrations:read", "View Integrations", "View integration status", "integrations"),
    ("integrations:configure", "Configure Integrations", "Set up external integrations", "integrations"),
    ("integrations:sync", "Sync Data", "Trigger data synchronization", "integrations"),
    
    # API Access
    ("api:read", "API Read Access", "Read data via API", "api"),
    ("api:write", "API Write Access", "Create/update data via API", "api"),
    ("api:admin", "API Admin Access", "Full API access including admin operations", "api", True),
]


def create_system_permissions() -> List[Permission]:
    """
    Create all standard system permissions.
    
    Returns:
        List[Permission]: List of system permission objects
    """
    permissions = []
    
    for perm_data in SYSTEM_PERMISSIONS:
        name = perm_data[0]
        display_name = perm_data[1]
        description = perm_data[2]
        category = perm_data[3]
        is_dangerous = perm_data[4] if len(perm_data) > 4 else False
        requires_admin = perm_data[5] if len(perm_data) > 5 else False
        
        permission = Permission.create_permission(
            name=name,
            display_name=display_name,
            description=description,
            category=category,
            is_dangerous=is_dangerous,
            requires_admin=requires_admin
        )
        permissions.append(permission)
    
    return permissions