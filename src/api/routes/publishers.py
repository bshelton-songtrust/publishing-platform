"""Publisher API endpoints for multi-tenant publishing platform."""

import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload

from src.api.dependencies.common import (
    get_current_tenant_id,
    get_current_user_id,
    get_pagination_params,
    validate_uuid_param,
)
from src.core.database import get_db_session
from src.models.publisher import Publisher
from src.models.account import Account
from src.models.user import User
from src.models.user_publisher import UserPublisher
from src.models.role import Role
from src.schemas.publisher import (
    PublisherCreateRequest,
    PublisherUpdateRequest,
    PublisherResponse,
    PublisherCollectionResponse,
    PublisherSettingsRequest,
    PublisherSettingsResponse,
    PublisherBrandingRequest,
    PublisherBrandingResponse,
    PublisherUserInviteRequest,
    PublisherUserRoleUpdateRequest,
    PublisherUserCollectionResponse,
    PublisherAccountResponse,
    PublisherPlanChangeRequest,
    PublisherUsageStatsResponse,
    PublisherSearchFilters,
)
from src.services.publisher_service import (
    PublisherService,
    PublisherServiceError,
    PublisherNotFoundError,
    PublisherValidationError,
    PublisherPermissionError,
)
from src.services.user_service import UserService
from src.services.account_service import AccountService
from src.services.events import get_event_publisher

logger = logging.getLogger(__name__)
router = APIRouter()


def get_publisher_service(session: AsyncSession = Depends(get_db_session)) -> PublisherService:
    """Get publisher service instance."""
    event_publisher = get_event_publisher()
    return PublisherService(session, event_publisher)


def get_user_service(session: AsyncSession = Depends(get_db_session)) -> UserService:
    """Get user service instance."""
    return UserService(session)


def get_account_service(session: AsyncSession = Depends(get_db_session)) -> AccountService:
    """Get account service instance."""
    return AccountService(session)


async def verify_publisher_access(
    publisher_id: UUID,
    request: Request,
    session: AsyncSession,
    required_permission: str = "read"
) -> Publisher:
    """
    Verify user has access to publisher and return publisher.
    
    For system admins, allows access to any publisher.
    For regular users, enforces publisher-level access.
    """
    user_id = getattr(request.state, "user_id", None)
    is_admin = getattr(request.state, "is_admin", False)
    
    # Get publisher
    query = select(Publisher).where(Publisher.id == publisher_id)
    result = await session.execute(query)
    publisher = result.scalar_one_or_none()
    
    if not publisher:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Publisher not found"
        )
    
    # System admin can access any publisher
    if is_admin:
        return publisher
    
    # Regular users must have relationship with publisher
    if user_id:
        user_publisher_query = select(UserPublisher).where(
            and_(
                UserPublisher.user_id == user_id,
                UserPublisher.publisher_id == publisher_id,
                UserPublisher.status == "active"
            )
        )
        user_publisher_result = await session.execute(user_publisher_query)
        user_publisher = user_publisher_result.scalar_one_or_none()
        
        if user_publisher:
            return publisher
    
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Access denied to this publisher"
    )


# Core Publisher Endpoints

@router.post("", response_model=PublisherResponse, status_code=status.HTTP_201_CREATED)
async def create_publisher(
    request: PublisherCreateRequest,
    user_id: str = Depends(get_current_user_id),
    publisher_service: PublisherService = Depends(get_publisher_service),
):
    """
    Create a new publisher.
    
    Only system administrators can create publishers.
    The creator is automatically assigned as the publisher owner.
    """
    try:
        # Extract publisher data
        publisher_data = request.data.attributes.model_dump()
        
        # Remove nested objects and handle them separately
        branding_data = publisher_data.pop("branding", {})
        address_data = publisher_data.pop("business_address", {})
        settings_data = publisher_data.pop("settings", {})
        additional_data = publisher_data.pop("additional_data", {})
        
        # Convert branding and address from objects to dicts
        if hasattr(branding_data, "model_dump"):
            branding_data = branding_data.model_dump()
        if hasattr(address_data, "model_dump"):
            address_data = address_data.model_dump()
        if hasattr(settings_data, "model_dump"):
            settings_data = settings_data.model_dump()
        
        # Prepare final publisher data
        publisher_data.update({
            "branding": branding_data,
            "business_address": address_data,
            "settings": settings_data,
            "additional_data": additional_data,
        })
        
        # Create publisher
        publisher, account = await publisher_service.create_publisher(
            publisher_data=publisher_data,
            creator_user_id=UUID(user_id)
        )
        
        # Transform response
        publisher_dict = publisher.__dict__.copy()
        publisher_dict["branding"] = publisher.get_branding_config()
        publisher_dict["business_address"] = publisher.get_business_address()
        
        return PublisherResponse(
            data={
                "type": "publisher",
                "id": str(publisher.id),
                "attributes": {
                    k: v for k, v in publisher_dict.items() 
                    if k not in ["id", "_sa_instance_state"]
                }
            }
        )
        
    except PublisherValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "errors": [
                    {
                        "status": "422",
                        "code": error.code,
                        "title": "Validation Error",
                        "detail": error.message,
                        "source": {"pointer": f"/data/attributes/{error.field}"}
                    }
                    for error in e.validation_errors
                ]
            }
        )
    except PublisherServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/{publisher_id}", response_model=PublisherResponse)
