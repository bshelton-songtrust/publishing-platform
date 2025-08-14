"""Songwriters API endpoints."""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies.common import (
    get_current_tenant_id,
    get_current_user_id,
    get_pagination_params,
)
from src.core.database import get_db_session
from src.models.songwriter import Songwriter
from src.schemas.songwriter import (
    SongwriterCreateRequest,
    SongwriterResponse,
    SongwriterCollectionResponse,
    SongwriterUpdateRequest,
    SongwriterPatchRequest,
)
from src.services.events import get_event_publisher

router = APIRouter()


@router.get("", response_model=SongwriterCollectionResponse)
async def list_songwriters(
    # Pagination
    pagination=Depends(get_pagination_params),
    # Filters
    q: Optional[str] = Query(None, description="Search query"),
    first_name: Optional[str] = Query(None, description="Filter by first name"),
    last_name: Optional[str] = Query(None, description="Filter by last name"),
    stage_name: Optional[str] = Query(None, description="Filter by stage name"),
    ipi: Optional[str] = Query(None, description="Filter by IPI"),
    status: Optional[str] = Query(None, description="Filter by status"),
    # Dependencies
    session: AsyncSession = Depends(get_db_session),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """List songwriters with filtering and pagination."""
    # Build query
    query = session.query(Songwriter).filter(Songwriter.tenant_id == tenant_id)
    
    # Apply filters
    if q:
        search_filter = or_(
            Songwriter.first_name.ilike(f"%{q}%"),
            Songwriter.last_name.ilike(f"%{q}%"),
            Songwriter.stage_name.ilike(f"%{q}%"),
            Songwriter.full_name.ilike(f"%{q}%")
        )
        query = query.filter(search_filter)
    
    if first_name:
        query = query.filter(Songwriter.first_name.ilike(f"%{first_name}%"))
    
    if last_name:
        query = query.filter(Songwriter.last_name.ilike(f"%{last_name}%"))
    
    if stage_name:
        query = query.filter(Songwriter.stage_name.ilike(f"%{stage_name}%"))
    
    if ipi:
        query = query.filter(Songwriter.ipi == ipi)
    
    if status:
        query = query.filter(Songwriter.status == status)
    
    # Get total count
    total_query = query.statement.compile()
    total_result = await session.execute(
        func.count().select_from(query.subquery())
    )
    total = total_result.scalar()
    
    # Apply pagination
    query = query.offset(pagination["offset"]).limit(pagination["limit"])
    
    # Execute query
    result = await session.execute(query)
    songwriters = result.scalars().all()
    
    return SongwriterCollectionResponse(
        data=[
            {
                "type": "songwriter",
                "id": str(songwriter.id),
                "attributes": {k: v for k, v in songwriter.to_dict().items() if k not in ["id", "tenant_id", "created_by"]}
            }
            for songwriter in songwriters
        ],
        meta={
            "pagination": {
                "page": pagination["page"],
                "per_page": pagination["per_page"],
                "total": total,
                "pages": (total + pagination["per_page"] - 1) // pagination["per_page"]
            }
        }
    )


@router.post("", response_model=SongwriterResponse, status_code=status.HTTP_201_CREATED)
async def create_songwriter(
    request: SongwriterCreateRequest,
    session: AsyncSession = Depends(get_db_session),
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: str = Depends(get_current_user_id),
):
    """Create a new songwriter."""
    # Create songwriter
    songwriter = Songwriter(
        tenant_id=tenant_id,
        created_by=user_id,
        **request.data.attributes.dict()
    )
    
    session.add(songwriter)
    await session.commit()
    await session.refresh(songwriter)
    
    # Publish event
    event_publisher = get_event_publisher()
    await event_publisher.publish_songwriter_created(songwriter, tenant_id, user_id)
    
    return SongwriterResponse(
        data={
            "type": "songwriter",
            "id": str(songwriter.id),
            "attributes": {k: v for k, v in songwriter.to_dict().items() if k not in ["id", "tenant_id", "created_by"]}
        }
    )


@router.get("/{songwriter_id}", response_model=SongwriterResponse)
async def get_songwriter(
    songwriter_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Get a specific songwriter."""
    result = await session.execute(
        session.query(Songwriter).filter(
            and_(Songwriter.id == songwriter_id, Songwriter.tenant_id == tenant_id)
        )
    )
    songwriter = result.scalar_one_or_none()
    
    if not songwriter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Songwriter not found"
        )
    
    return SongwriterResponse(
        data={
            "type": "songwriter",
            "id": str(songwriter.id),
            "attributes": {k: v for k, v in songwriter.to_dict().items() if k not in ["id", "tenant_id", "created_by"]}
        }
    )


@router.patch("/{songwriter_id}", response_model=SongwriterResponse)
async def update_songwriter(
    songwriter_id: UUID,
    request: SongwriterPatchRequest,
    session: AsyncSession = Depends(get_db_session),
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: str = Depends(get_current_user_id),
):
    """Update a songwriter (partial update)."""
    # Get existing songwriter
    result = await session.execute(
        session.query(Songwriter).filter(
            and_(Songwriter.id == songwriter_id, Songwriter.tenant_id == tenant_id)
        )
    )
    songwriter = result.scalar_one_or_none()
    
    if not songwriter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Songwriter not found"
        )
    
    # Update fields
    update_data = request.data.attributes.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(songwriter, field, value)
    
    await session.commit()
    await session.refresh(songwriter)
    
    # Publish event
    event_publisher = get_event_publisher()
    await event_publisher.publish_songwriter_updated(songwriter, tenant_id, user_id)
    
    return SongwriterResponse(
        data={
            "type": "songwriter",
            "id": str(songwriter.id),
            "attributes": {k: v for k, v in songwriter.to_dict().items() if k not in ["id", "tenant_id", "created_by"]}
        }
    )


@router.delete("/{songwriter_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_songwriter(
    songwriter_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: str = Depends(get_current_user_id),
):
    """Delete a songwriter."""
    # Get existing songwriter
    result = await session.execute(
        session.query(Songwriter).filter(
            and_(Songwriter.id == songwriter_id, Songwriter.tenant_id == tenant_id)
        )
    )
    songwriter = result.scalar_one_or_none()
    
    if not songwriter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Songwriter not found"
        )
    
    # Check if songwriter has associated works
    # This would be implemented based on business rules
    
    # Delete songwriter
    await session.delete(songwriter)
    await session.commit()
    
    # Publish event
    event_publisher = get_event_publisher()
    await event_publisher.publish_songwriter_deleted(songwriter_id, tenant_id, user_id)
    
    return None