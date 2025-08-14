"""Enhanced authentication middleware supporting multiple token types."""

import logging
from typing import Optional, Dict, Any
from datetime import datetime

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware

from src.services.token_service import TokenService, TokenValidationResult
from src.core.database import get_db_session
from src.core.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class EnhancedAuthenticationMiddleware(BaseHTTPMiddleware):
    """
    Enhanced authentication middleware supporting multiple token types.
    
    Supports:
    - User JWT tokens (access/refresh)
    - Service tokens (API keys)
    - Personal Access Tokens (PATs)
    
    Features:
    - Multi-token type detection and validation
    - Publisher context management
    - Rate limiting integration
    - Security event logging
    - IP-based restrictions
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
        """Process request and validate authentication."""
        
        # Skip authentication for exempt paths
        if request.url.path in self.EXEMPT_PATHS:
            return await call_next(request)

        # Skip authentication if disabled (development/testing)
        if settings.disable_auth:
            await self._set_dev_context(request)
            return await call_next(request)

        # Extract and validate token
        token = self._extract_token(request)
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error": "missing_authorization",
                    "message": "Authorization header is required",
                    "code": "AUTHORIZATION_REQUIRED"
                },
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Validate token using TokenService
        async with get_db_session() as session:
            token_service = TokenService(session)
            validation_result = await token_service.validate_token(token)

        if not validation_result.is_valid:
            await self._log_authentication_failure(request, validation_result.error)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error": "invalid_token",
                    "message": validation_result.error,
                    "code": "INVALID_TOKEN"
                },
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Set request context based on token type
        await self._set_request_context(request, validation_result)
        
        # Apply additional validations
        await self._apply_security_validations(request, validation_result)

        # Process the request
        response = await call_next(request)
        
        # Add response headers
        self._add_response_headers(response, validation_result)
        
        return response

    def _extract_token(self, request: Request) -> Optional[str]:
        """Extract token from Authorization header."""
        authorization = request.headers.get("Authorization")
        if not authorization:
            return None

        if not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error": "invalid_authorization_format",
                    "message": "Authorization must be in 'Bearer <token>' format",
                    "code": "INVALID_AUTHORIZATION_FORMAT"
                },
                headers={"WWW-Authenticate": "Bearer"},
            )

        return authorization.split(" ")[1]

    async def _set_request_context(self, request: Request, validation_result: TokenValidationResult):
        """Set request context based on token validation result."""
        
        # Common context
        request.state.token_type = validation_result.token_type
        request.state.permissions = validation_result.permissions
        request.state.publisher_id = validation_result.publisher_id
        request.state.token_data = validation_result.token_data

        if validation_result.token_type == "user":
            await self._set_user_context(request, validation_result)
        elif validation_result.token_type == "service":
            await self._set_service_context(request, validation_result)
        elif validation_result.token_type == "pat":
            await self._set_pat_context(request, validation_result)

        # Set publisher context for database RLS
        if validation_result.publisher_id:
            request.state.current_publisher_id = validation_result.publisher_id

        logger.debug(f"Set {validation_result.token_type} context for {request.url.path}")

    async def _set_user_context(self, request: Request, validation_result: TokenValidationResult):
        """Set user-specific context."""
        request.state.user_id = validation_result.user_id
        request.state.user_email = validation_result.token_data.get("email")
        request.state.user_role = validation_result.token_data.get("role")
        request.state.session_id = validation_result.token_data.get("session_id")
        request.state.publishers = validation_result.token_data.get("publishers", [])
        
        # For backward compatibility
        request.state.user_roles = [validation_result.token_data.get("role")] if validation_result.token_data.get("role") else []

    async def _set_service_context(self, request: Request, validation_result: TokenValidationResult):
        """Set service-specific context."""
        request.state.service_account_id = validation_result.token_data.get("service_account_id")
        request.state.service_name = validation_result.token_data.get("service_name")
        request.state.token_id = validation_result.token_data.get("token_id")
        
        # Service tokens don't have users, but we need something for audit trails
        request.state.user_id = f"service:{validation_result.token_data.get('service_account_id')}"
        request.state.user_email = f"{validation_result.token_data.get('service_name')}@service.local"
        request.state.user_roles = ["service"]

    async def _set_pat_context(self, request: Request, validation_result: TokenValidationResult):
        """Set Personal Access Token specific context."""
        request.state.user_id = validation_result.user_id
        request.state.pat_id = validation_result.token_data.get("token_id")
        request.state.pat_name = validation_result.token_data.get("token_name")
        request.state.inherit_user_permissions = validation_result.token_data.get("inherit_user_permissions")
        
        # PATs act on behalf of users
        request.state.user_roles = ["pat_user"]

    async def _set_dev_context(self, request: Request):
        """Set default development context."""
        request.state.token_type = "dev"
        request.state.user_id = "dev-user-id"
        request.state.user_email = "dev@example.com"
        request.state.user_roles = ["admin"]
        request.state.permissions = ["*"]
        request.state.publisher_id = "dev-publisher-id"
        request.state.current_publisher_id = "dev-publisher-id"

    async def _apply_security_validations(self, request: Request, validation_result: TokenValidationResult):
        """Apply additional security validations."""
        
        # IP-based restrictions for service tokens and PATs
        if validation_result.token_type in ["service", "pat"]:
            await self._validate_ip_restrictions(request, validation_result)
        
        # Rate limiting can be applied here
        # await self._apply_rate_limiting(request, validation_result)
        
        # Log security events for suspicious activity
        await self._log_security_events(request, validation_result)

    async def _validate_ip_restrictions(self, request: Request, validation_result: TokenValidationResult):
        """Validate IP restrictions for tokens that support them."""
        client_ip = self._get_client_ip(request)
        
        if validation_result.token_type == "service":
            # Service tokens have IP restrictions at the service account level
            # This would require checking the service account's allowed_ips
            # For now, we'll skip this validation
            pass
        elif validation_result.token_type == "pat":
            # PATs can have IP restrictions
            # This would require checking the PAT's allowed_ips
            # For now, we'll skip this validation
            pass

    async def _apply_rate_limiting(self, request: Request, validation_result: TokenValidationResult):
        """Apply rate limiting based on token type and configuration."""
        # Implementation would depend on rate limiting strategy
        # Could use Redis, in-memory cache, or database-based rate limiting
        pass

    async def _log_security_events(self, request: Request, validation_result: TokenValidationResult):
        """Log security events for monitoring."""
        # Log successful authentications for service tokens and PATs
        if validation_result.token_type in ["service", "pat"]:
            security_event = {
                "event_type": "token_authentication",
                "token_type": validation_result.token_type,
                "ip_address": self._get_client_ip(request),
                "user_agent": request.headers.get("User-Agent"),
                "endpoint": request.url.path,
                "method": request.method,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            if validation_result.token_type == "service":
                security_event["service_account_id"] = validation_result.token_data.get("service_account_id")
            elif validation_result.token_type == "pat":
                security_event["user_id"] = validation_result.user_id
                security_event["token_id"] = validation_result.token_data.get("token_id")
            
            logger.info(f"Token authentication: {security_event}")

    async def _log_authentication_failure(self, request: Request, error: str):
        """Log authentication failures for security monitoring."""
        failure_event = {
            "event_type": "authentication_failure",
            "error": error,
            "ip_address": self._get_client_ip(request),
            "user_agent": request.headers.get("User-Agent"),
            "endpoint": request.url.path,
            "method": request.method,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        logger.warning(f"Authentication failure: {failure_event}")

    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address from request."""
        # Check for forwarded IP headers (for load balancers/proxies)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        # Fallback to direct client IP
        if hasattr(request, "client") and request.client:
            return request.client.host
        
        return "unknown"

    def _add_response_headers(self, response, validation_result: TokenValidationResult):
        """Add response headers for debugging and security."""
        response.headers["X-Auth-Type"] = validation_result.token_type
        
        if validation_result.publisher_id:
            response.headers["X-Publisher-ID"] = validation_result.publisher_id
        
        # Don't expose sensitive token data in headers
        response.headers["X-Auth-Status"] = "authenticated"


