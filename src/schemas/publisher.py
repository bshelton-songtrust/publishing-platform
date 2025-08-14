"""Publisher-related Pydantic schemas."""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from uuid import UUID
from decimal import Decimal

from pydantic import Field, field_validator, EmailStr

from .base import BaseSchema, JSONAPIResponse, JSONAPICollectionResponse, Relationship


# Core Publisher Schemas

class PublisherBrandingAttributes(BaseSchema):
    """Attributes for publisher branding configuration."""
    
    logo_url: Optional[str] = Field(None, description="URL to publisher logo")
    primary_color: str = Field("#1a1a1a", description="Primary brand color (hex)")
    secondary_color: str = Field("#ffffff", description="Secondary brand color (hex)")
    accent_color: str = Field("#0066cc", description="Accent brand color (hex)")
    theme: str = Field("light", description="UI theme preference")
    custom_css: Optional[str] = Field(None, description="Custom CSS overrides")
    
    @field_validator("primary_color", "secondary_color", "accent_color")
    @classmethod
    def validate_color_format(cls, v: str) -> str:
        if not v.startswith("#") or len(v) != 7:
            raise ValueError("Color must be a valid hex color (e.g., #ffffff)")
        return v.lower()
    
    @field_validator("theme")
    @classmethod
    def validate_theme(cls, v: str) -> str:
        valid_themes = {"light", "dark", "auto"}
        if v not in valid_themes:
            raise ValueError(f"Theme must be one of: {valid_themes}")
        return v


class PublisherBusinessAddressAttributes(BaseSchema):
    """Attributes for publisher business address."""
    
    street_address: Optional[str] = Field(None, max_length=500, description="Street address")
    city: Optional[str] = Field(None, max_length=100, description="City")
    state_province: Optional[str] = Field(None, max_length=100, description="State or province")
    postal_code: Optional[str] = Field(None, max_length=20, description="Postal/ZIP code")
    country: Optional[str] = Field(None, max_length=2, description="Country code (ISO 3166-1)")
    timezone: str = Field("UTC", description="Publisher timezone")
    
    @field_validator("country")
    @classmethod
    def validate_country_code(cls, v: Optional[str]) -> Optional[str]:
        if v and len(v) != 2:
            raise ValueError("Country must be 2-letter ISO 3166-1 code")
        return v.upper() if v else v


class PublisherSettingsAttributes(BaseSchema):
    """Attributes for publisher configuration settings."""
    
    currency: str = Field("USD", max_length=3, description="Primary currency (ISO 4217)")
    date_format: str = Field("YYYY-MM-DD", description="Preferred date format")
    time_format: str = Field("24h", description="Time format preference")
    language: str = Field("en", max_length=5, description="Primary language (ISO 639-1)")
    
    notifications: Dict[str, bool] = Field(
        default_factory=lambda: {
            "email_enabled": True,
            "sms_enabled": False,
            "push_enabled": True
        },
        description="Notification preferences"
    )
    
    integrations: Dict[str, bool] = Field(
        default_factory=lambda: {
            "pro_sync_enabled": False,
            "dsp_reporting_enabled": False,
            "accounting_sync_enabled": False
        },
        description="Integration settings"
    )
    
    security: Dict[str, Union[bool, int, str]] = Field(
        default_factory=lambda: {
            "require_2fa": False,
            "session_timeout_minutes": 480,
            "password_policy": "standard"
        },
        description="Security settings"
    )
    
    @field_validator("currency")
    @classmethod
    def validate_currency_code(cls, v: str) -> str:
        if len(v) != 3:
            raise ValueError("Currency must be 3-letter ISO 4217 code")
        return v.upper()
    
    @field_validator("time_format")
    @classmethod
    def validate_time_format(cls, v: str) -> str:
        valid_formats = {"12h", "24h"}
        if v not in valid_formats:
            raise ValueError(f"Time format must be one of: {valid_formats}")
        return v


