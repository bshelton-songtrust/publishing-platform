"""Songwriter-related Pydantic schemas."""

from datetime import date, datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import Field, field_validator

from .base import BaseSchema, JSONAPIResponse, JSONAPICollectionResponse


class SongwriterAttributes(BaseSchema):
    """Attributes for songwriter resource."""
    
    # Personal information
    first_name: str = Field(min_length=1, max_length=100, description="First name")
    last_name: str = Field(min_length=1, max_length=100, description="Last name")
    full_name: Optional[str] = Field(None, description="Computed full name")
    stage_name: Optional[str] = Field(None, max_length=255, description="Stage/professional name")
    
    # Industry identifiers
    ipi: Optional[str] = Field(None, max_length=15, description="IPI number")
    isni: Optional[str] = Field(None, max_length=16, description="ISNI number")
    
    # Contact information
    email: Optional[str] = Field(None, max_length=255, description="Email address")
    phone: Optional[str] = Field(None, max_length=50, description="Phone number")
    address: Dict[str, str] = Field(
        default_factory=dict, 
        description="Address: street, city, state, country, postal_code"
    )
    
    # Personal details
    birth_date: Optional[date] = Field(None, description="Date of birth")
    birth_country: Optional[str] = Field(None, description="Country of birth (ISO 3166-1 alpha-2)")
    nationality: Optional[str] = Field(None, description="Nationality (ISO 3166-1 alpha-2)")
    gender: Optional[str] = Field(None, max_length=20, description="Gender identity")
    
    # Professional status
    status: str = Field("active", description="Status: active, inactive, deceased")
    deceased_date: Optional[date] = Field(None, description="Date of death")
    
    # Biography and additional info
    biography: Optional[str] = Field(None, description="Biography or description")
    website: Optional[str] = Field(None, max_length=255, description="Website URL")
    social_media: Dict[str, str] = Field(
        default_factory=dict, description="Social media profiles"
    )
    
    # Audit fields (read-only)
    created_at: Optional[datetime] = Field(None, description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")
    
    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        valid_statuses = {"active", "inactive", "deceased"}
        if v not in valid_statuses:
            raise ValueError(f"Status must be one of: {valid_statuses}")
        return v
    
    @field_validator("birth_country", "nationality")
    @classmethod
    def validate_country_code(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        
        if len(v) != 2:
            raise ValueError("Country code must be 2 characters (ISO 3166-1 alpha-2)")
        return v.upper()
    
    @field_validator("email")
    @classmethod
    def validate_email_format(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        
        # Basic email validation
        import re
        email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        if not re.match(email_pattern, v):
            raise ValueError("Invalid email format")
        return v.lower()
    
    @field_validator("website")
    @classmethod
    def validate_website_url(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        
        # Basic URL validation
        if not v.startswith(("http://", "https://")):
            v = f"https://{v}"
        return v


class SongwriterResource(BaseSchema):
    """JSON:API resource for songwriter."""
    
    type: str = Field("songwriter", description="Resource type")
    id: UUID = Field(description="Songwriter UUID")
    attributes: SongwriterAttributes


class SongwriterCreateRequest(BaseSchema):
    """Request schema for creating a songwriter."""
    
    data: SongwriterResource = Field(description="Songwriter data to create")


class SongwriterUpdateRequest(BaseSchema):
    """Request schema for updating a songwriter."""
    
    data: SongwriterResource = Field(description="Songwriter data to update")


class SongwriterPatchRequest(BaseSchema):
    """Request schema for patching a songwriter (partial update)."""
    
    data: SongwriterResource = Field(description="Songwriter data to patch")


class SongwriterResponse(JSONAPIResponse):
    """Response schema for single songwriter."""
    
    data: SongwriterResource = Field(description="Songwriter resource")


class SongwriterCollectionResponse(JSONAPICollectionResponse):
    """Response schema for songwriter collection."""
    
    data: List[SongwriterResource] = Field(description="Songwriter resources")


class SongwriterSearchFilters(BaseSchema):
    """Search filters for songwriters."""
    
    q: Optional[str] = Field(None, max_length=500, description="Full-text search query")
    name: Optional[str] = Field(None, description="Name filter (partial match)")
    stage_name: Optional[str] = Field(None, description="Stage name filter")
    ipi: Optional[str] = Field(None, description="IPI number filter")
    isni: Optional[str] = Field(None, description="ISNI number filter")
    email: Optional[str] = Field(None, description="Email filter")
    status: Optional[List[str]] = Field(None, description="Status filter")
    nationality: Optional[str] = Field(None, description="Nationality filter")
    birth_country: Optional[str] = Field(None, description="Birth country filter")
    
    # Date range filters
    birth_date_gte: Optional[date] = Field(None, description="Born on or after date")
    birth_date_lte: Optional[date] = Field(None, description="Born on or before date")
    created_date_gte: Optional[str] = Field(None, description="Created on or after date")
    created_date_lte: Optional[str] = Field(None, description="Created on or before date")
    
    @field_validator("status")
    @classmethod
    def validate_status_list(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return v
        
        valid_statuses = {"active", "inactive", "deceased"}
        for status in v:
            if status not in valid_statuses:
                raise ValueError(f"Each status must be one of: {valid_statuses}")
        return v


class BulkSongwriterOperation(BaseSchema):
    """Schema for bulk songwriter operations."""
    
    operation: str = Field(description="Operation type: create, update, delete")
    data: List[SongwriterResource] = Field(description="Songwriter resources for operation")
    
    @field_validator("operation")
    @classmethod
    def validate_operation(cls, v: str) -> str:
        valid_operations = {"create", "update", "delete"}
        if v not in valid_operations:
            raise ValueError(f"Operation must be one of: {valid_operations}")
        return v


class BulkSongwriterResponse(BaseSchema):
    """Response schema for bulk songwriter operations."""
    
    operation: str = Field(description="Operation type performed")
    total_items: int = Field(description="Total items in the operation")
    successful_items: int = Field(description="Successfully processed items")
    failed_items: int = Field(description="Failed items")
    
    results: List[Dict[str, Any]] = Field(description="Detailed results per item")
    errors: List[Dict[str, Any]] = Field(default_factory=list, description="Error details")
    
    meta: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")