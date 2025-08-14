"""Logging middleware for request/response tracking."""

import json
import logging
import time
import uuid
from typing import Callable

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.core.settings import get_settings

settings = get_settings()


# Configure structured logging
def configure_logging():
    """Configure structured logging with JSON output."""
    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, settings.log_level),
    )
    
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to log all requests and responses with structured logging.
    Includes performance metrics and contextual information.
    """

    def __init__(self, app, logger_name: str = "catalog.http"):
        super().__init__(app)
        self.logger = structlog.get_logger(logger_name)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with comprehensive logging."""
        # Generate unique request ID
        request_id = str(uuid.uuid4())
        
        # Start timing
        start_time = time.time()
        
        # Extract request information
        method = request.method
        url = str(request.url)
        path = request.url.path
        query_params = dict(request.query_params)
        headers = dict(request.headers)
        
        # Extract contextual information
        tenant_id = getattr(request.state, "tenant_id", None)
        user_id = getattr(request.state, "user_id", None)
        user_agent = headers.get("user-agent", "")
        client_ip = self._get_client_ip(request)
        
        # Prepare request log data
        request_data = {
            "request_id": request_id,
            "method": method,
            "path": path,
            "query_params": query_params,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "client_ip": client_ip,
            "user_agent": user_agent,
        }
        
        # Log sensitive headers only in debug mode
        if settings.debug:
            request_data["headers"] = self._sanitize_headers(headers)
        
        self.logger.info("HTTP request started", **request_data)
        
        # Store request context
        request.state.request_id = request_id
        request.state.start_time = start_time
        
        # Process request
        try:
            response = await call_next(request)
            
            # Calculate response time
            process_time = time.time() - start_time
            
            # Prepare response log data
            response_data = {
                "request_id": request_id,
                "method": method,
                "path": path,
                "status_code": response.status_code,
                "process_time_ms": round(process_time * 1000, 2),
                "tenant_id": tenant_id,
                "user_id": user_id,
                "client_ip": client_ip,
            }
            
            # Log response with appropriate level based on status code
            if 200 <= response.status_code < 400:
                self.logger.info("HTTP request completed successfully", **response_data)
            elif 400 <= response.status_code < 500:
                self.logger.warning("HTTP request completed with client error", **response_data)
            else:
                self.logger.error("HTTP request completed with server error", **response_data)
            
            # Add response headers
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time"] = str(process_time)
            
            return response
            
        except Exception as e:
            # Calculate error response time
            process_time = time.time() - start_time
            
            # Log error
            error_data = {
                "request_id": request_id,
                "method": method,
                "path": path,
                "error_type": type(e).__name__,
                "error_message": str(e),
                "process_time_ms": round(process_time * 1000, 2),
                "tenant_id": tenant_id,
                "user_id": user_id,
                "client_ip": client_ip,
            }
            
            self.logger.error("HTTP request failed with exception", **error_data)
            
            # Re-raise the exception
            raise

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP address with proxy support."""
        # Check for forwarded headers
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            # Take the first IP in the chain
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip
        
        # Fall back to direct client IP
        if hasattr(request, "client") and request.client:
            return request.client.host
        
        return "unknown"

    def _sanitize_headers(self, headers: dict) -> dict:
        """Remove sensitive information from headers."""
        sensitive_headers = {
            "authorization",
            "cookie",
            "x-api-key",
            "x-auth-token",
        }
        
        sanitized = {}
        for key, value in headers.items():
            if key.lower() in sensitive_headers:
                sanitized[key] = "[REDACTED]"
            else:
                sanitized[key] = value
        
        return sanitized


def get_request_logger(request: Request) -> structlog.BoundLogger:
    """Get a logger bound with request context."""
    logger = structlog.get_logger("catalog.request")
    
    # Bind contextual information
    context = {
        "request_id": getattr(request.state, "request_id", "unknown"),
        "tenant_id": getattr(request.state, "tenant_id", None),
        "user_id": getattr(request.state, "user_id", None),
        "path": request.url.path,
    }
    
    return logger.bind(**context)


# Initialize logging configuration
configure_logging()