"""Authentication middleware and dependencies."""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from starlette.middleware.base import BaseHTTPMiddleware

from src.core.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Security components
security = HTTPBearer(auto_error=False)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Import enhanced authentication for new functionality
try:
    from .enhanced_auth import (
        EnhancedAuthenticationMiddleware,
        get_current_user_id as enhanced_get_current_user_id,
        get_current_publisher_id as enhanced_get_current_publisher_id,
        get_current_permissions,
        get_token_type,
        require_permission,
        require_publisher_access,
        require_token_type
    )
    ENHANCED_AUTH_AVAILABLE = True
except ImportError:
    ENHANCED_AUTH_AVAILABLE = False
    logger.warning("Enhanced authentication not available, falling back to basic auth")


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """
    Middleware to handle JWT authentication for all requests.
    Can be disabled for development/testing.
    """

    EXEMPT_PATHS = {
        "/health",
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
            # Set a default user context for development
            request.state.user_id = "dev-user-id"
            request.state.user_email = "dev@example.com"
            request.state.user_roles = ["admin"]
            return await call_next(request)

        # Extract authorization header
        authorization = request.headers.get("Authorization")
        if not authorization:
            logger.warning(f"Missing Authorization header for {request.url.path}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error": "missing_authorization",
                    "message": "Authorization header is required",
                    "code": "AUTHORIZATION_REQUIRED"
                },
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Validate Bearer token format
        if not authorization.startswith("Bearer "):
            logger.warning(f"Invalid authorization format for {request.url.path}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error": "invalid_authorization_format",
                    "message": "Authorization must be in 'Bearer <token>' format",
                    "code": "INVALID_AUTHORIZATION_FORMAT"
                },
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Extract token
        token = authorization.split(" ")[1]
        
        try:
            # Decode and validate JWT token
            payload = jwt.decode(
                token,
                settings.jwt_secret_key,
                algorithms=[settings.jwt_algorithm]
            )
            
            # Extract user information from token
            user_id = payload.get("sub")
            if not user_id:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail={
                        "error": "invalid_token_payload",
                        "message": "Token must contain 'sub' claim",
                        "code": "INVALID_TOKEN_PAYLOAD"
                    }
                )

            # Validate UUID format for user_id
            try:
                uuid.UUID(user_id)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail={
                        "error": "invalid_user_id",
                        "message": "User ID must be a valid UUID",
                        "code": "INVALID_USER_ID"
                    }
                )

            # Store user context in request state
            request.state.user_id = user_id
            request.state.user_email = payload.get("email", "")
            request.state.user_roles = payload.get("roles", [])
            request.state.token_exp = payload.get("exp", 0)

            logger.debug(f"Authenticated user {user_id} for {request.url.path}")

        except JWTError as e:
            logger.warning(f"JWT validation failed for {request.url.path}: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error": "invalid_token",
                    "message": "Invalid or expired JWT token",
                    "code": "INVALID_JWT_TOKEN"
                },
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Process the request
        response = await call_next(request)
        
        return response


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            minutes=settings.jwt_access_token_expire_minutes
        )
    
    to_encode.update({"exp": expire})
    
    encoded_jwt = jwt.encode(
        to_encode, 
        settings.jwt_secret_key, 
        algorithm=settings.jwt_algorithm
    )
    
    return encoded_jwt


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Generate password hash."""
    return pwd_context.hash(password)


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


def get_current_user_email(request: Request) -> str:
    """Extract current user email from request state."""
    if not hasattr(request.state, "user_email"):
        raise HTTPException(
            status_code=500,
            detail={
                "error": "user_context_missing",
                "message": "User context not established",
                "code": "USER_CONTEXT_ERROR"
            }
        )
    return request.state.user_email


def get_current_user_roles(request: Request) -> list:
    """Extract current user roles from request state."""
    if not hasattr(request.state, "user_roles"):
        raise HTTPException(
            status_code=500,
            detail={
                "error": "user_context_missing", 
                "message": "User context not established",
                "code": "USER_CONTEXT_ERROR"
            }
        )
    return request.state.user_roles


def require_role(required_role: str):
    """Dependency to require specific user role."""
    def role_checker(request: Request) -> bool:
        user_roles = get_current_user_roles(request)
        if required_role not in user_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "insufficient_permissions",
                    "message": f"Role '{required_role}' is required",
                    "code": "INSUFFICIENT_PERMISSIONS"
                }
            )
        return True
    return role_checker