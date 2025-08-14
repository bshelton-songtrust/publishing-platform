"""Personal Access Token management API endpoints."""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field, validator

from src.core.database import get_db_session
from src.services.token_service import TokenService
from src.services.user_service import UserService
from src.middleware.enhanced_auth import (
    get_current_user_id, 
    get_current_publisher_id,
    require_token_type
)
from src.schemas.base import BaseCollectionResponse

router = APIRouter(prefix="/users/me/tokens", tags=["Personal Access Tokens"])


# Request/Response Models

class PersonalAccessTokenCreateRequest(BaseModel):
    """Personal access token creation request."""
    name: str = Field(..., min_length=1, max_length=100, description="Token name (e.g., 'CI/CD Pipeline', 'Mobile App')")
    description: Optional[str] = Field(None, max_length=500, description="Optional description of the token's purpose")
    publisher_id: Optional[str] = Field(None, description="Publisher to scope this token to (null for multi-publisher access)")
    scopes: Optional[List[str]] = Field(None, description="Permission scopes for this token")
    inherit_user_permissions: bool = Field(True, description="Whether to inherit all user permissions or use only specified scopes")
    expires_at: Optional[datetime] = Field(None, description="Token expiration date (null for non-expiring)")
    
    # IP restrictions
    allowed_ips: Optional[List[str]] = Field(None, description="Allowed IP addresses/ranges")
    require_ip_allowlist: bool = Field(False, description="Whether to enforce IP allowlist")
    
    # Tags for organization
    tags: Optional[List[str]] = Field(None, description="Tags for categorization")

    @validator('expires_at')
    def validate_future_expiration(cls, v):
        if v and v <= datetime.utcnow():
            raise ValueError('expires_at must be in the future')
        return v

    @validator('name')
    def validate_name(cls, v):
        if not v.strip():
            raise ValueError('name cannot be empty')
        return v.strip()


