"""Recordings API endpoints."""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.dependencies.common import (
    get_current_tenant_id,
    get_current_user_id,
    get_pagination_params,
)
from src.core.database import get_db_session
from src.models.recording import Recording
from src.models.work import Work
from src.schemas.recording import (
    RecordingCreateRequest,
    RecordingResponse,
    RecordingCollectionResponse,
    RecordingUpdateRequest,
    RecordingPatchRequest,
)
from src.services.business_rules import RecordingValidator
from src.services.events import get_event_publisher

router = APIRouter()


@router.get("", response_model=RecordingCollectionResponse)
async def list_recordings(
    # Pagination
    pagination=Depends(get_pagination_params),
    # Filters
    q: Optional[str] = Query(None, description="Search query"),
    work_id: Optional[UUID] = Query(None, description="Filter by work ID"),
    title: Optional[str] = Query(None, description="Filter by title"),
    artist_name: Optional[str] = Query(None, description="Filter by artist name"),
    isrc: Optional[str] = Query(None, description="Filter by ISRC"),
    label: Optional[str] = Query(None, description="Filter by label"),
    # Includes
    include: Optional[str] = Query(None, description="Include related resources (work)"),
    # Dependencies
    session: AsyncSession = Depends(get_db_session),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """List recordings with filtering and pagination."""
    # Build query
    query = session.query(Recording).filter(Recording.tenant_id == tenant_id)
    
    # Apply filters
    if q:
        search_filter = or_(
            Recording.title.ilike(f"%{q}%"),
            Recording.artist_name.ilike(f"%{q}%"),
            Recording.isrc.ilike(f"%{q}%"),
            Recording.label.ilike(f"%{q}%")
        )
        query = query.filter(search_filter)
    
    if work_id:
        query = query.filter(Recording.work_id == work_id)
    
    if title:
        query = query.filter(Recording.title.ilike(f"%{title}%"))
    
    if artist_name:
        query = query.filter(Recording.artist_name.ilike(f"%{artist_name}%"))
    
    if isrc:
        query = query.filter(Recording.isrc == isrc)
    
    if label:
        query = query.filter(Recording.label.ilike(f"%{label}%"))
    
    # Handle includes
    if include and "work" in include:
        query = query.options(selectinload(Recording.work))
    
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
    recordings = result.scalars().all()
    
    # Transform to response
    recordings_data = []
    for recording in recordings:
        recording_dict = recording.to_dict()
        if include and "work" in include and recording.work:
            recording_dict["work"] = {
                "id": str(recording.work.id),
                "title": recording.work.title,
                "iswc": recording.work.iswc
            }
        recordings_data.append(recording_dict)
    
    return RecordingCollectionResponse(
        data=[
            {
                "type": "recording",
                "id": str(recording["id"]),
                "attributes": {k: v for k, v in recording.items() if k not in ["id", "tenant_id", "created_by"]}
            }
            for recording in recordings_data
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


@router.post("", response_model=RecordingResponse, status_code=status.HTTP_201_CREATED)
async def create_recording(
    request: RecordingCreateRequest,
    session: AsyncSession = Depends(get_db_session),
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: str = Depends(get_current_user_id),
):
    """Create a new recording."""
    # Validate business rules
    validator = RecordingValidator()
    validation_result = validator.validate_recording_creation(
        request.data.attributes.dict(), 
        {"tenant_id": tenant_id}
    )
    
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
    
    # Verify work exists and belongs to tenant
    work_id = request.data.attributes.work_id
    result = await session.execute(
        session.query(Work).filter(
            and_(Work.id == work_id, Work.tenant_id == tenant_id)
        )
    )
    work = result.scalar_one_or_none()
    
    if not work:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Work not found or does not belong to tenant"
        )
    
    # Create recording
    recording = Recording(
        tenant_id=tenant_id,
        created_by=user_id,
        **request.data.attributes.dict()
    )
    
    session.add(recording)
    await session.commit()
    await session.refresh(recording)
    
    # Publish event
    event_publisher = get_event_publisher()
    await event_publisher.publish_recording_created(recording, tenant_id, user_id)
    
    return RecordingResponse(
        data={
            "type": "recording",
            "id": str(recording.id),
            "attributes": {k: v for k, v in recording.to_dict().items() if k not in ["id", "tenant_id", "created_by"]}
        }
    )


@router.get("/{recording_id}", response_model=RecordingResponse)
async def get_recording(
    recording_id: UUID,
    include: Optional[str] = Query(None, description="Include related resources (work)"),
    session: AsyncSession = Depends(get_db_session),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Get a specific recording."""
    query = session.query(Recording).filter(
        and_(Recording.id == recording_id, Recording.tenant_id == tenant_id)
    )
    
    if include and "work" in include:
        query = query.options(selectinload(Recording.work))
    
    result = await session.execute(query)
    recording = result.scalar_one_or_none()
    
    if not recording:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recording not found"
        )
    
    recording_dict = recording.to_dict()
    if include and "work" in include and recording.work:
        recording_dict["work"] = {
            "id": str(recording.work.id),
            "title": recording.work.title,
            "iswc": recording.work.iswc
        }
    
    return RecordingResponse(
        data={
            "type": "recording",
            "id": str(recording_dict["id"]),
            "attributes": {k: v for k, v in recording_dict.items() if k not in ["id", "tenant_id", "created_by"]}
        }
    )


@router.patch("/{recording_id}", response_model=RecordingResponse)
async def update_recording(
    recording_id: UUID,
    request: RecordingPatchRequest,
    session: AsyncSession = Depends(get_db_session),
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: str = Depends(get_current_user_id),
):
    """Update a recording (partial update)."""
    # Get existing recording
    result = await session.execute(
        session.query(Recording).filter(
            and_(Recording.id == recording_id, Recording.tenant_id == tenant_id)
        )
    )
    recording = result.scalar_one_or_none()
    
    if not recording:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recording not found"
        )
    
    # Update fields
    update_data = request.data.attributes.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(recording, field, value)
    
    await session.commit()
    await session.refresh(recording)
    
    # Publish event
    event_publisher = get_event_publisher()
    await event_publisher.publish_recording_updated(recording, tenant_id, user_id)
    
    return RecordingResponse(
        data={
            "type": "recording",
            "id": str(recording.id),
            "attributes": {k: v for k, v in recording.to_dict().items() if k not in ["id", "tenant_id", "created_by"]}
        }
    )


@router.delete("/{recording_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_recording(
    recording_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: str = Depends(get_current_user_id),
):
    """Delete a recording."""
    # Get existing recording
    result = await session.execute(
        session.query(Recording).filter(
            and_(Recording.id == recording_id, Recording.tenant_id == tenant_id)
        )
    )
    recording = result.scalar_one_or_none()
    
    if not recording:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recording not found"
        )
    
    # Delete recording
    await session.delete(recording)
    await session.commit()
    
    # Publish event
    event_publisher = get_event_publisher()
    await event_publisher.publish_recording_deleted(recording_id, tenant_id, user_id)
    
    return None