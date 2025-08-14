"""Service token management API endpoints."""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field, validator

from src.core.database import get_db_session
from src.services.service_account_service import ServiceAccountService
from src.services.token_service import TokenService
from src.middleware.enhanced_auth import (
    get_current_user_id, 
    get_current_publisher_id,
    require_permission,
    require_token_type
)
from src.schemas.base import BaseCollectionResponse

router = APIRouter(prefix="/service-accounts", tags=["Service Accounts"])


# Request/Response Models

class ServiceAccountCreateRequest(BaseModel):
    """Service account creation request."""
    name: str = Field(..., min_length=3, max_length=100, description="Unique service account name")
    display_name: str = Field(..., min_length=3, max_length=255, description="Human-readable display name")
    description: Optional[str] = Field(None, description="Description of the service account")
    service_type: str = Field(..., description="Type of service: external, internal, partner, automation")
    publisher_id: Optional[str] = Field(None, description="Publisher this service account belongs to")
    scopes: Optional[List[str]] = Field(None, description="Permission scopes for this service")
    
    # Rate limiting
    rate_limit_per_minute: Optional[int] = Field(60, ge=1, le=10000, description="Requests per minute limit")
    rate_limit_per_hour: Optional[int] = Field(1000, ge=1, le=100000, description="Requests per hour limit")
    rate_limit_per_day: Optional[int] = Field(10000, ge=1, le=1000000, description="Requests per day limit")
    
    # IP restrictions
    allowed_ips: Optional[List[str]] = Field(None, description="Allowed IP addresses/ranges")
    require_ip_allowlist: bool = Field(False, description="Whether to enforce IP allowlist")
    
    # Webhooks
    webhook_url: Optional[str] = Field(None, description="Webhook URL for events")
    webhook_events: Optional[List[str]] = Field(None, description="Events to send via webhook")

    @validator('service_type')
    def validate_service_type(cls, v):
        allowed_types = ['external', 'internal', 'partner', 'automation', 'integration']
        if v not in allowed_types:
            raise ValueError(f'service_type must be one of: {", ".join(allowed_types)}')
        return v

    @validator('name')
    def validate_name_format(cls, v):
        if not v.replace('-', '').replace('_', '').isalnum():
            raise ValueError('name must contain only alphanumeric characters, hyphens, and underscores')
        return v.lower()


class ServiceAccountUpdateRequest(BaseModel):
    """Service account update request."""
    display_name: Optional[str] = Field(None, min_length=3, max_length=255)
    description: Optional[str] = Field(None)
    scopes: Optional[List[str]] = Field(None)
    rate_limit_per_minute: Optional[int] = Field(None, ge=1, le=10000)
    rate_limit_per_hour: Optional[int] = Field(None, ge=1, le=100000)
    rate_limit_per_day: Optional[int] = Field(None, ge=1, le=1000000)
    allowed_ips: Optional[List[str]] = Field(None)
    require_ip_allowlist: Optional[bool] = Field(None)
    webhook_url: Optional[str] = Field(None)
    webhook_events: Optional[List[str]] = Field(None)


class ServiceAccountResponse(BaseModel):
    """Service account response model."""
    id: str
    name: str
    display_name: str
    description: Optional[str]
    service_type: str
    publisher_id: Optional[str]
    owner_user_id: Optional[str]
    owner_email: str
    status: str
    is_active: bool
    scopes: List[str]
    
    # Usage stats
    total_requests: int
    total_errors: int
    last_used_at: Optional[datetime]
    
    # Rate limits
    rate_limit_per_minute: int
    rate_limit_per_hour: int
    rate_limit_per_day: int
    burst_limit: int
    
    # Security
    allowed_ips: List[str]
    require_ip_allowlist: bool
    
    # Webhooks
    webhook_url: Optional[str]
    webhook_events: List[str]
    
    # Metadata
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ServiceAccountCollectionResponse(BaseCollectionResponse):
    """Collection response for service accounts."""
    data: List[ServiceAccountResponse]


class ServiceTokenCreateRequest(BaseModel):
    """Service token creation request."""
    name: str = Field(..., min_length=1, max_length=100, description="Token name/description")
    expires_at: Optional[datetime] = Field(None, description="Token expiration date (null for non-expiring)")
    scopes: Optional[List[str]] = Field(None, description="Token-specific scopes (overrides service account scopes)")

    @validator('expires_at')
    def validate_future_expiration(cls, v):
        if v and v <= datetime.utcnow():
            raise ValueError('expires_at must be in the future')
        return v