class PersonalAccessTokenUpdateRequest(BaseModel):
    """Personal access token update request."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    scopes: Optional[List[str]] = Field(None)
    expires_at: Optional[datetime] = Field(None)
    allowed_ips: Optional[List[str]] = Field(None)
    require_ip_allowlist: Optional[bool] = Field(None)
    tags: Optional[List[str]] = Field(None)

    @validator('expires_at')
    def validate_future_expiration(cls, v):
        if v and v <= datetime.utcnow():
            raise ValueError('expires_at must be in the future')
        return v


class PersonalAccessTokenResponse(BaseModel):
    """Personal access token response model (safe fields only)."""
    id: str
    name: str
    description: Optional[str]
    prefix: str
    suffix: str
    status: str
    publisher_id: Optional[str]
    expires_at: Optional[datetime]
    last_used_at: Optional[datetime]
    total_requests: int
    scopes: Optional[List[str]]
    inherit_user_permissions: bool
    tags: List[str]
    created_at: datetime

    class Config:
        from_attributes = True


class PersonalAccessTokenCreateResponse(BaseModel):
    """Response for token creation including the actual token."""
    token: str = Field(..., description="The actual token value (only shown once)")
    token_info: PersonalAccessTokenResponse = Field(..., description="Token metadata")


class PersonalAccessTokenCollectionResponse(BaseCollectionResponse):
    """Collection response for personal access tokens."""
    data: List[PersonalAccessTokenResponse]


class PersonalAccessTokenUsageResponse(BaseModel):
    """Personal access token usage statistics."""
    token_id: str
    total_requests: int
    total_errors: int
    error_rate: float
    last_used_at: Optional[datetime]
    days_since_last_use: Optional[int]
    daily_usage_count: int
    most_used_endpoints: List[Dict[str, Any]]


# Token Management Endpoints

@router.post("", response_model=PersonalAccessTokenCreateResponse)
async def create_personal_access_token(
    request: PersonalAccessTokenCreateRequest,
    user_id: str = Depends(get_current_user_id),
    current_publisher_id: Optional[str] = Depends(get_current_publisher_id),
    session: AsyncSession = Depends(get_db_session),
    # Only user tokens can create PATs (not service tokens or other PATs)
    _: str = Depends(require_token_type("user"))
):
    """
    Create a new personal access token.
    
    **Warning**: The token value is only returned once. Store it securely.
    
    Personal access tokens allow you to authenticate to the API without using your password.
    They inherit your user permissions but can be further restricted with scopes.
    """
    token_service = TokenService(session)
    user_service = UserService(session)
    
    # Get user to verify they exist and are active
    user = await user_service.get_user(user_id)
    if not user or not user.can_login():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "user_inactive",
                "message": "User account is inactive",
                "code": "USER_INACTIVE"
            }
        )
    
    # Use request publisher_id or current publisher context
    target_publisher_id = request.publisher_id or current_publisher_id
    
    # Verify user has access to the specified publisher
    if target_publisher_id:
        has_access = await user_service.verify_publisher_access(user_id, target_publisher_id)
        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "no_publisher_access",
                    "message": "User does not have access to the specified publisher",
                    "code": "NO_PUBLISHER_ACCESS"
                }
            )
    
    try:
        raw_token, pat = await token_service.create_personal_access_token(
            user=user,
            name=request.name,
            description=request.description,
            publisher_id=target_publisher_id,
            scopes=request.scopes,
            expires_at=request.expires_at
        )
        
        # Update additional fields that aren't set by the service
        if request.allowed_ips:
            pat.allowed_ips = request.allowed_ips
        if request.require_ip_allowlist:
            pat.require_ip_allowlist = request.require_ip_allowlist
        if request.tags:
            pat.tags = request.tags
        if not request.inherit_user_permissions:
            pat.inherit_user_permissions = False
        
        await session.commit()
        
        return PersonalAccessTokenCreateResponse(
            token=raw_token,
            token_info=PersonalAccessTokenResponse.from_orm(pat)
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


@router.get("", response_model=PersonalAccessTokenCollectionResponse)
async def list_personal_access_tokens(
    publisher_id: Optional[str] = Query(None, description="Filter by publisher ID"),
    status: Optional[str] = Query(None, description="Filter by status (active, expired, revoked)"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session)
):
    """
    List personal access tokens for the current user.
    """
    from sqlalchemy import select, and_
    from src.models import PersonalAccessToken
    
    # Build query
    stmt = select(PersonalAccessToken).where(PersonalAccessToken.user_id == user_id)
    
    # Apply filters
    if publisher_id:
        stmt = stmt.where(PersonalAccessToken.publisher_id == publisher_id)
    if status:
        stmt = stmt.where(PersonalAccessToken.status == status)
    
    # Apply pagination and ordering
    stmt = stmt.offset(offset).limit(limit).order_by(PersonalAccessToken.created_at.desc())
    
    result = await session.execute(stmt)
    tokens = result.scalars().all()
    
    return PersonalAccessTokenCollectionResponse(
        data=[PersonalAccessTokenResponse.from_orm(token) for token in tokens],
        total=len(tokens),  # In a real implementation, get total count
        limit=limit,
        offset=offset
    )


@router.get("/{token_id}", response_model=PersonalAccessTokenResponse)
async def get_personal_access_token(
    token_id: str,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Get a specific personal access token by ID.
    """
    from src.models import PersonalAccessToken
    
    token = await session.get(PersonalAccessToken, token_id)
    
    if not token or token.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "token_not_found",
                "message": "Personal access token not found",
                "code": "TOKEN_NOT_FOUND"
            }
        )
    
    return PersonalAccessTokenResponse.from_orm(token)


@router.put("/{token_id}", response_model=PersonalAccessTokenResponse)
async def update_personal_access_token(
    token_id: str,
    request: PersonalAccessTokenUpdateRequest,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Update a personal access token.
    
    Note: You cannot change the token value itself, only its metadata.
    """
    from src.models import PersonalAccessToken
    
    token = await session.get(PersonalAccessToken, token_id)
    
    if not token or token.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "token_not_found",
                "message": "Personal access token not found",
                "code": "TOKEN_NOT_FOUND"
            }
        )
    
    # Update fields
    update_data = request.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(token, field, value)
    
    await session.commit()
    
    return PersonalAccessTokenResponse.from_orm(token)


@router.delete("/{token_id}")
async def revoke_personal_access_token(
    token_id: str,
    reason: Optional[str] = Query(None, description="Reason for revocation"),
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Revoke a personal access token.
    
    Once revoked, the token cannot be used for authentication.
    """
    from src.models import PersonalAccessToken
    
    token = await session.get(PersonalAccessToken, token_id)
    
    if not token or token.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "token_not_found",
                "message": "Personal access token not found",
                "code": "TOKEN_NOT_FOUND"
            }
        )
    
    # Revoke the token
    token.revoke(reason)
    await session.commit()
    
    return {"message": "Personal access token revoked successfully"}