async def get_publisher(
    publisher_id: str,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    include: Optional[str] = Query(None, description="Include related resources (account,users,stats)"),
):
    """Get publisher details."""
    try:
        publisher_uuid = validate_uuid_param(publisher_id, "publisher_id")
        
        # Verify access
        publisher = await verify_publisher_access(publisher_uuid, request, session)
        
        # Load relationships if requested
        if include:
            include_list = [i.strip() for i in include.split(",")]
            
            query = select(Publisher).where(Publisher.id == publisher_uuid)
            
            if "account" in include_list:
                query = query.options(joinedload(Publisher.account))
            if "users" in include_list:
                query = query.options(
                    selectinload(Publisher.user_relationships).joinedload(UserPublisher.user)
                )
            
            result = await session.execute(query)
            publisher = result.scalar_one()
        
        # Transform response
        publisher_dict = publisher.__dict__.copy()
        publisher_dict["branding"] = publisher.get_branding_config()
        publisher_dict["business_address"] = publisher.get_business_address()
        
        # Add included data if requested
        included_data = []
        if include and "account" in include and publisher.account:
            included_data.append({
                "type": "account",
                "id": str(publisher.account.id),
                "attributes": {
                    k: v for k, v in publisher.account.__dict__.items()
                    if k not in ["id", "_sa_instance_state", "publisher_id"]
                }
            })
        
        response_data = {
            "data": {
                "type": "publisher",
                "id": str(publisher.id),
                "attributes": {
                    k: v for k, v in publisher_dict.items() 
                    if k not in ["id", "_sa_instance_state"]
                }
            }
        }
        
        if included_data:
            response_data["included"] = included_data
        
        return PublisherResponse(**response_data)
        
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid publisher ID format"
        )


@router.put("/{publisher_id}", response_model=PublisherResponse)
async def update_publisher(
    publisher_id: str,
    request_data: PublisherUpdateRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user_id),
    publisher_service: PublisherService = Depends(get_publisher_service),
):
    """Update publisher information."""
    try:
        publisher_uuid = validate_uuid_param(publisher_id, "publisher_id")
        
        # Verify access (requires admin permission)
        await verify_publisher_access(publisher_uuid, request, session, "admin")
        
        # Extract update data
        update_data = request_data.data.attributes.model_dump(exclude_unset=True)
        
        # Handle nested objects
        if "branding" in update_data:
            branding_data = update_data.pop("branding")
            if hasattr(branding_data, "model_dump"):
                update_data["branding"] = branding_data.model_dump()
        
        if "business_address" in update_data:
            address_data = update_data.pop("business_address")
            if hasattr(address_data, "model_dump"):
                update_data["business_address"] = address_data.model_dump()
        
        if "settings" in update_data:
            settings_data = update_data.pop("settings")
            if hasattr(settings_data, "model_dump"):
                update_data["settings"] = settings_data.model_dump()
        
        # Update publisher
        publisher = await publisher_service.update_publisher(
            publisher_id=publisher_uuid,
            update_data=update_data,
            updated_by=UUID(user_id)
        )
        
        # Transform response
        publisher_dict = publisher.__dict__.copy()
        publisher_dict["branding"] = publisher.get_branding_config()
        publisher_dict["business_address"] = publisher.get_business_address()
        
        return PublisherResponse(
            data={
                "type": "publisher",
                "id": str(publisher.id),
                "attributes": {
                    k: v for k, v in publisher_dict.items() 
                    if k not in ["id", "_sa_instance_state"]
                }
            }
        )
        
    except PublisherValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "errors": [
                    {
                        "status": "422",
                        "code": error.code,
                        "title": "Validation Error",
                        "detail": error.message,
                        "source": {"pointer": f"/data/attributes/{error.field}"}
                    }
                    for error in e.validation_errors
                ]
            }
        )
    except PublisherNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Publisher not found"
        )
    except PublisherServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/{publisher_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_publisher(
    publisher_id: str,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user_id),
    publisher_service: PublisherService = Depends(get_publisher_service),
    reason: Optional[str] = Query(None, description="Reason for archiving"),
):
    """Archive (soft delete) a publisher."""
    try:
        publisher_uuid = validate_uuid_param(publisher_id, "publisher_id")
        
        # Verify access (requires admin permission)
        await verify_publisher_access(publisher_uuid, request, session, "admin")
        
        # Archive publisher
        await publisher_service.archive_publisher(
            publisher_id=publisher_uuid,
            archived_by=UUID(user_id),
            reason=reason
        )
        
        return None
        
    except PublisherNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Publisher not found"
        )
    except PublisherServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("", response_model=PublisherCollectionResponse)