class ServiceTokenResponse(BaseModel):
    """Service token response model (safe fields only)."""
    id: str
    name: str
    prefix: str
    suffix: str
    token_type: str
    status: str
    expires_at: Optional[datetime]
    last_used_at: Optional[datetime]
    total_requests: int
    created_at: datetime

    class Config:
        from_attributes = True


class ServiceTokenCreateResponse(BaseModel):
    """Response for token creation including the actual token."""
    token: str = Field(..., description="The actual token value (only shown once)")
    token_info: ServiceTokenResponse = Field(..., description="Token metadata")


class ServiceTokenCollectionResponse(BaseCollectionResponse):
    """Collection response for service tokens."""
    data: List[ServiceTokenResponse]


class ServiceUsageStatsResponse(BaseModel):
    """Service account usage statistics."""
    service_account_id: str
    period_days: int
    total_requests: int
    total_errors: int
    error_rate: float
    active_tokens: int
    total_tokens: int
    last_used_at: Optional[datetime]
    monthly_usage: Dict[str, Any]
    rate_limits: Dict[str, int]


# Service Account Management

@router.post("", response_model=ServiceAccountResponse)
async def create_service_account(
    request: ServiceAccountCreateRequest,
    user_id: str = Depends(get_current_user_id),
    publisher_id: str = Depends(get_current_publisher_id),
    session: AsyncSession = Depends(get_db_session),
    _: bool = Depends(require_permission("service_accounts:create"))
):
    """
    Create a new service account.
    
    Requires 'service_accounts:create' permission.
    """
    service_account_service = ServiceAccountService(session)
    
    # Use request publisher_id or fallback to current user's publisher
    target_publisher_id = request.publisher_id or publisher_id
    
    try:
        service_account = await service_account_service.create_service_account(
            name=request.name,
            display_name=request.display_name,
            description=request.description,
            service_type=request.service_type,
            publisher_id=target_publisher_id,
            owner_user_id=user_id,
            scopes=request.scopes or [],
            rate_limit_per_minute=request.rate_limit_per_minute,
            rate_limit_per_hour=request.rate_limit_per_hour,
            rate_limit_per_day=request.rate_limit_per_day,
            allowed_ips=request.allowed_ips or [],
            require_ip_allowlist=request.require_ip_allowlist,
            webhook_url=request.webhook_url,
            webhook_events=request.webhook_events or []
        )
        
        return ServiceAccountResponse.from_orm(service_account)
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "service_account_creation_failed",
                "message": str(e),
                "code": "SERVICE_ACCOUNT_CREATION_FAILED"
            }
        )


@router.get("", response_model=ServiceAccountCollectionResponse)
async def list_service_accounts(
    publisher_id: Optional[str] = Query(None, description="Filter by publisher ID"),
    service_type: Optional[str] = Query(None, description="Filter by service type"),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    user_id: str = Depends(get_current_user_id),
    current_publisher_id: Optional[str] = Depends(get_current_publisher_id),
    session: AsyncSession = Depends(get_db_session),
    _: bool = Depends(require_permission("service_accounts:read"))
):
    """
    List service accounts with filtering and pagination.
    
    Requires 'service_accounts:read' permission.
    """
    service_account_service = ServiceAccountService(session)
    
    # Use filter publisher_id or current publisher context
    filter_publisher_id = publisher_id or current_publisher_id
    
    service_accounts = await service_account_service.list_service_accounts(
        publisher_id=filter_publisher_id,
        service_type=service_type,
        status=status,
        limit=limit,
        offset=offset
    )
    
    return ServiceAccountCollectionResponse(
        data=[ServiceAccountResponse.from_orm(sa) for sa in service_accounts],
        total=len(service_accounts),  # In a real implementation, get total count
        limit=limit,
        offset=offset
    )


@router.get("/{service_account_id}", response_model=ServiceAccountResponse)
async def get_service_account(
    service_account_id: str,
    session: AsyncSession = Depends(get_db_session),
    _: bool = Depends(require_permission("service_accounts:read"))
):
    """
    Get a specific service account by ID.
    
    Requires 'service_accounts:read' permission.
    """
    service_account_service = ServiceAccountService(session)
    
    service_account = await service_account_service.get_service_account(service_account_id)
    if not service_account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "service_account_not_found",
                "message": "Service account not found",
                "code": "SERVICE_ACCOUNT_NOT_FOUND"
            }
        )
    
    return ServiceAccountResponse.from_orm(service_account)