@router.post("/{token_id}/suspend")
async def suspend_personal_access_token(
    token_id: str,
    reason: Optional[str] = Query(None, description="Reason for suspension"),
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Temporarily suspend a personal access token.
    
    Suspended tokens cannot be used but can be reactivated later.
    """
    from src.models import PersonalAccessToken
    
    token = await session.get(PersonalAccessToken, token_id)
    
    if not token or token.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "token_not_found",
                "message": "Personal access token not found",
                "code": "TOKEN_NOT_FOUND"
            }
        )
    
    if token.status != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "token_not_active",
                "message": "Token is not active and cannot be suspended",
                "code": "TOKEN_NOT_ACTIVE"
            }
        )
    
    # Suspend the token
    token.suspend(reason)
    await session.commit()
    
    return {"message": "Personal access token suspended successfully"}


@router.post("/{token_id}/reactivate")
async def reactivate_personal_access_token(
    token_id: str,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Reactivate a suspended personal access token.
    """
    from src.models import PersonalAccessToken
    
    token = await session.get(PersonalAccessToken, token_id)
    
    if not token or token.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "token_not_found",
                "message": "Personal access token not found",
                "code": "TOKEN_NOT_FOUND"
            }
        )
    
    if token.status != "suspended":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "token_not_suspended",
                "message": "Token is not suspended and cannot be reactivated",
                "code": "TOKEN_NOT_SUSPENDED"
            }
        )
    
    # Check if token is expired
    if token.is_expired():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "token_expired",
                "message": "Cannot reactivate an expired token",
                "code": "TOKEN_EXPIRED"
            }
        )
    
    # Reactivate the token
    token.reactivate()
    await session.commit()
    
    return {"message": "Personal access token reactivated successfully"}


# Analytics and Usage

@router.get("/{token_id}/usage", response_model=PersonalAccessTokenUsageResponse)
async def get_token_usage_stats(
    token_id: str,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Get usage statistics for a personal access token.
    """
    from src.models import PersonalAccessToken
    
    token = await session.get(PersonalAccessToken, token_id)
    
    if not token or token.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "token_not_found",
                "message": "Personal access token not found",
                "code": "TOKEN_NOT_FOUND"
            }
        )
    
    usage_summary = token.get_usage_summary()
    
    return PersonalAccessTokenUsageResponse(
        token_id=str(token.id),
        **usage_summary
    )


@router.get("/{token_id}/security-events")
async def get_token_security_events(
    token_id: str,
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of events to return"),
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Get security events for a personal access token.
    """
    from src.models import PersonalAccessToken
    
    token = await session.get(PersonalAccessToken, token_id)
    
    if not token or token.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "token_not_found",
                "message": "Personal access token not found",
                "code": "TOKEN_NOT_FOUND"
            }
        )
    
    # Get recent security events
    events = token.security_events[-limit:] if token.security_events else []
    
    return {"events": events}


# Bulk Operations

@router.post("/cleanup-expired")
async def cleanup_expired_tokens(
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Clean up expired personal access tokens for the current user.
    """
    from sqlalchemy import select, and_
    from src.models import PersonalAccessToken
    
    # Find expired tokens
    now = datetime.utcnow()
    stmt = select(PersonalAccessToken).where(
        and_(
            PersonalAccessToken.user_id == user_id,
            PersonalAccessToken.expires_at.isnot(None),
            PersonalAccessToken.expires_at < now,
            PersonalAccessToken.status != "revoked"
        )
    )
    
    result = await session.execute(stmt)
    expired_tokens = result.scalars().all()
    
    count = 0
    for token in expired_tokens:
        if token.status != "expired":
            token.status = "expired"
            token.is_active = False
            count += 1
    
    if count > 0:
        await session.commit()
    
    return {"message": f"Cleaned up {count} expired tokens"}


@router.get("/summary")
async def get_tokens_summary(
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Get summary statistics for all personal access tokens.
    """
    from sqlalchemy import select, func
    from src.models import PersonalAccessToken
    
    # Get counts by status
    stmt = select(
        PersonalAccessToken.status,
        func.count(PersonalAccessToken.id).label('count')
    ).where(
        PersonalAccessToken.user_id == user_id
    ).group_by(PersonalAccessToken.status)
    
    result = await session.execute(stmt)
    status_counts = {row.status: row.count for row in result}
    
    # Get total usage
    stmt = select(
        func.sum(PersonalAccessToken.total_requests).label('total_requests'),
        func.sum(PersonalAccessToken.total_errors).label('total_errors')
    ).where(PersonalAccessToken.user_id == user_id)
    
    result = await session.execute(stmt)
    usage_row = result.first()
    
    total_requests = usage_row.total_requests or 0
    total_errors = usage_row.total_errors or 0
    error_rate = (total_errors / total_requests * 100) if total_requests > 0 else 0
    
    return {
        "status_counts": status_counts,
        "total_tokens": sum(status_counts.values()),
        "total_requests": total_requests,
        "total_errors": total_errors,
        "error_rate": error_rate
    }