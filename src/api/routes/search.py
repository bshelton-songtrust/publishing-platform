"""Search API endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies.common import get_current_tenant_id
from src.core.database import get_db_session
from src.models.work import Work
from src.models.songwriter import Songwriter
from src.models.recording import Recording
from src.schemas.search import SearchResponse, SearchResultItem

router = APIRouter()


@router.get("/works", response_model=SearchResponse)
async def search_works(
    q: str = Query(..., min_length=2, description="Search query"),
    limit: int = Query(10, ge=1, le=100, description="Maximum results"),
    session: AsyncSession = Depends(get_db_session),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Search for musical works."""
    # Build search filter
    search_filter = or_(
        Work.title.ilike(f"%{q}%"),
        Work.iswc.ilike(f"%{q}%"),
        Work.description.ilike(f"%{q}%"),
        Work.genre.ilike(f"%{q}%")
    )
    
    # Execute search
    query = session.query(Work).filter(
        Work.tenant_id == tenant_id,
        search_filter
    ).limit(limit)
    
    result = await session.execute(query)
    works = result.scalars().all()
    
    # Transform results
    results = [
        SearchResultItem(
            type="work",
            id=str(work.id),
            title=work.title,
            subtitle=f"ISWC: {work.iswc}" if work.iswc else f"Genre: {work.genre}",
            description=work.description,
            score=1.0  # Could be actual relevance score
        )
        for work in works
    ]
    
    return SearchResponse(
        query=q,
        total=len(results),
        results=results
    )


@router.get("/songwriters", response_model=SearchResponse)
async def search_songwriters(
    q: str = Query(..., min_length=2, description="Search query"),
    limit: int = Query(10, ge=1, le=100, description="Maximum results"),
    session: AsyncSession = Depends(get_db_session),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Search for songwriters."""
    # Build search filter
    search_filter = or_(
        Songwriter.first_name.ilike(f"%{q}%"),
        Songwriter.last_name.ilike(f"%{q}%"),
        Songwriter.stage_name.ilike(f"%{q}%"),
        Songwriter.full_name.ilike(f"%{q}%"),
        Songwriter.ipi.ilike(f"%{q}%")
    )
    
    # Execute search
    query = session.query(Songwriter).filter(
        Songwriter.tenant_id == tenant_id,
        search_filter
    ).limit(limit)
    
    result = await session.execute(query)
    songwriters = result.scalars().all()
    
    # Transform results
    results = [
        SearchResultItem(
            type="songwriter",
            id=str(songwriter.id),
            title=songwriter.full_name or f"{songwriter.first_name} {songwriter.last_name}",
            subtitle=songwriter.stage_name or (f"IPI: {songwriter.ipi}" if songwriter.ipi else ""),
            description=songwriter.biography,
            score=1.0
        )
        for songwriter in songwriters
    ]
    
    return SearchResponse(
        query=q,
        total=len(results),
        results=results
    )


@router.get("/recordings", response_model=SearchResponse)
async def search_recordings(
    q: str = Query(..., min_length=2, description="Search query"),
    limit: int = Query(10, ge=1, le=100, description="Maximum results"),
    session: AsyncSession = Depends(get_db_session),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Search for recordings."""
    # Build search filter
    search_filter = or_(
        Recording.title.ilike(f"%{q}%"),
        Recording.artist_name.ilike(f"%{q}%"),
        Recording.isrc.ilike(f"%{q}%"),
        Recording.label.ilike(f"%{q}%")
    )
    
    # Execute search
    query = session.query(Recording).filter(
        Recording.tenant_id == tenant_id,
        search_filter
    ).limit(limit)
    
    result = await session.execute(query)
    recordings = result.scalars().all()
    
    # Transform results
    results = [
        SearchResultItem(
            type="recording",
            id=str(recording.id),
            title=recording.title,
            subtitle=f"Artist: {recording.artist_name}",
            description=f"Label: {recording.label}" if recording.label else f"ISRC: {recording.isrc}" if recording.isrc else "",
            score=1.0
        )
        for recording in recordings
    ]
    
    return SearchResponse(
        query=q,
        total=len(results),
        results=results
    )


@router.get("/all", response_model=SearchResponse)
async def search_all(
    q: str = Query(..., min_length=2, description="Search query"),
    limit: int = Query(10, ge=1, le=100, description="Maximum results per type"),
    session: AsyncSession = Depends(get_db_session),
    tenant_id: str = Depends(get_current_tenant_id),
):
    """Search across all entity types."""
    results = []
    
    # Search works
    works_response = await search_works(q, limit, session, tenant_id)
    results.extend(works_response.results)
    
    # Search songwriters
    songwriters_response = await search_songwriters(q, limit, session, tenant_id)
    results.extend(songwriters_response.results)
    
    # Search recordings
    recordings_response = await search_recordings(q, limit, session, tenant_id)
    results.extend(recordings_response.results)
    
    # Sort by score (all 1.0 for now, but could be improved)
    results.sort(key=lambda r: r.score, reverse=True)
    
    return SearchResponse(
        query=q,
        total=len(results),
        results=results[:limit * 3]  # Limit total results
    )