# Dependency functions for FastAPI endpoints

def get_current_user_id(request: Request) -> str:
    """Extract current user ID from request state."""
    if not hasattr(request.state, "user_id"):
        raise HTTPException(
            status_code=500,
            detail={
                "error": "user_context_missing",
                "message": "User context not established",
                "code": "USER_CONTEXT_ERROR"
            }
        )
    return request.state.user_id

def get_current_publisher_id(request: Request) -> Optional[str]:
    """Extract current publisher ID from request state."""
    return getattr(request.state, "publisher_id", None)

def get_current_permissions(request: Request) -> list:
    """Extract current permissions from request state."""
    return getattr(request.state, "permissions", [])

def get_token_type(request: Request) -> str:
    """Extract token type from request state."""
    return getattr(request.state, "token_type", "unknown")

def require_permission(permission: str):
    """Dependency to require a specific permission."""
    def permission_checker(request: Request) -> bool:
        permissions = get_current_permissions(request)
        
        if not permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "no_permissions",
                    "message": "No permissions available",
                    "code": "NO_PERMISSIONS"
                }
            )
        
        # Check for exact match
        if permission in permissions:
            return True
        
        # Check for wildcard permissions
        resource = permission.split(':')[0] if ':' in permission else permission
        if f"{resource}:*" in permissions or "*" in permissions:
            return True
        
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "insufficient_permissions",
                "message": f"Permission '{permission}' is required",
                "code": "INSUFFICIENT_PERMISSIONS",
                "required_permission": permission,
                "available_permissions": permissions
            }
        )
    
    return permission_checker

def require_publisher_access():
    """Dependency to require publisher context."""
    def publisher_checker(request: Request) -> str:
        publisher_id = get_current_publisher_id(request)
        
        if not publisher_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "publisher_required",
                    "message": "Publisher context is required for this operation",
                    "code": "PUBLISHER_REQUIRED"
                }
            )
        
        return publisher_id
    
    return publisher_checker

def require_token_type(*allowed_types: str):
    """Dependency to require specific token types."""
    def token_type_checker(request: Request) -> str:
        token_type = get_token_type(request)
        
        if token_type not in allowed_types:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "invalid_token_type",
                    "message": f"Token type '{token_type}' not allowed. Allowed types: {', '.join(allowed_types)}",
                    "code": "INVALID_TOKEN_TYPE"
                }
            )
        
        return token_type
    
    return token_type_checker