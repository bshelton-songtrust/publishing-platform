"""Pydantic schemas for request/response validation."""

from .base import *
from .work import *
from .songwriter import *
from .recording import *
from .search import *
from .publisher import *

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
    
    # Publisher schemas
    "PublisherAttributes",
    "PublisherBrandingAttributes",
    "PublisherBusinessAddressAttributes", 
    "PublisherSettingsAttributes",
    "PublisherRelationships",
    "PublisherResource",
    "PublisherCreateRequest",
    "PublisherUpdateRequest",
    "PublisherResponse",
    "PublisherCollectionResponse",
    "PublisherSettingsRequest",
    "PublisherSettingsResponse",
    "PublisherBrandingRequest",
    "PublisherBrandingResponse",
    "PublisherUserAttributes",
    "PublisherUserResource",
    "PublisherUserInviteRequest",
    "PublisherUserRoleUpdateRequest",
    "PublisherUserCollectionResponse",
    "PublisherAccountAttributes",
    "PublisherAccountResource",
    "PublisherAccountResponse",
    "PublisherPlanChangeRequest",
    "PublisherUsageStatsAttributes",
    "PublisherUsageStatsResponse",
    "PublisherSearchFilters",
]