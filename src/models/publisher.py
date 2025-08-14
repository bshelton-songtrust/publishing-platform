"""Publisher model for multi-tenant publishing platform."""

import uuid
from sqlalchemy import (
    Column, String, CheckConstraint, Index, UUID, Text,
    ForeignKey
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from .base import TimestampMixin
from src.core.database import Base


class Publisher(Base, TimestampMixin):
    """
    Publisher model representing a music publishing company or organization.
    
    This is the primary tenant entity in the multi-tenant architecture.
    All catalog entities (works, recordings, songwriters) belong to a publisher
    for data isolation and business context.
    
    The Publisher model supports various types of publishing organizations:
    - Enterprise: Large publishing companies with complex catalogs
    - Professional: Mid-size publishers with established catalogs  
    - Platform: Digital platforms aggregating multiple publishers
    - Boutique: Small independent publishers and individuals
    
    Business models supported:
    - Traditional: Traditional publishing with PRO relationships
    - Platform: Digital platform-based revenue models
    - Hybrid: Mix of traditional and digital approaches
    """
    
    __tablename__ = "publishers"
    
    # Core Identity Fields
    id = Column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4,
        comment="Primary key UUID"
    )
    
    name = Column(
        String(255), 
        nullable=False,
        comment="Publisher organization name (e.g. 'Sony Music Publishing')"
    )
    
    subdomain = Column(
        String(100), 
        unique=True, 
        nullable=False,
        comment="Unique subdomain identifier for tenant isolation (e.g. 'sony-music')"
    )
    
    publisher_type = Column(
        String(20),
        nullable=False,
        default="professional",
        comment="Publisher organization type: enterprise, professional, platform, boutique"
    )
    
    business_model = Column(
        String(20),
        nullable=False,
        default="traditional", 
        comment="Primary business model: traditional, platform, hybrid"
    )
    
    status = Column(
        String(20), 
        default="active",
        nullable=False,
        comment="Publisher operational status: active, suspended, archived, trial"
    )
    
    # Publisher-Specific Business Fields
    branding = Column(
        JSONB,
        default=dict,
        comment="Publisher branding configuration including logos, colors, themes"
    )
    
    tax_id = Column(
        String(50),
        nullable=True,
        comment="Tax identification number (EIN, VAT, etc.)"
    )
    
    business_license = Column(
        String(100),
        nullable=True,
        comment="Business license or registration number"
    )
    
    primary_contact_email = Column(
        String(255),
        nullable=False,
        comment="Primary business contact email address"
    )
    
    support_email = Column(
        String(255),
        nullable=True,
        comment="Customer/writer support email address"
    )
    
    business_address = Column(
        JSONB,
        default=dict,
        comment="Complete business address information in JSON format"
    )
    
    # Configuration and Metadata
    settings = Column(
        JSONB, 
        default=dict,
        comment="Publisher-specific configuration settings and preferences"
    )
    
    additional_data = Column(
        JSONB, 
        default=dict,
        comment="Additional flexible metadata in JSON format"
    )

    # Table-level constraints and indexes
    __table_args__ = (
        # Check constraints for enum-like fields
        CheckConstraint(
            "publisher_type IN ('enterprise', 'professional', 'platform', 'boutique')",
            name="valid_publisher_type"
        ),
        CheckConstraint(
            "business_model IN ('traditional', 'platform', 'hybrid')",
            name="valid_business_model"
        ),
        CheckConstraint(
            "status IN ('active', 'suspended', 'archived', 'trial')",
            name="valid_publisher_status"
        ),
        
        # Business rules constraints
        CheckConstraint(
            "length(subdomain) >= 3",
            name="subdomain_min_length"
        ),
        CheckConstraint(
            "subdomain ~ '^[a-z0-9-]+$'",
            name="subdomain_format"
        ),
        CheckConstraint(
            "primary_contact_email ~ '^[^@]+@[^@]+\.[^@]+$'",
            name="valid_primary_email_format"
        ),
        CheckConstraint(
            "support_email IS NULL OR support_email ~ '^[^@]+@[^@]+\.[^@]+$'",
            name="valid_support_email_format"
        ),
        
        # Performance indexes
        Index("idx_publishers_subdomain", "subdomain"),
        Index("idx_publishers_status", "status"),
        Index("idx_publishers_type", "publisher_type"),
        Index("idx_publishers_business_model", "business_model"),
        Index("idx_publishers_primary_contact", "primary_contact_email"),
        Index("idx_publishers_created_at", "created_at"),
        
        # Composite indexes for common query patterns
        Index("idx_publishers_type_status", "publisher_type", "status"),
        Index("idx_publishers_status_created", "status", "created_at"),
    )

    # Relationships
    account = relationship("Account", back_populates="publisher", uselist=False)
    roles = relationship("Role", back_populates="publisher", lazy="dynamic")
    user_relationships = relationship("UserPublisher", back_populates="publisher", lazy="dynamic")
    works = relationship("Work", back_populates="publisher", lazy="dynamic")
    recordings = relationship("Recording", back_populates="publisher", lazy="dynamic")
    songwriters = relationship("Songwriter", back_populates="publisher", lazy="dynamic")
    service_accounts = relationship("ServiceAccount", back_populates="publisher", lazy="dynamic")
    personal_access_tokens = relationship("PersonalAccessToken", back_populates="publisher", lazy="dynamic")

    def __init__(self, **kwargs):
        """
        Initialize Publisher with default configurations.
        
        Sets up default branding, business address structure,
        and settings for new publisher instances.
        """
        super().__init__(**kwargs)
        
        # Initialize default branding structure if not provided
        if not self.branding:
            self.branding = {
                "logo_url": None,
                "primary_color": "#1a1a1a",
                "secondary_color": "#ffffff", 
                "accent_color": "#0066cc",
                "theme": "light",
                "custom_css": None
            }
        
        # Initialize default business address structure if not provided
        if not self.business_address:
            self.business_address = {
                "street_address": None,
                "city": None,
                "state_province": None,
                "postal_code": None,
                "country": None,
                "timezone": "UTC"
            }
        
        # Initialize default settings if not provided
        if not self.settings:
            self.settings = {
                "currency": "USD",
                "date_format": "YYYY-MM-DD",
                "time_format": "24h",
                "language": "en",
                "notifications": {
                    "email_enabled": True,
                    "sms_enabled": False,
                    "push_enabled": True
                },
                "integrations": {
                    "pro_sync_enabled": False,
                    "dsp_reporting_enabled": False,
                    "accounting_sync_enabled": False
                },
                "security": {
                    "require_2fa": False,
                    "session_timeout_minutes": 480,
                    "password_policy": "standard"
                }
            }

    @property
    def is_active(self) -> bool:
        """Check if publisher is in active status."""
        return self.status == "active"
    
    @property
    def is_trial(self) -> bool:
        """Check if publisher is in trial status."""
        return self.status == "trial"
    
    @property
    def is_suspended(self) -> bool:
        """Check if publisher is suspended."""
        return self.status == "suspended"
    
    @property
    def display_name(self) -> str:
        """Get display name for UI purposes."""
        return self.name
    
    @property
    def tenant_id(self) -> uuid.UUID:
        """
        Alias for id to maintain compatibility with multi-tenant patterns.
        
        In the publishing platform, the publisher IS the tenant,
        so tenant_id and publisher id are the same.
        """
        return self.id

    def get_branding_config(self) -> dict:
        """
        Get complete branding configuration with fallbacks.
        
        Returns:
            dict: Complete branding configuration with default values
        """
        default_branding = {
            "logo_url": None,
            "primary_color": "#1a1a1a",
            "secondary_color": "#ffffff",
            "accent_color": "#0066cc", 
            "theme": "light",
            "custom_css": None
        }
        
        # Merge with stored branding, preferring stored values
        return {**default_branding, **(self.branding or {})}

    def get_business_address(self) -> dict:
        """
        Get formatted business address.
        
        Returns:
            dict: Complete business address information
        """
        return self.business_address or {}

    def get_contact_info(self) -> dict:
        """
        Get all contact information for the publisher.
        
        Returns:
            dict: Contact information including emails and address
        """
        return {
            "primary_email": self.primary_contact_email,
            "support_email": self.support_email,
            "business_address": self.get_business_address()
        }

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
            
        # Support dot notation for nested keys (e.g., "notifications.email_enabled")
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

    def can_access_feature(self, feature: str) -> bool:
        """
        Check if publisher can access a specific feature based on type and status.
        
        Args:
            feature: Feature name to check
            
        Returns:
            bool: True if feature is accessible
        """
        if not self.is_active and not self.is_trial:
            return False
            
        # Feature access based on publisher type
        feature_matrix = {
            "boutique": ["basic_catalog", "basic_royalties", "basic_reporting"],
            "professional": ["basic_catalog", "basic_royalties", "basic_reporting", 
                           "advanced_reporting", "bulk_operations", "api_access"],
            "platform": ["basic_catalog", "basic_royalties", "basic_reporting",
                        "advanced_reporting", "bulk_operations", "api_access",
                        "multi_publisher", "white_label"],
            "enterprise": ["basic_catalog", "basic_royalties", "basic_reporting",
                          "advanced_reporting", "bulk_operations", "api_access", 
                          "multi_publisher", "white_label", "custom_integrations",
                          "dedicated_support"]
        }
        
        allowed_features = feature_matrix.get(self.publisher_type, [])
        return feature in allowed_features

    def __repr__(self) -> str:
        """String representation of the Publisher."""
        return (f"<Publisher(id={self.id}, name='{self.name}', "
                f"subdomain='{self.subdomain}', type='{self.publisher_type}', "
                f"status='{self.status}')>")

    def __str__(self) -> str:
        """Human-readable string representation."""
        return f"{self.name} ({self.publisher_type.title()} Publisher)"