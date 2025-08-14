"""Common FastAPI dependencies."""

from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db_session, set_tenant_context
from src.core.settings import get_settings


async def get_db_with_tenant_context(
    request: Request,
    session: AsyncSession = Depends(get_db_session)
) -> AsyncSession:
    """Get database session with tenant context set."""
    tenant_id = getattr(request.state, "tenant_id", None)
    if tenant_id:
        await set_tenant_context(session, tenant_id)
    return session


def get_current_tenant_id(request: Request) -> str:
    """Get current tenant ID from request."""
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(
            status_code=400,
            detail="Missing tenant context"
        )
    return tenant_id


def get_current_user_id(request: Request) -> str:
    """Get current user ID from request."""
    # For development with DISABLE_AUTH=true, return a default user ID
    settings = get_settings()
    if settings.disable_auth:
        return "00000000-0000-0000-0000-000000000000"
    
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="User not authenticated"
        )
    return user_id


def get_pagination_params(
    page: int = Query(1, ge=1, le=1000, description="Page number"),
    per_page: int = Query(25, ge=1, le=100, description="Items per page"),
    sort_by: Optional[str] = Query(None, description="Sort field"),
    sort_order: str = Query("asc", regex="^(asc|desc)$", description="Sort order")
) -> dict:
    """Get pagination parameters from query string."""
    return {
        "page": page,
        "per_page": per_page,
        "offset": (page - 1) * per_page,
        "limit": per_page,
        "sort_by": sort_by,
        "sort_order": sort_order
    }


def get_fields_param(
    fields: Optional[str] = Query(None, description="Sparse fieldsets (comma-separated)")
) -> Optional[dict]:
    """Parse sparse fieldsets parameter."""
    if not fields:
        return None
    
    # Parse fields parameter: fields[type]=field1,field2
    # For now, simple comma-separated implementation
    field_list = [f.strip() for f in fields.split(",")]
    return {"default": field_list} if field_list else None


def get_include_param(
    include: Optional[str] = Query(None, description="Related resources to include (comma-separated)")
) -> Optional[list]:
    """Parse include parameter for related resources."""
    if not include:
        return None
    
    include_list = [i.strip() for i in include.split(",")]
    return include_list if include_list else None


def validate_uuid_param(uuid_str: str, param_name: str = "id") -> UUID:
    """Validate and parse UUID parameter."""
    try:
        return UUID(uuid_str)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_uuid",
                "message": f"Invalid UUID format for {param_name}",
                "code": "INVALID_UUID_FORMAT"
            }
        )