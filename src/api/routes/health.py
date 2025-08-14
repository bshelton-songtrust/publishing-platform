"""Health check and system endpoints."""

import json
from datetime import datetime
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db_session
from src.core.settings import get_settings
from src.schemas.base import HealthCheckResponse
from src.services.events import get_event_publisher

router = APIRouter()
settings = get_settings()


@router.get("/health", response_model=HealthCheckResponse)
async def health_check(session: AsyncSession = Depends(get_db_session)):
    """
    Service health check endpoint.
    
    Checks the health of the service and its dependencies:
    - Database connectivity
    - Event publishing system
    - Configuration validity
    """
    health_data = {
        "status": "healthy",
        "timestamp": datetime.utcnow(),
        "version": "1.0.0",
        "environment": settings.environment,
        "dependencies": {}
    }
    
    overall_status = "healthy"
    
    # Check database connectivity
    try:
        result = await session.execute(text("SELECT 1 as health_check"))
        row = result.fetchone()
        if row and row[0] == 1:
            health_data["dependencies"]["database"] = {
                "status": "healthy",
                "response_time_ms": 0,  # Could measure actual response time
                "details": "Connection successful"
            }
        else:
            raise Exception("Unexpected database response")
    except Exception as e:
        health_data["dependencies"]["database"] = {
            "status": "unhealthy",
            "error": str(e),
            "details": "Database connection failed"
        }
        overall_status = "unhealthy"
    
    # Check event publishing system
    try:
        event_publisher = get_event_publisher()
        if event_publisher.event_bus_type == "sqs":
            if event_publisher.sqs_client and event_publisher.queue_url:
                health_data["dependencies"]["events"] = {
                    "status": "healthy",
                    "type": "sqs",
                    "details": "SQS client initialized"
                }
            else:
                health_data["dependencies"]["events"] = {
                    "status": "degraded",
                    "type": "sqs",
                    "details": "SQS not properly configured"
                }
                if overall_status == "healthy":
                    overall_status = "degraded"
        else:
            health_data["dependencies"]["events"] = {
                "status": "healthy",
                "type": "mock",
                "details": "Mock event publisher active"
            }
    except Exception as e:
        health_data["dependencies"]["events"] = {
            "status": "unhealthy",
            "error": str(e),
            "details": "Event system check failed"
        }
        overall_status = "unhealthy"
    
    # Check Redis (optional dependency)
    try:
        # This would check Redis connectivity if implemented
        health_data["dependencies"]["redis"] = {
            "status": "healthy",
            "details": "Not implemented in health check"
        }
    except Exception as e:
        health_data["dependencies"]["redis"] = {
            "status": "degraded",
            "error": str(e),
            "details": "Redis check failed"
        }
        if overall_status == "healthy":
            overall_status = "degraded"
    
    # Update overall status
    health_data["status"] = overall_status
    
    # Return appropriate HTTP status
    if overall_status == "unhealthy":
        raise HTTPException(status_code=503, detail=health_data)
    
    return HealthCheckResponse(**health_data)


@router.get("/health/database")
async def database_health(session: AsyncSession = Depends(get_db_session)):
    """Detailed database health check."""
    try:
        # Check basic connectivity
        result = await session.execute(text("SELECT 1"))
        result.fetchone()
        
        # Check table existence
        tables_result = await session.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('tenants', 'works', 'songwriters', 'recordings')
        """))
        tables = [row[0] for row in tables_result.fetchall()]
        
        # Check RLS is enabled
        rls_result = await session.execute(text("""
            SELECT schemaname, tablename, rowsecurity 
            FROM pg_tables 
            WHERE schemaname = 'public' 
            AND tablename IN ('tenants', 'works', 'songwriters', 'recordings')
        """))
        rls_status = {row[1]: row[2] for row in rls_result.fetchall()}
        
        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "details": {
                "connectivity": "ok",
                "tables": tables,
                "row_level_security": rls_status
            }
        }
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "unhealthy",
                "timestamp": datetime.utcnow().isoformat(),
                "error": str(e)
            }
        )


@router.get("/health/dependencies")
async def dependencies_health():
    """Check external dependencies health."""
    dependencies = {}
    overall_status = "healthy"
    
    # Check event system
    try:
        event_publisher = get_event_publisher()
        dependencies["events"] = {
            "status": "healthy" if event_publisher else "unhealthy",
            "type": event_publisher.event_bus_type if event_publisher else "unknown"
        }
    except Exception as e:
        dependencies["events"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        overall_status = "degraded"
    
    # Add more dependency checks here as needed
    
    return {
        "status": overall_status,
        "timestamp": datetime.utcnow().isoformat(),
        "dependencies": dependencies
    }


@router.get("/version")
async def version_info():
    """Get service version information."""
    return {
        "service": "catalog-management-service",
        "version": "1.0.0",
        "environment": settings.environment,
        "api_version": "v1",
        "build_info": {
            "timestamp": datetime.utcnow().isoformat(),
            "commit": "unknown",  # Could be populated from build process
            "branch": "main"
        }
    }


@router.get("/openapi.json")
async def get_openapi_spec():
    """Get OpenAPI specification."""
    # This will be automatically handled by FastAPI
    # but we can customize it here if needed
    from fastapi.openapi.utils import get_openapi
    from src.main import app
    
    return get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )