"""Search-related Pydantic schemas."""

from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from pydantic import Field, field_validator

from .base import BaseSchema, JSONAPICollectionResponse
from .work import WorkResource
from .songwriter import SongwriterResource  
from .recording import RecordingResource


class SearchParams(BaseSchema):
    """Parameters for search endpoints."""
    
    q: str = Field(min_length=1, max_length=500, description="Search query")
    types: Optional[List[str]] = Field(
        None, description="Resource types to search: work, songwriter, recording"
    )
    
    # Pagination
    page: int = Field(1, ge=1, le=1000, description="Page number")
    per_page: int = Field(25, ge=1, le=100, description="Items per page")
    
    # Sorting
    sort_by: Optional[str] = Field(None, description="Sort field")
    sort_order: str = Field("desc", description="Sort order: asc or desc")
    
    # Search options
    fuzzy: bool = Field(False, description="Enable fuzzy matching")
    min_score: Optional[float] = Field(None, ge=0, le=1, description="Minimum relevance score")
    highlight: bool = Field(False, description="Include search term highlighting")
    
    @field_validator("types")
    @classmethod
    def validate_types(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return v
        
        valid_types = {"work", "songwriter", "recording"}
        for resource_type in v:
            if resource_type not in valid_types:
                raise ValueError(f"Each type must be one of: {valid_types}")
        return v
    
    @field_validator("sort_order")
    @classmethod
    def validate_sort_order(cls, v: str) -> str:
        if v.lower() not in ("asc", "desc"):
            raise ValueError("sort_order must be 'asc' or 'desc'")
        return v.lower()


class SearchResultItem(BaseSchema):
    """Individual search result item."""
    
    resource: Union[WorkResource, SongwriterResource, RecordingResource] = Field(
        description="The matching resource"
    )
    score: float = Field(description="Relevance score (0-1)")
    highlights: Optional[Dict[str, List[str]]] = Field(
        None, description="Highlighted search terms"
    )
    match_fields: List[str] = Field(
        default_factory=list, description="Fields that matched the search"
    )


class SearchFilters(BaseSchema):
    """Advanced search filters."""
    
    # Work-specific filters
    work_genre: Optional[str] = Field(None, description="Work genre filter")
    work_language: Optional[str] = Field(None, description="Work language filter")
    work_status: Optional[List[str]] = Field(None, description="Work status filter")
    work_has_iswc: Optional[bool] = Field(None, description="Work has ISWC filter")
    
    # Songwriter-specific filters
    songwriter_status: Optional[List[str]] = Field(None, description="Songwriter status filter")
    songwriter_nationality: Optional[str] = Field(None, description="Songwriter nationality filter")
    songwriter_has_ipi: Optional[bool] = Field(None, description="Songwriter has IPI filter")
    
    # Recording-specific filters
    recording_type: Optional[List[str]] = Field(None, description="Recording type filter")
    recording_status: Optional[List[str]] = Field(None, description="Recording status filter")
    recording_has_isrc: Optional[bool] = Field(None, description="Recording has ISRC filter")
    
    # Date range filters
    created_date_gte: Optional[str] = Field(None, description="Created on or after date")
    created_date_lte: Optional[str] = Field(None, description="Created on or before date")
    updated_date_gte: Optional[str] = Field(None, description="Updated on or after date")
    updated_date_lte: Optional[str] = Field(None, description="Updated on or before date")


class SearchFacet(BaseSchema):
    """Search facet for aggregated results."""
    
    field: str = Field(description="Field name")
    values: List[Dict[str, Any]] = Field(description="Facet values with counts")


class SearchMeta(BaseSchema):
    """Metadata for search results."""
    
    total_results: int = Field(description="Total number of matching results")
    search_time_ms: float = Field(description="Search execution time in milliseconds")
    max_score: float = Field(description="Maximum relevance score")
    
    # Type-specific counts
    work_count: int = Field(0, description="Number of matching works")
    songwriter_count: int = Field(0, description="Number of matching songwriters")
    recording_count: int = Field(0, description="Number of matching recordings")
    
    # Search query analysis
    analyzed_query: str = Field(description="Processed search query")
    suggested_queries: List[str] = Field(
        default_factory=list, description="Suggested alternative queries"
    )
    
    # Facets for filtering
    facets: List[SearchFacet] = Field(
        default_factory=list, description="Available facets for filtering"
    )


class SearchResponse(JSONAPICollectionResponse):
    """Response schema for search results."""
    
    data: List[SearchResultItem] = Field(description="Search results")
    meta: SearchMeta = Field(description="Search metadata")


class AutocompleteParams(BaseSchema):
    """Parameters for autocomplete endpoints."""
    
    q: str = Field(min_length=1, max_length=100, description="Partial query for completion")
    types: Optional[List[str]] = Field(
        None, description="Resource types: work, songwriter, recording"
    )
    field: Optional[str] = Field(None, description="Specific field to complete")
    limit: int = Field(10, ge=1, le=50, description="Maximum suggestions")
    
    @field_validator("types")
    @classmethod
    def validate_types(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return v
        
        valid_types = {"work", "songwriter", "recording"}
        for resource_type in v:
            if resource_type not in valid_types:
                raise ValueError(f"Each type must be one of: {valid_types}")
        return v


class AutocompleteSuggestion(BaseSchema):
    """Individual autocomplete suggestion."""
    
    text: str = Field(description="Suggested completion text")
    type: str = Field(description="Resource type")
    field: str = Field(description="Field that matched")
    resource_id: Optional[UUID] = Field(None, description="Associated resource ID")
    score: float = Field(description="Suggestion relevance score")


class AutocompleteResponse(BaseSchema):
    """Response schema for autocomplete suggestions."""
    
    query: str = Field(description="Original query")
    suggestions: List[AutocompleteSuggestion] = Field(description="Completion suggestions")
    meta: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class SimilarResourceParams(BaseSchema):
    """Parameters for finding similar resources."""
    
    resource_id: UUID = Field(description="Resource ID to find similar items for")
    resource_type: str = Field(description="Resource type: work, songwriter, recording")
    similarity_threshold: float = Field(0.5, ge=0, le=1, description="Minimum similarity score")
    limit: int = Field(10, ge=1, le=50, description="Maximum similar items")
    
    @field_validator("resource_type")
    @classmethod
    def validate_resource_type(cls, v: str) -> str:
        valid_types = {"work", "songwriter", "recording"}
        if v not in valid_types:
            raise ValueError(f"Resource type must be one of: {valid_types}")
        return v


class SimilarResourceResult(BaseSchema):
    """Similar resource result."""
    
    resource: Union[WorkResource, SongwriterResource, RecordingResource] = Field(
        description="Similar resource"
    )
    similarity_score: float = Field(description="Similarity score (0-1)")
    similarity_reasons: List[str] = Field(
        default_factory=list, description="Reasons for similarity"
    )


class SimilarResourceResponse(BaseSchema):
    """Response schema for similar resources."""
    
    source_resource_id: UUID = Field(description="Source resource ID")
    source_resource_type: str = Field(description="Source resource type")
    similar_resources: List[SimilarResourceResult] = Field(description="Similar resources")
    meta: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")