@router.put("/{service_account_id}", response_model=ServiceAccountResponse)
async def update_service_account(
    service_account_id: str,
    request: ServiceAccountUpdateRequest,
    session: AsyncSession = Depends(get_db_session),
    _: bool = Depends(require_permission("service_accounts:update"))
):
    """
    Update a service account.
    
    Requires 'service_accounts:update' permission.
    """
    service_account_service = ServiceAccountService(session)
    
    # Convert request to dict, excluding None values
    updates = {k: v for k, v in request.dict().items() if v is not None}
    
    service_account = await service_account_service.update_service_account(
        service_account_id, **updates
    )
    
    if not service_account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "service_account_not_found",
                "message": "Service account not found",
                "code": "SERVICE_ACCOUNT_NOT_FOUND"
            }
        )
    
    return ServiceAccountResponse.from_orm(service_account)


@router.post("/{service_account_id}/suspend")
async def suspend_service_account(
    service_account_id: str,
    reason: str,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
    _: bool = Depends(require_permission("service_accounts:admin"))
):
    """
    Suspend a service account.
    
    Requires 'service_accounts:admin' permission.
    """
    service_account_service = ServiceAccountService(session)
    
    success = await service_account_service.suspend_service_account(
        service_account_id, reason, user_id
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "service_account_not_found",
                "message": "Service account not found",
                "code": "SERVICE_ACCOUNT_NOT_FOUND"
            }
        )
    
    return {"message": "Service account suspended successfully"}


@router.post("/{service_account_id}/reactivate")
async def reactivate_service_account(
    service_account_id: str,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
    _: bool = Depends(require_permission("service_accounts:admin"))
):
    """
    Reactivate a suspended service account.
    
    Requires 'service_accounts:admin' permission.
    """
    service_account_service = ServiceAccountService(session)
    
    success = await service_account_service.reactivate_service_account(
        service_account_id, user_id
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "service_account_not_found_or_not_suspended",
                "message": "Service account not found or not suspended",
                "code": "SERVICE_ACCOUNT_NOT_FOUND_OR_NOT_SUSPENDED"
            }
        )
    
    return {"message": "Service account reactivated successfully"}


@router.delete("/{service_account_id}")
async def delete_service_account(
    service_account_id: str,
    session: AsyncSession = Depends(get_db_session),
    _: bool = Depends(require_permission("service_accounts:delete"))
):
    """
    Delete a service account (soft delete).
    
    Requires 'service_accounts:delete' permission.
    """
    service_account_service = ServiceAccountService(session)
    
    success = await service_account_service.delete_service_account(service_account_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "service_account_not_found",
                "message": "Service account not found",
                "code": "SERVICE_ACCOUNT_NOT_FOUND"
            }
        )
    
    return {"message": "Service account deleted successfully"}


# Token Management

@router.post("/{service_account_id}/tokens", response_model=ServiceTokenCreateResponse)
async def create_service_token(
    service_account_id: str,
    request: ServiceTokenCreateRequest,
    session: AsyncSession = Depends(get_db_session),
    _: bool = Depends(require_permission("service_tokens:create"))
):
    """
    Create a new token for a service account.
    
    Requires 'service_tokens:create' permission.
    
    **Warning**: The token value is only returned once. Store it securely.
    """
    service_account_service = ServiceAccountService(session)
    
    try:
        raw_token, service_token = await service_account_service.create_token(
            service_account_id,
            request.name,
            request.expires_at,
            request.scopes
        )
        
        return ServiceTokenCreateResponse(
            token=raw_token,
            token_info=ServiceTokenResponse.from_orm(service_token)
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "token_creation_failed",
                "message": str(e),
                "code": "TOKEN_CREATION_FAILED"
            }
        )


@router.get("/{service_account_id}/tokens", response_model=ServiceTokenCollectionResponse)
async def list_service_tokens(
    service_account_id: str,
    include_inactive: bool = Query(False, description="Include inactive/revoked tokens"),
    session: AsyncSession = Depends(get_db_session),
    _: bool = Depends(require_permission("service_tokens:read"))
):
    """
    List tokens for a service account.
    
    Requires 'service_tokens:read' permission.
    """
    service_account_service = ServiceAccountService(session)
    
    tokens = await service_account_service.list_tokens(service_account_id, include_inactive)
    
    return ServiceTokenCollectionResponse(
        data=[ServiceTokenResponse.from_orm(token) for token in tokens],
        total=len(tokens),
        limit=100,  # Default limit
        offset=0
    )


