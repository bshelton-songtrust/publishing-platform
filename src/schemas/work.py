"""Work-related Pydantic schemas."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import Field, field_validator

from .base import BaseSchema, JSONAPIResponse, JSONAPICollectionResponse, Relationship


class WorkWriterAttributes(BaseSchema):
    """Attributes for work writer relationship."""
    
    songwriter_id: UUID = Field(description="Songwriter UUID")
    role: str = Field(description="Writer role: composer, lyricist, composer_lyricist")
    contribution_percentage: Optional[Decimal] = Field(
        None, ge=0, le=100, description="Contribution percentage (0-100)"
    )
    is_primary: bool = Field(False, description="Whether this is the primary writer for this role")
    credit_name: Optional[str] = Field(None, max_length=255, description="Credit name override")
    publishing_share: Optional[Decimal] = Field(
        None, ge=0, le=100, description="Publishing share percentage (0-100)"
    )
    writer_share: Optional[Decimal] = Field(
        None, ge=0, le=100, description="Writer share percentage (0-100)"
    )
    contribution_description: Optional[str] = Field(
        None, description="Description of the contribution"
    )
    
    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        valid_roles = {"composer", "lyricist", "composer_lyricist"}
        if v not in valid_roles:
            raise ValueError(f"Role must be one of: {valid_roles}")
        return v


class WorkWriterResource(BaseSchema):
    """JSON:API resource for work writer."""
    
    type: str = Field("work_writer", description="Resource type")
    id: UUID = Field(description="Work writer UUID")
    attributes: WorkWriterAttributes


class WorkAttributes(BaseSchema):
    """Attributes for musical work resource."""
    
    # Core identification
    title: str = Field(min_length=1, max_length=500, description="Work title")
    iswc: Optional[str] = Field(None, description="International Standard Musical Work Code")
    alternate_titles: List[str] = Field(default_factory=list, description="Alternate titles")
    
    # Classification
    genre: Optional[str] = Field(None, max_length=100, description="Primary genre")
    subgenre: Optional[str] = Field(None, max_length=100, description="Subgenre")
    language: Optional[str] = Field(None, description="Primary language (ISO 639-1)")
    
    # Technical details
    duration: Optional[int] = Field(None, gt=0, description="Duration in seconds")
    tempo: Optional[int] = Field(None, ge=20, le=300, description="Tempo in BPM")
    key_signature: Optional[str] = Field(None, max_length=10, description="Key signature")
    time_signature: Optional[str] = Field(None, max_length=10, description="Time signature")
    
    # Registration and status
    registration_status: str = Field(
        "draft", description="Registration status"
    )
    registration_date: Optional[str] = Field(None, description="Registration date")
    publication_date: Optional[str] = Field(None, description="Publication date")
    
    # Content flags
    is_instrumental: bool = Field(False, description="Whether work is instrumental")
    has_lyrics: bool = Field(True, description="Whether work has lyrics")
    
    # Rights information
    rights_society: Optional[str] = Field(None, max_length=100, description="Primary PRO")
    rights_status: Optional[str] = Field(None, max_length=50, description="Rights status")
    
    # Additional information
    description: Optional[str] = Field(None, description="Work description")
    tags: List[str] = Field(default_factory=list, description="Tags for categorization")
    external_ids: Dict[str, str] = Field(
        default_factory=dict, description="External system identifiers"
    )
    
    # Version information
    original_work_id: Optional[UUID] = Field(
        None, description="Original work if this is a derivative"
    )
    version_info: Dict[str, Any] = Field(
        default_factory=dict, description="Version metadata"
    )
    
    # Writers (embedded for convenience)
    writers: List[WorkWriterAttributes] = Field(
        default_factory=list, description="Work writers"
    )
    
    # Audit fields (read-only)
    created_at: Optional[datetime] = Field(None, description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")
    
    @field_validator("iswc")
    @classmethod
    def validate_iswc(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        
        # ISWC format: T-XXXXXXXXX-X
        import re
        if not re.match(r"^T-[0-9]{9}-[0-9]$", v):
            raise ValueError("ISWC must be in format T-XXXXXXXXX-X")
        return v
    
    @field_validator("language")
    @classmethod
    def validate_language(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        
        # ISO 639-1 language code validation
        import re
        if not re.match(r"^[a-z]{2}(-[A-Z]{2})?$", v):
            raise ValueError("Language must be valid ISO 639-1 code")
        return v
    
    @field_validator("registration_status")
    @classmethod
    def validate_registration_status(cls, v: str) -> str:
        valid_statuses = {"draft", "pending", "registered", "published", "archived"}
        if v not in valid_statuses:
            raise ValueError(f"Registration status must be one of: {valid_statuses}")
        return v


class WorkRelationships(BaseSchema):
    """Relationships for work resource."""
    
    writers: Optional[Relationship] = Field(None, description="Work writers")
    recordings: Optional[Relationship] = Field(None, description="Associated recordings")
    original_work: Optional[Relationship] = Field(None, description="Original work reference")


class WorkResource(BaseSchema):
    """JSON:API resource for musical work."""
    
    type: str = Field("work", description="Resource type")
    id: UUID = Field(description="Work UUID")
    attributes: WorkAttributes
    relationships: Optional[WorkRelationships] = None


class WorkCreateRequest(BaseSchema):
    """Request schema for creating a work."""
    
    data: WorkResource = Field(description="Work data to create")


class WorkUpdateRequest(BaseSchema):
    """Request schema for updating a work."""
    
    data: WorkResource = Field(description="Work data to update")


class WorkPatchRequest(BaseSchema):
    """Request schema for patching a work (partial update)."""
    
    data: WorkResource = Field(description="Work data to patch")


class WorkResponse(JSONAPIResponse):
    """Response schema for single work."""
    
    data: WorkResource = Field(description="Work resource")


class WorkCollectionResponse(JSONAPICollectionResponse):
    """Response schema for work collection."""
    
    data: List[WorkResource] = Field(description="Work resources")


class WorkSearchFilters(BaseSchema):
    """Search filters for works."""
    
    q: Optional[str] = Field(None, max_length=500, description="Full-text search query")
    title: Optional[str] = Field(None, description="Title filter (partial match)")
    iswc: Optional[str] = Field(None, description="ISWC filter")
    genre: Optional[str] = Field(None, description="Genre filter")
    language: Optional[str] = Field(None, description="Language filter")
    status: Optional[List[str]] = Field(None, description="Registration status filter")
    writer_name: Optional[str] = Field(None, description="Writer name filter")
    
    # Date range filters
    created_date_gte: Optional[str] = Field(None, description="Created on or after date")
    created_date_lte: Optional[str] = Field(None, description="Created on or before date")
    
    @field_validator("status")
    @classmethod
    def validate_status_list(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return v
        
        valid_statuses = {"draft", "pending", "registered", "published", "archived"}
        for status in v:
            if status not in valid_statuses:
                raise ValueError(f"Each status must be one of: {valid_statuses}")
        return v


class BulkWorkOperation(BaseSchema):
    """Schema for bulk work operations."""
    
    operation: str = Field(description="Operation type: create, update, delete")
    data: List[WorkResource] = Field(description="Work resources for operation")
    
    @field_validator("operation")
    @classmethod
    def validate_operation(cls, v: str) -> str:
        valid_operations = {"create", "update", "delete"}
        if v not in valid_operations:
            raise ValueError(f"Operation must be one of: {valid_operations}")
        return v


class BulkWorkResponse(BaseSchema):
    """Response schema for bulk work operations."""
    
    operation: str = Field(description="Operation type performed")
    total_items: int = Field(description="Total items in the operation")
    successful_items: int = Field(description="Successfully processed items")
    failed_items: int = Field(description="Failed items")
    
    results: List[Dict[str, Any]] = Field(description="Detailed results per item")
    errors: List[Dict[str, Any]] = Field(default_factory=list, description="Error details")
    
    meta: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")