async def list_publishers(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    publisher_service: PublisherService = Depends(get_publisher_service),
    # Pagination
    pagination=Depends(get_pagination_params),
    # Filters
    q: Optional[str] = Query(None, description="Search query"),
    name: Optional[str] = Query(None, description="Filter by name"),
    subdomain: Optional[str] = Query(None, description="Filter by subdomain"),
    publisher_type: Optional[str] = Query(None, description="Filter by publisher type"),
    business_model: Optional[str] = Query(None, description="Filter by business model"),
    status: Optional[List[str]] = Query(None, description="Filter by status"),
    # Includes
    include: Optional[str] = Query(None, description="Include related resources (account,users)"),
):
    """
    List publishers with filtering and pagination.
    
    System administrators can see all publishers.
    Regular users only see publishers they have access to.
    """
    try:
        is_admin = getattr(request.state, "is_admin", False)
        user_id = getattr(request.state, "user_id", None)
        
        # Build filters
        filters = {}
        if q:
            filters["search"] = q
        if publisher_type:
            filters["publisher_type"] = publisher_type
        if business_model:
            filters["business_model"] = business_model
        if status:
            filters["status"] = status[0] if len(status) == 1 else status
        
        # Get publishers based on access level
        if is_admin:
            # Admin can see all publishers
            publishers, total = await publisher_service.list_publishers(
                filters=filters,
                pagination=pagination
            )
        else:
            # Regular users only see their publishers
            if not user_id:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required"
                )
            
            # Get user's publishers
            query = select(Publisher).join(UserPublisher).where(
                and_(
                    UserPublisher.user_id == user_id,
                    UserPublisher.status == "active"
                )
            )
            
            # Apply filters
            if filters.get("search"):
                search_term = f"%{filters['search']}%"
                query = query.where(
                    or_(
                        Publisher.name.ilike(search_term),
                        Publisher.subdomain.ilike(search_term)
                    )
                )
            
            if filters.get("publisher_type"):
                query = query.where(Publisher.publisher_type == filters["publisher_type"])
            
            if filters.get("business_model"):
                query = query.where(Publisher.business_model == filters["business_model"])
            
            if filters.get("status"):
                if isinstance(filters["status"], list):
                    query = query.where(Publisher.status.in_(filters["status"]))
                else:
                    query = query.where(Publisher.status == filters["status"])
            
            # Get total count
            count_query = select(func.count()).select_from(query.subquery())
            total_result = await session.execute(count_query)
            total = total_result.scalar()
            
            # Apply pagination
            query = query.offset(pagination["offset"]).limit(pagination["limit"])
            
            result = await session.execute(query)
            publishers = result.scalars().all()
        
        # Transform to response
        publishers_data = []
        for publisher in publishers:
            publisher_dict = publisher.__dict__.copy()
            publisher_dict["branding"] = publisher.get_branding_config()
            publisher_dict["business_address"] = publisher.get_business_address()
            
            publishers_data.append({
                "type": "publisher",
                "id": str(publisher.id),
                "attributes": {
                    k: v for k, v in publisher_dict.items() 
                    if k not in ["id", "_sa_instance_state"]
                }
            })
        
        return PublisherCollectionResponse(
            data=publishers_data,
            meta={
                "pagination": {
                    "page": pagination["page"],
                    "per_page": pagination["per_page"],
                    "total": total,
                    "pages": (total + pagination["per_page"] - 1) // pagination["per_page"]
                }
            }
        )
        
    except PublisherServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