@router.post("/{service_account_id}/tokens/{token_id}/rotate", response_model=ServiceTokenCreateResponse)
async def rotate_service_token(
    service_account_id: str,
    token_id: str,
    new_name: Optional[str] = Query(None, description="Name for the new token"),
    session: AsyncSession = Depends(get_db_session),
    _: bool = Depends(require_permission("service_tokens:rotate"))
):
    """
    Rotate a service token (create new one and start grace period for old one).
    
    Requires 'service_tokens:rotate' permission.
    
    **Warning**: The new token value is only returned once. Store it securely.
    """
    service_account_service = ServiceAccountService(session)
    
    try:
        raw_token, new_token = await service_account_service.rotate_token(token_id, new_name)
        
        return ServiceTokenCreateResponse(
            token=raw_token,
            token_info=ServiceTokenResponse.from_orm(new_token)
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "token_rotation_failed",
                "message": str(e),
                "code": "TOKEN_ROTATION_FAILED"
            }
        )


@router.delete("/{service_account_id}/tokens/{token_id}")
async def revoke_service_token(
    service_account_id: str,
    token_id: str,
    reason: Optional[str] = Query(None, description="Reason for revocation"),
    session: AsyncSession = Depends(get_db_session),
    _: bool = Depends(require_permission("service_tokens:revoke"))
):
    """
    Revoke a service token.
    
    Requires 'service_tokens:revoke' permission.
    """
    service_account_service = ServiceAccountService(session)
    
    success = await service_account_service.revoke_token(token_id, reason)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "token_not_found",
                "message": "Token not found",
                "code": "TOKEN_NOT_FOUND"
            }
        )
    
    return {"message": "Token revoked successfully"}


# Usage and Analytics

@router.get("/{service_account_id}/usage", response_model=ServiceUsageStatsResponse)
async def get_service_usage_stats(
    service_account_id: str,
    period_days: int = Query(30, ge=1, le=365, description="Period in days for usage stats"),
    session: AsyncSession = Depends(get_db_session),
    _: bool = Depends(require_permission("service_accounts:read"))
):
    """
    Get usage statistics for a service account.
    
    Requires 'service_accounts:read' permission.
    """
    service_account_service = ServiceAccountService(session)
    
    usage_stats = await service_account_service.get_usage_stats(service_account_id, period_days)
    
    if not usage_stats:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "service_account_not_found",
                "message": "Service account not found",
                "code": "SERVICE_ACCOUNT_NOT_FOUND"
            }
        )
    
    return ServiceUsageStatsResponse(**usage_stats)


@router.get("/{service_account_id}/security-events")
async def get_security_events(
    service_account_id: str,
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of events to return"),
    session: AsyncSession = Depends(get_db_session),
    _: bool = Depends(require_permission("service_accounts:read"))
):
    """
    Get security events for a service account.
    
    Requires 'service_accounts:read' permission.
    """
    service_account_service = ServiceAccountService(session)
    
    events = await service_account_service.get_security_events(service_account_id, limit)
    
    return {"events": events}


# IP Management

@router.post("/{service_account_id}/allowed-ips")
async def add_allowed_ip(
    service_account_id: str,
    ip_address: str,
    session: AsyncSession = Depends(get_db_session),
    _: bool = Depends(require_permission("service_accounts:update"))
):
    """
    Add an IP address to the allowed list.
    
    Requires 'service_accounts:update' permission.
    """
    service_account_service = ServiceAccountService(session)
    
    success = await service_account_service.add_allowed_ip(service_account_id, ip_address)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "service_account_not_found",
                "message": "Service account not found",
                "code": "SERVICE_ACCOUNT_NOT_FOUND"
            }
        )
    
    return {"message": f"IP address {ip_address} added to allowed list"}


@router.delete("/{service_account_id}/allowed-ips/{ip_address}")
async def remove_allowed_ip(
    service_account_id: str,
    ip_address: str,
    session: AsyncSession = Depends(get_db_session),
    _: bool = Depends(require_permission("service_accounts:update"))
):
    """
    Remove an IP address from the allowed list.
    
    Requires 'service_accounts:update' permission.
    """
    service_account_service = ServiceAccountService(session)
    
    success = await service_account_service.remove_allowed_ip(service_account_id, ip_address)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "service_account_not_found",
                "message": "Service account not found",
                "code": "SERVICE_ACCOUNT_NOT_FOUND"
            }
        )
    
    return {"message": f"IP address {ip_address} removed from allowed list"}