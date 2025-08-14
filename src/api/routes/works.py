"""Works API endpoints."""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.dependencies.common import (
    get_current_tenant_id,
    get_current_user_id,
    get_pagination_params,
)
from src.core.database import get_db_session
from src.models.work import Work, WorkWriter
from src.models.songwriter import Songwriter
from src.schemas.work import (
    WorkCreateRequest,
    WorkResponse,
    WorkCollectionResponse,
    WorkUpdateRequest,
    WorkPatchRequest,
)
from src.services.business_rules import WorkValidator
from src.services.events import get_event_publisher

router = APIRouter()


@router.get("", response_model=WorkCollectionResponse)
async def list_works(
    # Pagination
    pagination=Depends(get_pagination_params),
    # Filters
    q: Optional[str] = Query(None, description="Search query"),
    title: Optional[str] = Query(None, description="Filter by title"),
    iswc: Optional[str] = Query(None, description="Filter by ISWC"),
    genre: Optional[str] = Query(None, description="Filter by genre"),
    status: Optional[List[str]] = Query(None, description="Filter by status"),
    # Includes
    include: Optional[str] = Query(None, description="Include related resources (writers)"),
    # Dependencies
    session: AsyncSession = Depends(get_db_session),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """List musical works with filtering and pagination."""
    # Build query
    query = select(Work).where(Work.tenant_id == tenant_id)
    
    # Apply filters
    if q:
        search_filter = or_(
            Work.title.ilike(f"%{q}%"),
            Work.iswc.ilike(f"%{q}%"),
            Work.description.ilike(f"%{q}%")
        )
        query = query.where(search_filter)
    
    if title:
        query = query.where(Work.title.ilike(f"%{title}%"))
    
    if iswc:
        query = query.where(Work.iswc == iswc)
    
    if genre:
        query = query.where(Work.genre == genre)
    
    if status:
        query = query.where(Work.status.in_(status))
    
    # Handle includes
    if include and "writers" in include:
        query = query.options(selectinload(Work.work_writers).selectinload(WorkWriter.songwriter))
    
    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await session.execute(count_query)
    total = total_result.scalar()
    
    # Apply pagination
    query = query.offset(pagination["offset"]).limit(pagination["limit"])
    
    # Execute query
    result = await session.execute(query)
    works = result.scalars().all()
    
    # Transform to response
    works_data = []
    for work in works:
        work_dict = work.to_dict()
        if include and "writers" in include and work.work_writers:
            work_dict["writers"] = [
                {
                    "songwriter_id": str(ww.songwriter_id),
                    "songwriter_name": f"{ww.songwriter.first_name} {ww.songwriter.last_name}" if ww.songwriter else None,
                    "role": ww.role,
                    "contribution_percentage": float(ww.contribution_percentage) if ww.contribution_percentage else None
                }
                for ww in work.work_writers
            ]
        works_data.append(work_dict)
    
    return WorkCollectionResponse(
        data=[
            {
                "type": "work",
                "id": str(work["id"]),
                "attributes": {k: v for k, v in work.items() if k not in ["id", "tenant_id", "created_by"]}
            }
            for work in works_data
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


@router.post("", response_model=WorkResponse, status_code=status.HTTP_201_CREATED)
async def create_work(
    request: WorkCreateRequest,
    session: AsyncSession = Depends(get_db_session),
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: str = Depends(get_current_user_id),
):
    """Create a new musical work."""
    # Validate business rules
    validator = WorkValidator()
    validation_result = validator.validate_work_creation(request.data.attributes.dict(), {"tenant_id": tenant_id})
    
    if not validation_result.is_valid:
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
                    for error in validation_result.errors
                ]
            }
        )
    
    # Create work
    work_data = request.data.attributes.dict()
    writers_data = work_data.pop("writers", [])
    
    work = Work(
        tenant_id=tenant_id,
        created_by=user_id,
        **work_data
    )
    
    # Add writers
    for writer_data in writers_data:
        work_writer = WorkWriter(
            songwriter_id=writer_data["songwriter_id"],
            role=writer_data["role"],
            contribution_percentage=writer_data.get("contribution_percentage")
        )
        work.work_writers.append(work_writer)
    
    session.add(work)
    await session.commit()
    await session.refresh(work)
    
    # Publish event
    event_publisher = get_event_publisher()
    await event_publisher.publish_work_created(work, tenant_id, user_id)
    
    return WorkResponse(
        data={
            "type": "work",
            "id": str(work.id),
            "attributes": {k: v for k, v in work.to_dict().items() if k not in ["id", "tenant_id", "created_by"]}
        }
    )


@router.get("/{work_id}", response_model=WorkResponse)
async def get_work(
    work_id: UUID,
    include: Optional[str] = Query(None, description="Include related resources (writers)"),
    session: AsyncSession = Depends(get_db_session),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Get a specific musical work."""
    query = select(Work).where(
        and_(Work.id == work_id, Work.tenant_id == tenant_id)
    )
    
    if include and "writers" in include:
        query = query.options(selectinload(Work.work_writers).selectinload(WorkWriter.songwriter))
    
    result = await session.execute(query)
    work = result.scalar_one_or_none()
    
    if not work:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Work not found"
        )
    
    work_dict = work.to_dict()
    if include and "writers" in include and work.work_writers:
        work_dict["writers"] = [
            {
                "songwriter_id": str(ww.songwriter_id),
                "songwriter_name": f"{ww.songwriter.first_name} {ww.songwriter.last_name}" if ww.songwriter else None,
                "role": ww.role,
                "contribution_percentage": float(ww.contribution_percentage) if ww.contribution_percentage else None
            }
            for ww in work.work_writers
        ]
    
    return WorkResponse(
        data={
            "type": "work",
            "id": str(work_dict["id"]),
            "attributes": {k: v for k, v in work_dict.items() if k not in ["id", "tenant_id", "created_by"]}
        }
    )


@router.patch("/{work_id}", response_model=WorkResponse)
async def update_work(
    work_id: UUID,
    request: WorkPatchRequest,
    session: AsyncSession = Depends(get_db_session),
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: str = Depends(get_current_user_id),
):
    """Update a musical work (partial update)."""
    # Get existing work
    result = await session.execute(
        select(Work).where(
            and_(Work.id == work_id, Work.tenant_id == tenant_id)
        )
    )
    work = result.scalar_one_or_none()
    
    if not work:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Work not found"
        )
    
    # Update fields
    update_data = request.data.attributes.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(work, field, value)
    
    await session.commit()
    await session.refresh(work)
    
    # Publish event
    event_publisher = get_event_publisher()
    await event_publisher.publish_work_updated(work, tenant_id, user_id)
    
    return WorkResponse(
        data={
            "type": "work",
            "id": str(work.id),
            "attributes": {k: v for k, v in work.to_dict().items() if k not in ["id", "tenant_id", "created_by"]}
        }
    )


@router.delete("/{work_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_work(
    work_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: str = Depends(get_current_user_id),
):
    """Delete a musical work."""
    # Get existing work
    result = await session.execute(
        select(Work).where(
            and_(Work.id == work_id, Work.tenant_id == tenant_id)
        )
    )
    work = result.scalar_one_or_none()
    
    if not work:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Work not found"
        )
    
    # Delete work
    await session.delete(work)
    await session.commit()
    
    # Publish event
    event_publisher = get_event_publisher()
    await event_publisher.publish_work_deleted(work_id, tenant_id, user_id)
    
    return None