# Publisher Settings Endpoints

@router.get("/{publisher_id}/settings", response_model=PublisherSettingsResponse)
async def get_publisher_settings(
    publisher_id: str,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    publisher_service: PublisherService = Depends(get_publisher_service),
):
    """Get publisher settings."""
    try:
        publisher_uuid = validate_uuid_param(publisher_id, "publisher_id")
        
        # Verify access
        await verify_publisher_access(publisher_uuid, request, session)
        
        # Get settings
        settings = await publisher_service.get_publisher_settings(publisher_uuid)
        
        return PublisherSettingsResponse(data=settings)
        
    except PublisherNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Publisher not found"
        )
    except PublisherServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.put("/{publisher_id}/settings", response_model=PublisherSettingsResponse)
async def update_publisher_settings(
    publisher_id: str,
    request_data: PublisherSettingsRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user_id),
    publisher_service: PublisherService = Depends(get_publisher_service),
):
    """Update publisher settings."""
    try:
        publisher_uuid = validate_uuid_param(publisher_id, "publisher_id")
        
        # Verify access (requires edit permission)
        await verify_publisher_access(publisher_uuid, request, session, "edit")
        
        # Update settings
        settings = await publisher_service.update_publisher_settings(
            publisher_id=publisher_uuid,
            settings_update=request_data.data,
            updated_by=UUID(user_id)
        )
        
        return PublisherSettingsResponse(data=settings)
        
    except PublisherValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "errors": [
                    {
                        "status": "422",
                        "code": error.code,
                        "title": "Validation Error",
                        "detail": error.message,
                        "source": {"pointer": f"/data/{error.field}"}
                    }
                    for error in e.validation_errors
                ]
            }
        )
    except PublisherNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Publisher not found"
        )
    except PublisherServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


# Publisher Branding Endpoints

@router.get("/{publisher_id}/branding", response_model=PublisherBrandingResponse)
async def get_publisher_branding(
    publisher_id: str,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    publisher_service: PublisherService = Depends(get_publisher_service),
):
    """Get publisher branding configuration."""
    try:
        publisher_uuid = validate_uuid_param(publisher_id, "publisher_id")
        
        # Verify access
        await verify_publisher_access(publisher_uuid, request, session)
        
        # Get branding config
        branding = await publisher_service.get_branding_config(publisher_uuid)
        
        return PublisherBrandingResponse(data=branding)
        
    except PublisherNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Publisher not found"
        )
    except PublisherServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.put("/{publisher_id}/branding", response_model=PublisherBrandingResponse)
async def update_publisher_branding(
    publisher_id: str,
    request_data: PublisherBrandingRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user_id),
    publisher_service: PublisherService = Depends(get_publisher_service),
):
    """Update publisher branding configuration."""
    try:
        publisher_uuid = validate_uuid_param(publisher_id, "publisher_id")
        
        # Verify access (requires edit permission)
        await verify_publisher_access(publisher_uuid, request, session, "edit")
        
        # Update branding
        branding_data = request_data.data.model_dump()
        branding = await publisher_service.update_branding_config(
            publisher_id=publisher_uuid,
            branding_update=branding_data,
            updated_by=UUID(user_id)
        )
        
        return PublisherBrandingResponse(data=branding)
        
    except PublisherValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "errors": [
                    {
                        "status": "422",
                        "code": error.code,
                        "title": "Validation Error",
                        "detail": error.message,
                        "source": {"pointer": f"/data/{error.field}"}
                    }
                    for error in e.validation_errors
                ]
            }
        )
    except PublisherNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Publisher not found"
        )
    except PublisherServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


# Publisher User Management Endpoints

