"""Recording-related Pydantic schemas."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import Field, field_validator

from .base import BaseSchema, JSONAPIResponse, JSONAPICollectionResponse, Relationship


class RecordingContributorAttributes(BaseSchema):
    """Attributes for recording contributor."""
    
    contributor_name: str = Field(min_length=1, max_length=255, description="Contributor name")
    role: str = Field(min_length=1, max_length=100, description="Role in the recording")
    instrument: Optional[str] = Field(None, max_length=100, description="Instrument played")
    is_primary: bool = Field(False, description="Whether this is a primary contributor")
    credit_name: Optional[str] = Field(None, max_length=255, description="Credit name override")
    contribution_description: Optional[str] = Field(
        None, description="Detailed contribution description"
    )


class RecordingAttributes(BaseSchema):
    """Attributes for recording resource."""
    
    # Core identification
    work_id: UUID = Field(description="Associated musical work UUID")
    title: str = Field(min_length=1, max_length=500, description="Recording title")
    isrc: Optional[str] = Field(None, description="International Standard Recording Code")
    
    # Artist and performer information
    artist_name: str = Field(min_length=1, max_length=255, description="Primary artist name")
    featured_artists: List[str] = Field(
        default_factory=list, description="Featured artist names"
    )
    performer_info: Dict[str, Any] = Field(
        default_factory=dict, description="Detailed performer information"
    )
    
    # Release information
    album_title: Optional[str] = Field(None, max_length=255, description="Album title")
    track_number: Optional[int] = Field(None, gt=0, description="Track number")
    disc_number: Optional[int] = Field(None, gt=0, description="Disc number")
    
    # Technical specifications
    duration_ms: Optional[int] = Field(None, gt=0, description="Duration in milliseconds")
    sample_rate: Optional[int] = Field(None, description="Sample rate in Hz")
    bit_depth: Optional[int] = Field(None, description="Bit depth")
    file_format: Optional[str] = Field(None, max_length=50, description="File format")
    
    # Recording details
    recording_date: Optional[str] = Field(None, description="Recording date")
    release_date: Optional[str] = Field(None, description="Release date")
    recording_location: Optional[str] = Field(
        None, max_length=255, description="Recording location"
    )
    
    # Commercial information
    label_name: Optional[str] = Field(None, max_length=255, description="Record label")
    catalog_number: Optional[str] = Field(None, max_length=100, description="Catalog number")
    upc_ean: Optional[str] = Field(None, max_length=20, description="UPC/EAN barcode")
    
    # Classification
    recording_type: str = Field("studio", description="Recording type")
    status: str = Field("active", description="Recording status")
    is_master: bool = Field(True, description="Whether this is a master recording")
    
    # Content flags
    explicit_content: bool = Field(False, description="Contains explicit content")
    is_cover: bool = Field(False, description="Is a cover version")
    is_remix: bool = Field(False, description="Is a remix")
    
    # Additional metadata
    description: Optional[str] = Field(None, description="Recording description")
    tags: List[str] = Field(default_factory=list, description="Tags for categorization")
    production_credits: Dict[str, Any] = Field(
        default_factory=dict, description="Production credits"
    )
    external_ids: Dict[str, str] = Field(
        default_factory=dict, description="External system identifiers"
    )
    media_files: List[Dict[str, Any]] = Field(
        default_factory=list, description="Associated media files"
    )
    
    # Contributors (embedded for convenience)
    contributors: List[RecordingContributorAttributes] = Field(
        default_factory=list, description="Recording contributors"
    )
    
    # Audit fields (read-only)
    created_at: Optional[datetime] = Field(None, description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")
    
    @field_validator("isrc")
    @classmethod
    def validate_isrc(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        
        # ISRC format: Country Code (2) + Registrant Code (3) + Year of Reference (2) + Designation Code (5)
        import re
        if not re.match(r"^[A-Z]{2}[A-Z0-9]{3}[0-9]{7}$", v):
            raise ValueError("ISRC must be in format: 2 letters + 3 alphanumeric + 7 digits")
        return v.upper()
    
    @field_validator("recording_type")
    @classmethod
    def validate_recording_type(cls, v: str) -> str:
        valid_types = {
            "studio", "live", "demo", "remix", "remaster", "alternate", "acoustic"
        }
        if v not in valid_types:
            raise ValueError(f"Recording type must be one of: {valid_types}")
        return v
    
    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        valid_statuses = {"active", "archived", "deleted"}
        if v not in valid_statuses:
            raise ValueError(f"Status must be one of: {valid_statuses}")
        return v
    
    @field_validator("file_format")
    @classmethod
    def validate_file_format(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        
        valid_formats = {
            "mp3", "wav", "flac", "aac", "m4a", "ogg", "wma", "aiff"
        }
        if v.lower() not in valid_formats:
            raise ValueError(f"File format must be one of: {valid_formats}")
        return v.lower()


class RecordingRelationships(BaseSchema):
    """Relationships for recording resource."""
    
    work: Optional[Relationship] = Field(None, description="Associated musical work")
    contributors: Optional[Relationship] = Field(None, description="Recording contributors")


class RecordingResource(BaseSchema):
    """JSON:API resource for recording."""
    
    type: str = Field("recording", description="Resource type")
    id: UUID = Field(description="Recording UUID")
    attributes: RecordingAttributes
    relationships: Optional[RecordingRelationships] = None


class RecordingCreateRequest(BaseSchema):
    """Request schema for creating a recording."""
    
    data: RecordingResource = Field(description="Recording data to create")


class RecordingUpdateRequest(BaseSchema):
    """Request schema for updating a recording."""
    
    data: RecordingResource = Field(description="Recording data to update")


class RecordingPatchRequest(BaseSchema):
    """Request schema for patching a recording (partial update)."""
    
    data: RecordingResource = Field(description="Recording data to patch")


class RecordingResponse(JSONAPIResponse):
    """Response schema for single recording."""
    
    data: RecordingResource = Field(description="Recording resource")


class RecordingCollectionResponse(JSONAPICollectionResponse):
    """Response schema for recording collection."""
    
    data: List[RecordingResource] = Field(description="Recording resources")


class RecordingSearchFilters(BaseSchema):
    """Search filters for recordings."""
    
    q: Optional[str] = Field(None, max_length=500, description="Full-text search query")
    title: Optional[str] = Field(None, description="Title filter (partial match)")
    isrc: Optional[str] = Field(None, description="ISRC filter")
    artist_name: Optional[str] = Field(None, description="Artist name filter")
    album_title: Optional[str] = Field(None, description="Album title filter")
    work_id: Optional[UUID] = Field(None, description="Associated work filter")
    label_name: Optional[str] = Field(None, description="Label name filter")
    recording_type: Optional[List[str]] = Field(None, description="Recording type filter")
    status: Optional[List[str]] = Field(None, description="Status filter")
    file_format: Optional[List[str]] = Field(None, description="File format filter")
    
    # Boolean filters
    is_master: Optional[bool] = Field(None, description="Master recording filter")
    explicit_content: Optional[bool] = Field(None, description="Explicit content filter")
    is_cover: Optional[bool] = Field(None, description="Cover version filter")
    is_remix: Optional[bool] = Field(None, description="Remix filter")
    
    # Date range filters
    recording_date_gte: Optional[str] = Field(None, description="Recorded on or after date")
    recording_date_lte: Optional[str] = Field(None, description="Recorded on or before date")
    release_date_gte: Optional[str] = Field(None, description="Released on or after date")
    release_date_lte: Optional[str] = Field(None, description="Released on or before date")
    created_date_gte: Optional[str] = Field(None, description="Created on or after date")
    created_date_lte: Optional[str] = Field(None, description="Created on or before date")
    
    # Numeric range filters
    duration_min: Optional[int] = Field(None, description="Minimum duration in ms")
    duration_max: Optional[int] = Field(None, description="Maximum duration in ms")
    track_number: Optional[int] = Field(None, description="Track number filter")
    
    @field_validator("recording_type")
    @classmethod
    def validate_recording_type_list(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return v
        
        valid_types = {
            "studio", "live", "demo", "remix", "remaster", "alternate", "acoustic"
        }
        for rec_type in v:
            if rec_type not in valid_types:
                raise ValueError(f"Each recording type must be one of: {valid_types}")
        return v
    
    @field_validator("status")
    @classmethod
    def validate_status_list(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return v
        
        valid_statuses = {"active", "archived", "deleted"}
        for status in v:
            if status not in valid_statuses:
                raise ValueError(f"Each status must be one of: {valid_statuses}")
        return v


class BulkRecordingOperation(BaseSchema):
    """Schema for bulk recording operations."""
    
    operation: str = Field(description="Operation type: create, update, delete")
    data: List[RecordingResource] = Field(description="Recording resources for operation")
    
    @field_validator("operation")
    @classmethod
    def validate_operation(cls, v: str) -> str:
        valid_operations = {"create", "update", "delete"}
        if v not in valid_operations:
            raise ValueError(f"Operation must be one of: {valid_operations}")
        return v


class BulkRecordingResponse(BaseSchema):
    """Response schema for bulk recording operations."""
    
    operation: str = Field(description="Operation type performed")
    total_items: int = Field(description="Total items in the operation")
    successful_items: int = Field(description="Successfully processed items")
    failed_items: int = Field(description="Failed items")
    
    results: List[Dict[str, Any]] = Field(description="Detailed results per item")
    errors: List[Dict[str, Any]] = Field(default_factory=list, description="Error details")
    
    meta: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")