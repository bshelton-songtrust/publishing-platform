"""Main FastAPI application for Catalog Management Service."""

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

from src.api.routes import health, works, songwriters, recordings, search, publishers
from src.core.database import get_database
from src.core.settings import get_settings
from src.middleware.auth import AuthenticationMiddleware
from src.middleware.logging import LoggingMiddleware, configure_logging
from src.middleware.rate_limiting import RateLimitMiddleware
from src.middleware.tenant import TenantContextMiddleware

# Initialize logging
configure_logging()

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management."""
    # Startup
    await get_database().connect()
    yield
    # Shutdown
    await get_database().disconnect()


app = FastAPI(
    title="Catalog Management Service",
    description="Musical works and recordings management service for Downtown Music Publishing",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
    openapi_url="/openapi.json" if not settings.is_production else None,
)

# Security middleware
app.add_middleware(
    TrustedHostMiddleware, 
    allowed_hosts=settings.allowed_hosts
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["*"],
)

# Custom middleware stack (order matters!)
app.add_middleware(LoggingMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(AuthenticationMiddleware)
app.add_middleware(TenantContextMiddleware)


# Exception handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions with JSON:API format."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "errors": [{
                "status": str(exc.status_code),
                "code": exc.detail.get("code", "HTTP_ERROR") if isinstance(exc.detail, dict) else "HTTP_ERROR",
                "title": exc.detail.get("message", "HTTP Error") if isinstance(exc.detail, dict) else str(exc.detail),
                "detail": exc.detail.get("message", str(exc.detail)) if isinstance(exc.detail, dict) else str(exc.detail),
                "source": {"pointer": request.url.path}
            }]
        }
    )


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    """Handle 404 errors with JSON:API format."""
    return JSONResponse(
        status_code=404,
        content={
            "errors": [{
                "status": "404",
                "code": "RESOURCE_NOT_FOUND",
                "title": "Resource Not Found",
                "detail": f"The requested resource was not found",
                "source": {"pointer": request.url.path}
            }]
        }
    )


@app.exception_handler(500)
async def internal_error_handler(request: Request, exc):
    """Handle 500 errors with JSON:API format."""
    return JSONResponse(
        status_code=500,
        content={
            "errors": [{
                "status": "500",
                "code": "INTERNAL_SERVER_ERROR",
                "title": "Internal Server Error", 
                "detail": "An unexpected error occurred"
            }]
        }
    )


# Routes
app.include_router(health.router, prefix="", tags=["system"])


# Placeholder routes for main functionality
@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "catalog-management-service",
        "version": "1.0.0",
        "status": "running",
        "api": {
            "docs": f"/docs" if not settings.is_production else None,
            "openapi": "/openapi.json" if not settings.is_production else None
        }
    }


# Main API routes
app.include_router(publishers.router, prefix="/api/v1/publishers", tags=["publishers"])
app.include_router(works.router, prefix="/api/v1/works", tags=["works"])
app.include_router(songwriters.router, prefix="/api/v1/songwriters", tags=["songwriters"])
app.include_router(recordings.router, prefix="/api/v1/recordings", tags=["recordings"])
app.include_router(search.router, prefix="/api/v1/search", tags=["search"])


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.is_development,
        log_level=settings.log_level.lower(),
    )