@router.get("/{publisher_id}/users", response_model=PublisherUserCollectionResponse)
async def get_publisher_users(
    publisher_id: str,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    publisher_service: PublisherService = Depends(get_publisher_service),
    # Pagination
    pagination=Depends(get_pagination_params),
    # Filters
    q: Optional[str] = Query(None, description="Search query"),
    role_name: Optional[str] = Query(None, description="Filter by role"),
    status: Optional[str] = Query(None, description="Filter by relationship status"),
):
    """Get users associated with a publisher."""
    try:
        publisher_uuid = validate_uuid_param(publisher_id, "publisher_id")
        
        # Verify access
        await verify_publisher_access(publisher_uuid, request, session)
        
        # Build filters
        filters = {}
        if q:
            filters["search"] = q
        if role_name:
            filters["role_name"] = role_name
        if status:
            filters["status"] = status
        
        # Get publisher users
        user_data_list, total = await publisher_service.get_publisher_users(
            publisher_id=publisher_uuid,
            filters=filters,
            pagination=pagination
        )
        
        # Transform to response
        users_data = []
        for user_data in user_data_list:
            # Create user attributes from the user data
            user_attributes = {
                "user_id": user_data["user_id"],
                "email": user_data["email"],
                "first_name": user_data["first_name"],
                "last_name": user_data["last_name"],
                "full_name": user_data["full_name"],
                "status": user_data["status"],
                "is_verified": user_data["is_verified"],
                "last_login_at": user_data["last_login_at"],
                "role_name": user_data["publisher_relationship"]["role_name"],
                "relationship_status": user_data["publisher_relationship"]["status"],
                "is_primary": user_data["publisher_relationship"]["is_primary"],
                "joined_at": user_data["publisher_relationship"]["joined_at"],
                "last_accessed_at": user_data["publisher_relationship"]["last_accessed_at"],
                "access_count": user_data["publisher_relationship"]["access_count"],
                "permissions": user_data["publisher_relationship"]["permissions"],
            }
            
            users_data.append({
                "type": "publisher_user",
                "id": str(user_data["publisher_relationship"]["id"]),
                "attributes": user_attributes
            })
        
        return PublisherUserCollectionResponse(
            data=users_data,
            meta={
                "pagination": {
                    "page": pagination["page"],
                    "per_page": pagination["per_page"],
                    "total": total,
                    "pages": (total + pagination["per_page"] - 1) // pagination["per_page"]
                }
            }
        )
        
    except PublisherNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Publisher not found"
        )
    except PublisherServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/{publisher_id}/users/invite", status_code=status.HTTP_201_CREATED)
async def invite_user_to_publisher(
    publisher_id: str,
    request_data: PublisherUserInviteRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user_id),
    publisher_service: PublisherService = Depends(get_publisher_service),
    user_service: UserService = Depends(get_user_service),
):
    """Invite user to publisher."""
    try:
        publisher_uuid = validate_uuid_param(publisher_id, "publisher_id")
        
        # Verify access (requires admin permission)
        await verify_publisher_access(publisher_uuid, request, session, "admin")
        
        # Get or create user by email
        user = await user_service.get_user_by_email(request_data.email)
        if not user:
            # Create new user account
            user = await user_service.create_user({
                "email": request_data.email,
                "status": "invited"
            })
        
        # Add user to publisher
        user_publisher = await publisher_service.add_user_to_publisher(
            publisher_id=publisher_uuid,
            user_id=user.id,
            role_id=request_data.role_id,
            added_by=UUID(user_id),
            is_primary=request_data.is_primary,
            send_invitation=request_data.send_email
        )
        
        return {
            "data": {
                "type": "publisher_user_invitation",
                "id": str(user_publisher.id),
                "attributes": {
                    "user_email": request_data.email,
                    "role_id": str(request_data.role_id),
                    "status": user_publisher.status,
                    "invited_at": user_publisher.invited_at
                }
            }
        }
        
    except PublisherNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Publisher not found"
        )
    except PublisherServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.put("/{publisher_id}/users/{user_id}/role")