class PublisherAttributes(BaseSchema):
    """Attributes for publisher resource."""
    
    # Core identity
    name: str = Field(min_length=1, max_length=255, description="Publisher organization name")
    subdomain: str = Field(min_length=3, max_length=100, description="Unique subdomain identifier")
    publisher_type: str = Field(
        "professional",
        description="Publisher type: enterprise, professional, platform, boutique"
    )
    business_model: str = Field(
        "traditional", 
        description="Business model: traditional, platform, hybrid"
    )
    status: str = Field("active", description="Publisher status: active, suspended, archived, trial")
    
    # Business information
    tax_id: Optional[str] = Field(None, max_length=50, description="Tax identification number")
    business_license: Optional[str] = Field(None, max_length=100, description="Business license number")
    primary_contact_email: EmailStr = Field(description="Primary business contact email")
    support_email: Optional[EmailStr] = Field(None, description="Customer support email")
    
    # Configuration
    branding: PublisherBrandingAttributes = Field(
        default_factory=PublisherBrandingAttributes,
        description="Publisher branding configuration"
    )
    business_address: PublisherBusinessAddressAttributes = Field(
        default_factory=PublisherBusinessAddressAttributes,
        description="Business address information"
    )
    settings: PublisherSettingsAttributes = Field(
        default_factory=PublisherSettingsAttributes,
        description="Publisher configuration settings"
    )
    additional_data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional flexible metadata"
    )
    
    # Audit fields (read-only)
    created_at: Optional[datetime] = Field(None, description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")
    
    @field_validator("subdomain")
    @classmethod
    def validate_subdomain(cls, v: str) -> str:
        import re
        if not re.match(r"^[a-z0-9-]+$", v.lower()):
            raise ValueError("Subdomain can only contain lowercase letters, numbers, and hyphens")
        return v.lower()
    
    @field_validator("publisher_type")
    @classmethod
    def validate_publisher_type(cls, v: str) -> str:
        valid_types = {"enterprise", "professional", "platform", "boutique"}
        if v not in valid_types:
            raise ValueError(f"Publisher type must be one of: {valid_types}")
        return v
    
    @field_validator("business_model")
    @classmethod
    def validate_business_model(cls, v: str) -> str:
        valid_models = {"traditional", "platform", "hybrid"}
        if v not in valid_models:
            raise ValueError(f"Business model must be one of: {valid_models}")
        return v
    
    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        valid_statuses = {"active", "suspended", "archived", "trial"}
        if v not in valid_statuses:
            raise ValueError(f"Status must be one of: {valid_statuses}")
        return v


class PublisherRelationships(BaseSchema):
    """Relationships for publisher resource."""
    
    account: Optional[Relationship] = Field(None, description="Associated account")
    users: Optional[Relationship] = Field(None, description="Associated users")
    roles: Optional[Relationship] = Field(None, description="Publisher roles")
    works: Optional[Relationship] = Field(None, description="Catalog works")
    recordings: Optional[Relationship] = Field(None, description="Catalog recordings")
    songwriters: Optional[Relationship] = Field(None, description="Associated songwriters")


class PublisherResource(BaseSchema):
    """JSON:API resource for publisher."""
    
    type: str = Field("publisher", description="Resource type")
    id: UUID = Field(description="Publisher UUID")
    attributes: PublisherAttributes
    relationships: Optional[PublisherRelationships] = None


# Request/Response Schemas

class PublisherCreateRequest(BaseSchema):
    """Request schema for creating a publisher."""
    
    data: PublisherResource = Field(description="Publisher data to create")


class PublisherUpdateRequest(BaseSchema):
    """Request schema for updating a publisher."""
    
    data: PublisherResource = Field(description="Publisher data to update")


class PublisherResponse(JSONAPIResponse):
    """Response schema for single publisher."""
    
    data: PublisherResource = Field(description="Publisher resource")


class PublisherCollectionResponse(JSONAPICollectionResponse):
    """Response schema for publisher collection."""
    
    data: List[PublisherResource] = Field(description="Publisher resources")


# Settings Management Schemas

class PublisherSettingsRequest(BaseSchema):
    """Request schema for updating publisher settings."""
    
    data: Dict[str, Any] = Field(description="Settings updates using dot notation")


class PublisherSettingsResponse(BaseSchema):
    """Response schema for publisher settings."""
    
    data: PublisherSettingsAttributes = Field(description="Complete publisher settings")


# Branding Management Schemas

class PublisherBrandingRequest(BaseSchema):
    """Request schema for updating publisher branding."""
    
    data: PublisherBrandingAttributes = Field(description="Branding configuration updates")


class PublisherBrandingResponse(BaseSchema):
    """Response schema for publisher branding."""
    
    data: PublisherBrandingAttributes = Field(description="Complete branding configuration")


# User Management Schemas

class PublisherUserAttributes(BaseSchema):
    """Attributes for publisher user relationship."""
    
    # User info
    user_id: UUID = Field(description="User UUID")
    email: EmailStr = Field(description="User email address")
    first_name: str = Field(description="User first name")
    last_name: str = Field(description="User last name")
    full_name: Optional[str] = Field(None, description="User full name")
    status: str = Field(description="User account status")
    is_verified: bool = Field(description="Whether user email is verified")
    last_login_at: Optional[datetime] = Field(None, description="Last login timestamp")
    
    # Publisher relationship info
    role_name: str = Field(description="User role within publisher")
    relationship_status: str = Field(description="Relationship status: invited, active, revoked")
    is_primary: bool = Field(description="Whether this is user's primary publisher")
    joined_at: Optional[datetime] = Field(None, description="When user joined publisher")
    last_accessed_at: Optional[datetime] = Field(None, description="Last access timestamp")
    access_count: int = Field(0, description="Number of times user accessed publisher")
    permissions: List[str] = Field(default_factory=list, description="User permissions")


class PublisherUserResource(BaseSchema):
    """JSON:API resource for publisher user."""
    
    type: str = Field("publisher_user", description="Resource type")
    id: UUID = Field(description="User-publisher relationship UUID")
    attributes: PublisherUserAttributes


class PublisherUserInviteRequest(BaseSchema):
    """Request schema for inviting user to publisher."""
    
    email: EmailStr = Field(description="Email address to invite")
    role_id: UUID = Field(description="Role UUID to assign")
    is_primary: bool = Field(False, description="Whether this should be user's primary publisher")
    send_email: bool = Field(True, description="Whether to send invitation email")
    message: Optional[str] = Field(None, max_length=500, description="Custom invitation message")


class PublisherUserRoleUpdateRequest(BaseSchema):
    """Request schema for updating user role."""
    
    role_id: UUID = Field(description="New role UUID to assign")


class PublisherUserCollectionResponse(JSONAPICollectionResponse):
    """Response schema for publisher users collection."""
    
    data: List[PublisherUserResource] = Field(description="Publisher user resources")


# Account Management Schemas

class PublisherAccountAttributes(BaseSchema):
    """Attributes for publisher account information."""
    
    # Account details
    plan_type: str = Field(description="Account plan: starter, professional, enterprise")
    billing_cycle: str = Field(description="Billing cycle: monthly, yearly")
    status: str = Field(description="Account status: active, trial, cancelled, suspended")
    
    # Subscription details
    trial_ends_at: Optional[datetime] = Field(None, description="Trial end date")
    next_billing_date: Optional[datetime] = Field(None, description="Next billing date")
    monthly_price: Decimal = Field(description="Monthly subscription price")
    yearly_price: Optional[Decimal] = Field(None, description="Yearly subscription price")
    
    # Usage and limits
    seats_licensed: int = Field(description="Number of licensed user seats")
    seats_used: int = Field(description="Number of seats currently in use")
    storage_limit_gb: Optional[int] = Field(None, description="Storage limit in GB")
    storage_used_gb: Decimal = Field(Decimal("0"), description="Storage used in GB")
    
    # Features
    features_enabled: List[str] = Field(default_factory=list, description="Enabled features")
    api_calls_limit: Optional[int] = Field(None, description="Monthly API calls limit")
    api_calls_used: int = Field(0, description="API calls used this month")
    
    # Billing information
    payment_method: Optional[str] = Field(None, description="Payment method type")
    billing_contact_email: Optional[EmailStr] = Field(None, description="Billing contact email")
    
    # Audit fields
    created_at: Optional[datetime] = Field(None, description="Account creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")


class PublisherAccountResource(BaseSchema):
    """JSON:API resource for publisher account."""
    
    type: str = Field("publisher_account", description="Resource type")
    id: UUID = Field(description="Account UUID")
    attributes: PublisherAccountAttributes


class PublisherAccountResponse(JSONAPIResponse):
    """Response schema for publisher account."""
    
    data: PublisherAccountResource = Field(description="Publisher account resource")


class PublisherPlanChangeRequest(BaseSchema):
    """Request schema for changing subscription plan."""
    
    plan_type: str = Field(description="New plan type: starter, professional, enterprise")
    billing_cycle: str = Field(description="Billing cycle: monthly, yearly")
    seats_licensed: Optional[int] = Field(None, description="Number of seats to license")
    effective_date: Optional[str] = Field(None, description="When change should take effect")
    
    @field_validator("plan_type")
    @classmethod
    def validate_plan_type(cls, v: str) -> str:
        valid_plans = {"starter", "professional", "enterprise"}
        if v not in valid_plans:
            raise ValueError(f"Plan type must be one of: {valid_plans}")
        return v
    
    @field_validator("billing_cycle")
    @classmethod
    def validate_billing_cycle(cls, v: str) -> str:
        valid_cycles = {"monthly", "yearly"}
        if v not in valid_cycles:
            raise ValueError(f"Billing cycle must be one of: {valid_cycles}")
        return v


class PublisherUsageStatsAttributes(BaseSchema):
    """Attributes for publisher usage statistics."""
    
    # Current period usage
    current_month: str = Field(description="Current month (YYYY-MM)")
    seats_used: int = Field(description="Current seats in use")
    storage_used_gb: Decimal = Field(description="Storage used in GB")
    api_calls_used: int = Field(description="API calls made this month")
    
    # Catalog statistics
    total_works: int = Field(0, description="Total works in catalog")
    total_recordings: int = Field(0, description="Total recordings in catalog")
    total_songwriters: int = Field(0, description="Total songwriters")
    
    # Activity statistics
    active_users_30d: int = Field(0, description="Active users in last 30 days")
    new_works_30d: int = Field(0, description="New works created in last 30 days")
    updated_works_30d: int = Field(0, description="Works updated in last 30 days")
    
    # Limits
    seats_limit: int = Field(description="Licensed seat limit")
    storage_limit_gb: Optional[int] = Field(None, description="Storage limit in GB")
    api_calls_limit: Optional[int] = Field(None, description="Monthly API calls limit")
    
    # Usage percentages
    seats_usage_percent: Decimal = Field(description="Seat usage percentage")
    storage_usage_percent: Optional[Decimal] = Field(None, description="Storage usage percentage")
    api_calls_usage_percent: Optional[Decimal] = Field(None, description="API usage percentage")


class PublisherUsageStatsResponse(BaseSchema):
    """Response schema for publisher usage statistics."""
    
    data: PublisherUsageStatsAttributes = Field(description="Usage statistics")


# Filter and Search Schemas

class PublisherSearchFilters(BaseSchema):
    """Search filters for publishers."""
    
    q: Optional[str] = Field(None, max_length=500, description="Full-text search query")
    name: Optional[str] = Field(None, description="Publisher name filter (partial match)")
    subdomain: Optional[str] = Field(None, description="Subdomain filter (partial match)")
    publisher_type: Optional[str] = Field(None, description="Publisher type filter")
    business_model: Optional[str] = Field(None, description="Business model filter")
    status: Optional[List[str]] = Field(None, description="Status filter")
    
    # Date range filters
    created_date_gte: Optional[str] = Field(None, description="Created on or after date")
    created_date_lte: Optional[str] = Field(None, description="Created on or before date")
    
    @field_validator("publisher_type")
    @classmethod
    def validate_publisher_type_filter(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        valid_types = {"enterprise", "professional", "platform", "boutique"}
        if v not in valid_types:
            raise ValueError(f"Publisher type must be one of: {valid_types}")
        return v
    
    @field_validator("business_model")
    @classmethod
    def validate_business_model_filter(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        valid_models = {"traditional", "platform", "hybrid"}
        if v not in valid_models:
            raise ValueError(f"Business model must be one of: {valid_models}")
        return v
    
    @field_validator("status")
    @classmethod
    def validate_status_list(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return v
        valid_statuses = {"active", "suspended", "archived", "trial"}
        for status in v:
            if status not in valid_statuses:
                raise ValueError(f"Each status must be one of: {valid_statuses}")
        return v