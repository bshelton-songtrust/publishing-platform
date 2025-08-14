"""Base Pydantic schemas following JSON:API specification."""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class BaseSchema(BaseModel):
    """Base schema with common configuration."""
    
    class Config:
        from_attributes = True
        populate_by_name = True
        str_strip_whitespace = True
        validate_assignment = True


class PaginationParams(BaseSchema):
    """Pagination parameters for collection endpoints."""
    
    page: int = Field(1, ge=1, le=1000, description="Page number")
    per_page: int = Field(25, ge=1, le=100, description="Items per page")
    sort_by: Optional[str] = Field(None, description="Sort field")
    sort_order: str = Field("asc", description="Sort order: asc or desc")
    
    @field_validator("sort_order")
    @classmethod
    def validate_sort_order(cls, v: str) -> str:
        if v.lower() not in ("asc", "desc"):
            raise ValueError("sort_order must be 'asc' or 'desc'")
        return v.lower()


class PaginationMeta(BaseSchema):
    """Pagination metadata for collection responses."""
    
    page: int = Field(description="Current page number")
    per_page: int = Field(description="Items per page")
    total_items: int = Field(description="Total number of items")
    total_pages: int = Field(description="Total number of pages")
    has_next: bool = Field(description="Whether there is a next page")
    has_prev: bool = Field(description="Whether there is a previous page")


class ResourceIdentifier(BaseSchema):
    """JSON:API resource identifier."""
    
    type: str = Field(description="Resource type")
    id: Union[str, UUID] = Field(description="Resource identifier")


class RelationshipData(BaseSchema):
    """JSON:API relationship data."""
    
    data: Union[ResourceIdentifier, List[ResourceIdentifier], None] = Field(
        description="Related resource identifier(s)"
    )


class Relationship(BaseSchema):
    """JSON:API relationship object."""
    
    data: Union[ResourceIdentifier, List[ResourceIdentifier], None] = Field(
        None, description="Related resource identifier(s)"
    )
    links: Optional[Dict[str, str]] = Field(
        None, description="Links related to the relationship"
    )
    meta: Optional[Dict[str, Any]] = Field(
        None, description="Metadata about the relationship"
    )


class JSONAPIError(BaseSchema):
    """JSON:API error object."""
    
    id: Optional[str] = Field(None, description="Unique error identifier")
    status: Optional[str] = Field(None, description="HTTP status code")
    code: Optional[str] = Field(None, description="Application-specific error code")
    title: Optional[str] = Field(None, description="Short, human-readable summary")
    detail: Optional[str] = Field(None, description="Human-readable explanation")
    source: Optional[Dict[str, str]] = Field(
        None, description="References to the source of the error"
    )
    meta: Optional[Dict[str, Any]] = Field(
        None, description="Additional metadata about the error"
    )


class JSONAPIErrorResponse(BaseSchema):
    """JSON:API error response."""
    
    errors: List[JSONAPIError] = Field(description="Array of error objects")
    meta: Optional[Dict[str, Any]] = Field(
        None, description="Metadata about the error response"
    )


class JSONAPIResponse(BaseSchema):
    """Base JSON:API response for single resources."""
    
    data: Optional[Dict[str, Any]] = Field(None, description="Primary data")
    included: Optional[List[Dict[str, Any]]] = Field(
        None, description="Related resources"
    )
    meta: Optional[Dict[str, Any]] = Field(None, description="Metadata")
    links: Optional[Dict[str, str]] = Field(None, description="Links")


class JSONAPICollectionResponse(BaseSchema):
    """Base JSON:API response for resource collections."""
    
    data: List[Dict[str, Any]] = Field(description="Primary data array")
    included: Optional[List[Dict[str, Any]]] = Field(
        None, description="Related resources"
    )
    meta: Optional[Dict[str, Any]] = Field(None, description="Metadata")
    links: Optional[Dict[str, str]] = Field(None, description="Links")


class HealthCheckResponse(BaseSchema):
    """Health check response schema."""
    
    status: str = Field(description="Service status: healthy, degraded, unhealthy")
    timestamp: datetime = Field(description="Health check timestamp")
    version: str = Field(description="Service version")
    environment: str = Field(description="Environment name")
    
    dependencies: Dict[str, Dict[str, Any]] = Field(
        description="Dependency health status"
    )
    
    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        valid_statuses = {"healthy", "degraded", "unhealthy"}
        if v not in valid_statuses:
            raise ValueError(f"Status must be one of: {valid_statuses}")
        return v


class FieldsParam(BaseSchema):
    """Fields parameter for sparse fieldsets."""
    
    fields: Optional[Dict[str, str]] = Field(
        None,
        description="Sparse fieldsets - comma-separated field names per resource type"
    )


class IncludeParam(BaseSchema):
    """Include parameter for related resources."""
    
    include: Optional[str] = Field(
        None,
        description="Comma-separated list of related resources to include"
    )


class FilterParam(BaseSchema):
    """Base filter parameter."""
    
    filter: Optional[Dict[str, Any]] = Field(
        None,
        description="Filter parameters for resource collection"
    )