async def update_user_role(
    publisher_id: str,
    user_id: str,
    request_data: PublisherUserRoleUpdateRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    current_user_id: str = Depends(get_current_user_id),
    publisher_service: PublisherService = Depends(get_publisher_service),
):
    """Update user role within publisher."""
    try:
        publisher_uuid = validate_uuid_param(publisher_id, "publisher_id")
        target_user_uuid = validate_uuid_param(user_id, "user_id")
        
        # Verify access (requires admin permission)
        await verify_publisher_access(publisher_uuid, request, session, "admin")
        
        # Update user role
        user_publisher = await publisher_service.update_user_role(
            publisher_id=publisher_uuid,
            user_id=target_user_uuid,
            new_role_id=request_data.role_id,
            updated_by=UUID(current_user_id)
        )
        
        return {
            "data": {
                "type": "publisher_user_role_update",
                "id": str(user_publisher.id),
                "attributes": {
                    "user_id": str(target_user_uuid),
                    "new_role_id": str(request_data.role_id),
                    "updated_at": user_publisher.updated_at
                }
            }
        }
        
    except PublisherNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Publisher not found"
        )
    except PublisherServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/{publisher_id}/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_user_from_publisher(
    publisher_id: str,
    user_id: str,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    current_user_id: str = Depends(get_current_user_id),
    publisher_service: PublisherService = Depends(get_publisher_service),
    reason: Optional[str] = Query(None, description="Reason for removal"),
):
    """Remove user from publisher."""
    try:
        publisher_uuid = validate_uuid_param(publisher_id, "publisher_id")
        target_user_uuid = validate_uuid_param(user_id, "user_id")
        
        # Verify access (requires admin permission)
        await verify_publisher_access(publisher_uuid, request, session, "admin")
        
        # Remove user from publisher
        await publisher_service.remove_user_from_publisher(
            publisher_id=publisher_uuid,
            user_id=target_user_uuid,
            removed_by=UUID(current_user_id),
            reason=reason
        )
        
        return None
        
    except PublisherNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Publisher not found"
        )
    except PublisherServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


# Account Integration Endpoints

@router.get("/{publisher_id}/account", response_model=PublisherAccountResponse)
async def get_publisher_account(
    publisher_id: str,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
):
    """Get publisher account details."""
    try:
        publisher_uuid = validate_uuid_param(publisher_id, "publisher_id")
        
        # Verify access
        publisher = await verify_publisher_access(publisher_uuid, request, session)
        
        # Get account with relationship loaded
        query = select(Publisher).options(joinedload(Publisher.account)).where(
            Publisher.id == publisher_uuid
        )
        result = await session.execute(query)
        publisher = result.scalar_one()
        
        if not publisher.account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Account not found for publisher"
            )
        
        # Transform account data
        account_dict = publisher.account.__dict__.copy()
        
        return PublisherAccountResponse(
            data={
                "type": "publisher_account",
                "id": str(publisher.account.id),
                "attributes": {
                    k: v for k, v in account_dict.items() 
                    if k not in ["id", "_sa_instance_state", "publisher_id"]
                }
            }
        )
        
    except PublisherNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Publisher not found"
        )


@router.put("/{publisher_id}/account/plan")
async def change_subscription_plan(
    publisher_id: str,
    request_data: PublisherPlanChangeRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user_id),
    account_service: AccountService = Depends(get_account_service),
):
    """Change publisher subscription plan."""
    try:
        publisher_uuid = validate_uuid_param(publisher_id, "publisher_id")
        
        # Verify access (requires admin permission)
        publisher = await verify_publisher_access(publisher_uuid, request, session, "admin")
        
        if not publisher.account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Account not found for publisher"
            )
        
        # Change plan
        account = await account_service.change_plan(
            account_id=publisher.account.id,
            plan_type=request_data.plan_type,
            billing_cycle=request_data.billing_cycle,
            seats_licensed=request_data.seats_licensed,
            changed_by=UUID(user_id),
            effective_date=request_data.effective_date
        )
        
        return {
            "data": {
                "type": "plan_change",
                "id": str(account.id),
                "attributes": {
                    "plan_type": account.plan_type,
                    "billing_cycle": account.billing_cycle,
                    "seats_licensed": account.seats_licensed,
                    "next_billing_date": account.next_billing_date,
                    "monthly_price": account.monthly_price
                }
            }
        }
        
    except PublisherNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Publisher not found"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/{publisher_id}/account/usage", response_model=PublisherUsageStatsResponse)
async def get_usage_statistics(
    publisher_id: str,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    account_service: AccountService = Depends(get_account_service),
):
    """Get publisher usage statistics."""
    try:
        publisher_uuid = validate_uuid_param(publisher_id, "publisher_id")
        
        # Verify access
        publisher = await verify_publisher_access(publisher_uuid, request, session)
        
        if not publisher.account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Account not found for publisher"
            )
        
        # Get usage statistics
        usage_stats = await account_service.get_usage_statistics(publisher.account.id)
        
        return PublisherUsageStatsResponse(data=usage_stats)
        
    except PublisherNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Publisher not found"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )