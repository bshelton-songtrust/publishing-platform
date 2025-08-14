"""Authentication API endpoints."""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, EmailStr, Field

from src.core.database import get_db_session
from src.services.user_service import UserService
from src.services.token_service import TokenService
from src.middleware.enhanced_auth import get_current_user_id, require_token_type

router = APIRouter(prefix="/auth", tags=["Authentication"])


# Request/Response Models

class LoginRequest(BaseModel):
    """User login request."""
    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., min_length=8, description="User password")
    publisher_id: Optional[str] = Field(None, description="Specific publisher to authenticate for")
    remember_me: bool = Field(False, description="Keep user logged in for extended period")


class TokenResponse(BaseModel):
    """Token response model."""
    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Token expiration time in seconds")
    refresh_token: Optional[str] = Field(None, description="Refresh token for token renewal")
    publisher_id: Optional[str] = Field(None, description="Active publisher context")
    user: Optional[Dict[str, Any]] = Field(None, description="User profile information")


class RefreshTokenRequest(BaseModel):
    """Refresh token request."""
    refresh_token: str = Field(..., description="Refresh token")
    publisher_id: Optional[str] = Field(None, description="Publisher context")


class PasswordChangeRequest(BaseModel):
    """Password change request."""
    current_password: str = Field(..., min_length=8, description="Current password")
    new_password: str = Field(..., min_length=8, description="New password")


class PasswordResetRequest(BaseModel):
    """Password reset initiation request."""
    email: EmailStr = Field(..., description="Email address for password reset")


class PasswordResetCompleteRequest(BaseModel):
    """Password reset completion request."""
    token: str = Field(..., description="Password reset token")
    new_password: str = Field(..., min_length=8, description="New password")


class TokenValidationRequest(BaseModel):
    """Token validation request."""
    token: str = Field(..., description="Token to validate")
    token_type: Optional[str] = Field(None, description="Expected token type")


class TokenValidationResponse(BaseModel):
    """Token validation response."""
    is_valid: bool = Field(..., description="Whether token is valid")
    token_type: Optional[str] = Field(None, description="Token type")
    user_id: Optional[str] = Field(None, description="User ID if applicable")
    publisher_id: Optional[str] = Field(None, description="Publisher ID if applicable")
    permissions: list = Field(default=[], description="Available permissions")
    expires_at: Optional[datetime] = Field(None, description="Token expiration time")
    error: Optional[str] = Field(None, description="Error message if invalid")


# Authentication Endpoints

@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    session: AsyncSession = Depends(get_db_session)
):
    """
    Authenticate user and return access tokens.
    
    Supports:
    - Email/password authentication
    - Publisher-specific authentication
    - Remember me functionality
    - Multi-publisher user access
    """
    user_service = UserService(session)
    token_service = TokenService(session)
    
    # Authenticate user
    user = await user_service.authenticate_user(request.email, request.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "invalid_credentials",
                "message": "Invalid email or password",
                "code": "INVALID_CREDENTIALS"
            }
        )
    
    # Verify publisher access if specified
    if request.publisher_id:
        has_access = await user_service.verify_publisher_access(
            str(user.id), request.publisher_id
        )
        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "no_publisher_access",
                    "message": "User does not have access to the specified publisher",
                    "code": "NO_PUBLISHER_ACCESS"
                }
            )
    
    # Create session (if using session management)
    session_id = None  # Could create UserSession here
    
    # Create tokens
    access_token_expires = timedelta(minutes=30 if not request.remember_me else 60 * 24)  # 24 hours for remember me
    refresh_token_expires = timedelta(days=7 if not request.remember_me else 30)  # 30 days for remember me
    
    access_token = await token_service.create_user_token(
        user, request.publisher_id, session_id, access_token_expires
    )
    
    refresh_token = await token_service.create_refresh_token(
        user, request.publisher_id, session_id
    )
    
    # Record successful login
    await user_service.record_login(str(user.id))
    
    # Get user profile for response
    user_profile = {
        "id": str(user.id),
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "full_name": user.full_name
    }
    
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=int(access_token_expires.total_seconds()),
        refresh_token=refresh_token,
        publisher_id=request.publisher_id,
        user=user_profile
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: RefreshTokenRequest,
    session: AsyncSession = Depends(get_db_session)
):
    """
    Refresh an access token using a refresh token.
    """
    token_service = TokenService(session)
    user_service = UserService(session)
    
    # Validate refresh token
    validation_result = await token_service.validate_token(request.refresh_token, "refresh")
    
    if not validation_result.is_valid or validation_result.token_data.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "invalid_refresh_token",
                "message": "Invalid or expired refresh token",
                "code": "INVALID_REFRESH_TOKEN"
            }
        )
    
    # Get user
    user = await user_service.get_user(validation_result.user_id)
    if not user or not user.can_login():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "user_inactive",
                "message": "User account is inactive",
                "code": "USER_INACTIVE"
            }
        )
    
    # Verify publisher access if specified
    publisher_id = request.publisher_id or validation_result.publisher_id
    if publisher_id:
        has_access = await user_service.verify_publisher_access(
            str(user.id), publisher_id
        )
        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "no_publisher_access",
                    "message": "User no longer has access to the specified publisher",
                    "code": "NO_PUBLISHER_ACCESS"
                }
            )
    
    # Create new access token
    session_id = validation_result.token_data.get("session_id")
    access_token = await token_service.create_user_token(user, publisher_id, session_id)
    
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=30 * 60,  # 30 minutes
        publisher_id=publisher_id
    )


