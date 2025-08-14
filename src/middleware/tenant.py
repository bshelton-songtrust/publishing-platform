"""Tenant context middleware for multi-tenant isolation."""

import logging
import uuid
from typing import Optional

from fastapi import HTTPException, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.core.database import set_tenant_context

logger = logging.getLogger(__name__)


class TenantContextMiddleware(BaseHTTPMiddleware):
    """
    Middleware to establish tenant context for all requests.
    Validates tenant ID and sets up Row-Level Security context.
    """

    EXEMPT_PATHS = {
        "/",
        "/health",
        "/health/database",
        "/health/dependencies", 
        "/version",
        "/openapi.json", 
        "/docs",
        "/redoc",
        "/favicon.ico"
    }

    async def dispatch(self, request: Request, call_next):
        """Process request and set tenant context."""
        # Skip tenant validation for exempt paths
        if request.url.path in self.EXEMPT_PATHS:
            return await call_next(request)

        # Extract tenant ID from header
        tenant_id = request.headers.get("X-Tenant-ID")
        if not tenant_id:
            logger.warning(f"Missing X-Tenant-ID header for {request.url.path}")
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "missing_tenant_id",
                    "message": "X-Tenant-ID header is required",
                    "code": "TENANT_ID_REQUIRED"
                }
            )

        # Validate UUID format
        try:
            tenant_uuid = uuid.UUID(tenant_id)
        except ValueError:
            logger.warning(f"Invalid tenant ID format: {tenant_id}")
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "invalid_tenant_id",
                    "message": "X-Tenant-ID must be a valid UUID",
                    "code": "INVALID_TENANT_ID_FORMAT"
                }
            )

        # Store tenant context in request state
        request.state.tenant_id = str(tenant_uuid)
        
        logger.debug(f"Set tenant context: {tenant_id} for {request.url.path}")

        # Process the request
        response = await call_next(request)
        
        # Add tenant ID to response headers for debugging
        response.headers["X-Tenant-ID"] = str(tenant_uuid)
        
        return response


def get_tenant_id(request: Request) -> str:
    """Extract tenant ID from request state."""
    if not hasattr(request.state, "tenant_id"):
        raise HTTPException(
            status_code=500,
            detail={
                "error": "tenant_context_missing",
                "message": "Tenant context not established",
                "code": "TENANT_CONTEXT_ERROR"
            }
        )
    return request.state.tenant_id


def get_optional_tenant_id(request: Request) -> Optional[str]:
    """Extract tenant ID from request state if available."""
    return getattr(request.state, "tenant_id", None)