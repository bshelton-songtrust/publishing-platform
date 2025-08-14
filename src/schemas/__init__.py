"""Pydantic schemas for request/response validation."""

from .base import *
from .work import *
from .songwriter import *
from .recording import *
from .search import *

__all__ = [
    # Base schemas
    "BaseSchema",
    "PaginationParams", 
    "PaginationMeta",
    "JSONAPIResponse",
    "JSONAPICollectionResponse",
    "JSONAPIError",
    "JSONAPIErrorResponse",
    "ResourceIdentifier",
    "RelationshipData",
    "Relationship",
    
    # Work schemas
    "WorkAttributes",
    "WorkRelationships",
    "WorkResource",
    "WorkCreateRequest",
    "WorkUpdateRequest", 
    "WorkResponse",
    "WorkCollectionResponse",
    "WorkWriterAttributes",
    "WorkWriterResource",
    
    # Songwriter schemas
    "SongwriterAttributes",
    "SongwriterResource",
    "SongwriterCreateRequest",
    "SongwriterUpdateRequest",
    "SongwriterResponse",
    "SongwriterCollectionResponse",
    
    # Recording schemas
    "RecordingAttributes",
    "RecordingRelationships",
    "RecordingResource",
    "RecordingCreateRequest",
    "RecordingUpdateRequest",
    "RecordingResponse",
    "RecordingCollectionResponse",
    
    # Search schemas
    "SearchParams",
    "SearchResponse",
    "SearchFilters",
]