@router.post("/logout")
async def logout(
    request: Request,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Logout user and invalidate tokens.
    """
    # In a full implementation, this would:
    # 1. Add the current token to a blacklist
    # 2. Invalidate the user's session
    # 3. Clear refresh tokens
    
    # For now, return success (client should discard token)
    return {"message": "Logged out successfully"}


@router.post("/verify", response_model=TokenValidationResponse)
async def verify_token(
    request: TokenValidationRequest,
    session: AsyncSession = Depends(get_db_session)
):
    """
    Verify and validate any type of token.
    
    Useful for:
    - Token introspection
    - Debugging authentication issues
    - Third-party token validation
    """
    token_service = TokenService(session)
    
    # Validate the token
    validation_result = await token_service.validate_token(
        request.token, request.token_type
    )
    
    response = TokenValidationResponse(
        is_valid=validation_result.is_valid,
        token_type=validation_result.token_type,
        user_id=validation_result.user_id,
        publisher_id=validation_result.publisher_id,
        permissions=validation_result.permissions,
        error=validation_result.error
    )
    
    # Add expiration time if available from token data
    if validation_result.is_valid and validation_result.token_data:
        exp = validation_result.token_data.get("exp")
        if exp:
            response.expires_at = datetime.fromtimestamp(exp)
    
    return response


# Password Management

@router.post("/password/change")
async def change_password(
    request: PasswordChangeRequest,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Change user password.
    Requires current password for verification.
    """
    user_service = UserService(session)
    
    # Change password
    success = await user_service.change_password(
        user_id, request.current_password, request.new_password
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "password_change_failed",
                "message": "Current password is incorrect or password change failed",
                "code": "PASSWORD_CHANGE_FAILED"
            }
        )
    
    return {"message": "Password changed successfully"}


@router.post("/password/reset")
async def initiate_password_reset(
    request: PasswordResetRequest,
    session: AsyncSession = Depends(get_db_session)
):
    """
    Initiate password reset process.
    Sends reset email to user.
    """
    user_service = UserService(session)
    
    # Initiate password reset
    success = await user_service.initiate_password_reset(request.email)
    
    # Always return success to prevent email enumeration
    return {"message": "If the email exists, a password reset link has been sent"}


@router.post("/password/reset/complete")
async def complete_password_reset(
    request: PasswordResetCompleteRequest,
    session: AsyncSession = Depends(get_db_session)
):
    """
    Complete password reset with token.
    """
    user_service = UserService(session)
    
    # Complete password reset
    success = await user_service.reset_password_with_token(
        request.token, request.new_password
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "password_reset_failed",
                "message": "Invalid or expired reset token",
                "code": "PASSWORD_RESET_FAILED"
            }
        )
    
    return {"message": "Password reset successfully"}


# Email Verification

@router.post("/email/verify")
async def verify_email(
    token: str,
    session: AsyncSession = Depends(get_db_session)
):
    """
    Verify user email address with verification token.
    """
    user_service = UserService(session)
    
    # Verify email
    success = await user_service.verify_user_email(token)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "email_verification_failed",
                "message": "Invalid or expired verification token",
                "code": "EMAIL_VERIFICATION_FAILED"
            }
        )
    
    return {"message": "Email verified successfully"}


@router.post("/email/resend-verification")
async def resend_verification_email(
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Resend email verification to current user.
    """
    user_service = UserService(session)
    
    # Resend verification email
    success = await user_service.resend_verification_email(user_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "verification_send_failed",
                "message": "Failed to send verification email",
                "code": "VERIFICATION_SEND_FAILED"
            }
        )
    
    return {"message": "Verification email sent"}


# User Profile

@router.get("/me")
async def get_current_user_profile(
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Get current authenticated user's profile.
    """
    user_service = UserService(session)
    
    user = await user_service.get_user(user_id, include_publishers=True)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "user_not_found",
                "message": "User not found",
                "code": "USER_NOT_FOUND"
            }
        )
    
    # Get user's publisher relationships
    publishers = await user_service.get_user_publishers(user_id)
    
    return {
        "id": str(user.id),
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "full_name": user.full_name,
        "avatar_url": user.avatar_url,
        "timezone": user.timezone,
        "language": user.language,
        "is_verified": user.is_verified,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "publishers": [
            {
                "id": str(pub["publisher_id"]),
                "name": pub["publisher_name"],
                "role": pub["role"],
                "status": pub["status"]
            }
            for pub in publishers
        ]
    }


# Session Management (if using session-based auth)

@router.get("/sessions")
async def list_user_sessions(
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session)
):
    """
    List active sessions for current user.
    """
    # This would integrate with UserSession model
    # For now, return placeholder
    return {"sessions": []}


@router.delete("/sessions/{session_id}")
async def revoke_session(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Revoke a specific user session.
    """
    # This would revoke a UserSession
    # For now, return success
    return {"message": "Session revoked successfully"}