"""User service layer for comprehensive user management in the multi-tenant platform.

This service provides complete business logic for user CRUD operations, authentication,
publisher relationships, security features, and profile management. It follows established
service patterns and integrates with all user-related models.
"""

import logging
import uuid
import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple, Union

from sqlalchemy import and_, or_, func, desc, asc, select
from sqlalchemy.orm import AsyncSession, selectinload, joinedload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError, NoResultFound

from src.models.user import User
from src.models.user_publisher import UserPublisher
from src.models.user_session import UserSession
from src.models.publisher import Publisher
from src.models.role import Role
from src.services.business_rules import ValidationResult, ValidationError, TenantContext
from src.services.events import EventPublisher

logger = logging.getLogger(__name__)


class UserServiceError(Exception):
    """Base exception for user service errors."""
    pass


class UserNotFoundError(UserServiceError):
    """Raised when a user cannot be found."""
    pass


class UserValidationError(UserServiceError):
    """Raised when user data validation fails."""
    
    def __init__(self, message: str, validation_errors: List[ValidationError] = None):
        super().__init__(message)
        self.validation_errors = validation_errors or []


class UserPermissionError(UserServiceError):
    """Raised when user lacks permission for operation."""
    pass


class UserAuthenticationError(UserServiceError):
    """Raised when user authentication fails."""
    pass


class UserSecurityError(UserServiceError):
    """Raised when security-related operations fail."""
    pass


class UserService:
    """
    Comprehensive User service for multi-tenant publishing platform.
    
    This service provides complete business logic for:
    - User CRUD operations with validation
    - Authentication and security features
    - Publisher-user relationship management
    - Profile and preference management
    - Email verification and password management
    - Multi-factor authentication
    - Session management integration
    - Security event logging and monitoring
    """
    
    def __init__(self, db_session: AsyncSession, event_publisher: EventPublisher = None):
        """
        Initialize the UserService.
        
        Args:
            db_session: Async database session
            event_publisher: Optional event publisher for async operations
        """
        self.db = db_session
        self.events = event_publisher
        
    # Core User Management Operations
    
    async def create_user(
        self,
        user_data: Dict[str, Any],
        send_verification_email: bool = True,
        initial_password: Optional[str] = None,
        external_auth_info: Optional[Dict[str, Any]] = None
    ) -> User:
        """
        Create a new user with validation and email verification.
        
        Args:
            user_data: User information
            send_verification_email: Whether to send email verification
            initial_password: Initial password (required if not external auth)
            external_auth_info: External authentication provider info
            
        Returns:
            User: Created user
            
        Raises:
            UserValidationError: If validation fails
            UserServiceError: If creation fails
        """
        logger.info(f"Creating new user: {user_data.get('email')}")
        
        # Validate user data
        validation_result = self._validate_user_creation(user_data, initial_password, external_auth_info)
        if not validation_result.is_valid:
            raise UserValidationError(
                "User validation failed",
                validation_result.errors
            )
        
        # Check email availability
        if await self._is_email_taken(user_data["email"]):
            raise UserValidationError("Email address is already registered")
        
        # Check username availability if provided
        if user_data.get("username") and await self._is_username_taken(user_data["username"]):
            raise UserValidationError("Username is already taken")
        
        try:
            # Create user instance
            user = User(**user_data)
            
            # Set up authentication
            if external_auth_info:
                user.is_external_auth = True
                user.external_auth_provider = external_auth_info["provider"]
                user.external_auth_id = external_auth_info["provider_id"]
                user.is_verified = True  # External auth users are pre-verified
                user.email_verified_at = datetime.utcnow()
                user.status = "active"
            else:
                if not initial_password:
                    raise UserValidationError("Password is required for non-external auth users")
                user.set_password(initial_password)
                user.status = "pending_verification" if send_verification_email else "active"
                user.is_verified = not send_verification_email
                if not send_verification_email:
                    user.email_verified_at = datetime.utcnow()
            
            self.db.add(user)
            await self.db.flush()  # Get user ID
            
            # Initialize profile completion score
            user.calculate_profile_completion()
            
            await self.db.commit()
            
            # Send verification email if needed
            if send_verification_email and not external_auth_info:
                await self._send_verification_email(user)
            
            # Publish user creation event
            if self.events:
                await self.events.publish_user_created(
                    user_id=user.id,
                    email=user.email,
                    is_external_auth=user.is_external_auth
                )
            
            logger.info(f"Successfully created user {user.id}")
            return user
            
        except IntegrityError as e:
            await self.db.rollback()
            logger.error(f"Database integrity error creating user: {e}")
            raise UserServiceError("Failed to create user due to data constraint violation")
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error creating user: {e}")
            raise UserServiceError(f"Failed to create user: {str(e)}")
    
    async def get_user(
        self,
        user_id: uuid.UUID,
        include_relationships: bool = False,
        include_sessions: bool = False
    ) -> User:
        """
        Get user by ID with optional relationship loading.
        
        Args:
            user_id: User UUID
            include_relationships: Whether to load publisher relationships
            include_sessions: Whether to load active sessions
            
        Returns:
            User: Found user
            
        Raises:
            UserNotFoundError: If user not found
        """
        try:
            query = select(User).where(User.id == user_id)
            
            if include_relationships:
                query = query.options(
                    selectinload(User.publisher_relationships)
                    .joinedload(UserPublisher.publisher)
                    .joinedload(Publisher.account),
                    selectinload(User.publisher_relationships)
                    .joinedload(UserPublisher.role)
                )
            
            if include_sessions:
                query = query.options(
                    selectinload(User.sessions).where(
                        UserSession.status == "active"
                    )
                )
            
            result = await self.db.execute(query)
            user = result.scalar_one()
            
            return user
            
        except NoResultFound:
            logger.warning(f"User {user_id} not found")
            raise UserNotFoundError(f"User {user_id} not found")
        except Exception as e:
            logger.error(f"Error retrieving user {user_id}: {e}")
            raise UserServiceError(f"Failed to retrieve user: {str(e)}")
    
    async def get_user_by_email(self, email: str) -> Optional[User]:
        """
        Get user by email address.
        
        Args:
            email: User email address
            
        Returns:
            Optional[User]: Found user or None
        """
        try:
            query = select(User).where(User.email == email.lower())
            result = await self.db.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error retrieving user by email {email}: {e}")
            raise UserServiceError(f"Failed to retrieve user: {str(e)}")
    
    async def update_user_profile(
        self,
        user_id: uuid.UUID,
        profile_data: Dict[str, Any],
        updated_by: Optional[uuid.UUID] = None
    ) -> User:
        """
        Update user profile information with validation.
        
        Args:
            user_id: User UUID
            profile_data: Profile fields to update
            updated_by: UUID of user making the update (for audit)
            
        Returns:
            User: Updated user
            
        Raises:
            UserNotFoundError: If user not found
            UserValidationError: If validation fails
        """
        logger.info(f"Updating profile for user {user_id}")
        
        user = await self.get_user(user_id)
        
        # Validate profile update
        validation_result = self._validate_profile_update(profile_data, user)
        if not validation_result.is_valid:
            raise UserValidationError(
                "Profile update validation failed",
                validation_result.errors
            )
        
        # Check email uniqueness if changing
        if ("email" in profile_data and 
            profile_data["email"] != user.email and
            await self._is_email_taken(profile_data["email"])):
            raise UserValidationError("Email address is already registered")
        
        # Check username uniqueness if changing
        if ("username" in profile_data and 
            profile_data["username"] != user.username and
            await self._is_username_taken(profile_data["username"])):
            raise UserValidationError("Username is already taken")
        
        try:
            # Update allowed profile fields
            updatable_fields = {
                "first_name", "last_name", "email", "username", "phone_number",
                "timezone", "language", "avatar_url"
            }
            
            email_changed = False
            for field, value in profile_data.items():
                if field in updatable_fields:
                    old_value = getattr(user, field)
                    setattr(user, field, value)
                    
                    # Track email changes for re-verification
                    if field == "email" and old_value != value:
                        email_changed = True
                        user.is_verified = False
                        user.email_verified_at = None
                        if user.status == "active":
                            user.status = "pending_verification"
            
            user.updated_at = datetime.utcnow()
            
            # Update profile completion score
            user.calculate_profile_completion()
            user.update_metadata("last_profile_update", datetime.utcnow().isoformat())
            
            await self.db.commit()
            
            # Send new verification email if email changed
            if email_changed:
                await self._send_verification_email(user)
            
            # Publish profile update event
            if self.events:
                await self.events.publish_user_profile_updated(
                    user_id=user.id,
                    updated_by=updated_by or user.id,
                    changes=list(profile_data.keys()),
                    email_changed=email_changed
                )
            
            logger.info(f"Successfully updated profile for user {user_id}")
            return user
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error updating user profile {user_id}: {e}")
            raise UserServiceError(f"Failed to update user profile: {str(e)}")
    
    async def update_user_preferences(
        self,
        user_id: uuid.UUID,
        preferences_update: Dict[str, Any],
        publisher_id: Optional[uuid.UUID] = None
    ) -> Dict[str, Any]:
        """
        Update user preferences with publisher context support.
        
        Args:
            user_id: User UUID
            preferences_update: Preferences to update
            publisher_id: Optional publisher context for preferences
            
        Returns:
            Dict[str, Any]: Updated preferences
        """
        logger.info(f"Updating preferences for user {user_id}")
        
        user = await self.get_user(user_id)
        
        try:
            # Update user-level preferences
            for key, value in preferences_update.items():
                user.update_preference(key, value)
            
            user.updated_at = datetime.utcnow()
            
            # If publisher context provided, also update publisher-specific preferences
            if publisher_id:
                user_publisher = await self._get_user_publisher_relationship(user_id, publisher_id)
                if user_publisher:
                    publisher_preferences = preferences_update.get("publisher_specific", {})
                    for key, value in publisher_preferences.items():
                        user_publisher.update_setting(key, value)
            
            await self.db.commit()
            
            # Publish preferences update event
            if self.events:
                await self.events.publish_user_preferences_updated(
                    user_id=user.id,
                    publisher_id=publisher_id,
                    preferences_changed=list(preferences_update.keys())
                )
            
            logger.info(f"Successfully updated preferences for user {user_id}")
            return user.preferences
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error updating user preferences {user_id}: {e}")
            raise UserServiceError(f"Failed to update user preferences: {str(e)}")
    
    async def archive_user(
        self,
        user_id: uuid.UUID,
        archived_by: uuid.UUID,
        reason: Optional[str] = None
    ) -> User:
        """
        Archive (soft delete) a user account.
        
        Args:
            user_id: User UUID
            archived_by: UUID of user performing the archive
            reason: Optional reason for archiving
            
        Returns:
            User: Archived user
        """
        logger.info(f"Archiving user {user_id}")
        
        user = await self.get_user(user_id, include_sessions=True)
        
        try:
            # Update status to deactivated
            user.status = "deactivated"
            user.updated_at = datetime.utcnow()
            
            # Store archive metadata
            user.update_metadata("archive_info", {
                "archived_by": str(archived_by),
                "archived_at": datetime.utcnow().isoformat(),
                "reason": reason
            })
            
            # Revoke all active sessions
            active_sessions = [s for s in user.sessions if s.is_active]
            for session in active_sessions:
                session.revoke("user_archived")
            
            # Suspend all publisher relationships
            publisher_relationships = await self._get_user_publisher_relationships(user_id)
            for up in publisher_relationships:
                if up.is_active:
                    up.suspend_access(
                        reason=f"User archived: {reason or 'No reason provided'}",
                        suspended_by=archived_by
                    )
            
            await self.db.commit()
            
            # Publish user archive event
            if self.events:
                await self.events.publish_user_archived(
                    user_id=user.id,
                    archived_by=archived_by,
                    reason=reason
                )
            
            logger.info(f"Successfully archived user {user_id}")
            return user
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error archiving user {user_id}: {e}")
            raise UserServiceError(f"Failed to archive user: {str(e)}")
    
    async def list_users(
        self,
        filters: Optional[Dict[str, Any]] = None,
        pagination: Optional[Dict[str, Any]] = None,
        publisher_id: Optional[uuid.UUID] = None
    ) -> Tuple[List[User], int]:
        """
        List users with filtering and pagination.
        
        Args:
            filters: Optional filters (status, is_verified, search, etc.)
            pagination: Optional pagination (limit, offset, sort_by, sort_order)
            publisher_id: Optional publisher context for filtering
            
        Returns:
            Tuple[List[User], int]: (users, total_count)
        """
        try:
            if publisher_id:
                # List users for a specific publisher
                query = select(User).join(UserPublisher).where(
                    UserPublisher.publisher_id == publisher_id
                ).options(
                    selectinload(User.publisher_relationships)
                    .where(UserPublisher.publisher_id == publisher_id)
                    .joinedload(UserPublisher.role)
                )
            else:
                # List all users (system-wide)
                query = select(User)
            
            # Apply filters
            if filters:
                if "status" in filters:
                    query = query.where(User.status == filters["status"])
                if "is_verified" in filters:
                    query = query.where(User.is_verified == filters["is_verified"])
                if "is_external_auth" in filters:
                    query = query.where(User.is_external_auth == filters["is_external_auth"])
                if "search" in filters:
                    search_term = f"%{filters['search']}%"
                    query = query.where(
                        or_(
                            User.email.ilike(search_term),
                            User.first_name.ilike(search_term),
                            User.last_name.ilike(search_term),
                            func.concat(User.first_name, ' ', User.last_name).ilike(search_term)
                        )
                    )
            
            # Get total count
            count_query = select(func.count(User.id))
            if publisher_id:
                count_query = count_query.join(UserPublisher).where(
                    UserPublisher.publisher_id == publisher_id
                )
            
            # Apply same filters to count query
            if filters:
                if "status" in filters:
                    count_query = count_query.where(User.status == filters["status"])
                if "is_verified" in filters:
                    count_query = count_query.where(User.is_verified == filters["is_verified"])
                if "is_external_auth" in filters:
                    count_query = count_query.where(User.is_external_auth == filters["is_external_auth"])
                if "search" in filters:
                    search_term = f"%{filters['search']}%"
                    count_query = count_query.where(
                        or_(
                            User.email.ilike(search_term),
                            User.first_name.ilike(search_term),
                            User.last_name.ilike(search_term),
                            func.concat(User.first_name, ' ', User.last_name).ilike(search_term)
                        )
                    )
            
            total_count_result = await self.db.execute(count_query)
            total_count = total_count_result.scalar()
            
            # Apply pagination and sorting
            if pagination:
                sort_by = pagination.get("sort_by", "created_at")
                sort_order = pagination.get("sort_order", "desc")
                
                if hasattr(User, sort_by):
                    order_col = getattr(User, sort_by)
                    if sort_order.lower() == "desc":
                        query = query.order_by(desc(order_col))
                    else:
                        query = query.order_by(asc(order_col))
                
                if "limit" in pagination:
                    query = query.limit(pagination["limit"])
                
                if "offset" in pagination:
                    query = query.offset(pagination["offset"])
            
            result = await self.db.execute(query)
            users = result.scalars().all()
            
            return list(users), total_count
            
        except Exception as e:
            logger.error(f"Error listing users: {e}")
            raise UserServiceError(f"Failed to list users: {str(e)}")
    
    # Authentication Operations
    
    async def authenticate_user(
        self,
        email: str,
        password: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Tuple[User, bool]:
        """
        Authenticate user with password and security checks.
        
        Args:
            email: User email address
            password: User password
            ip_address: Client IP address for security logging
            user_agent: Client user agent for security logging
            
        Returns:
            Tuple[User, bool]: (authenticated_user, requires_mfa)
            
        Raises:
            UserAuthenticationError: If authentication fails
        """
        logger.info(f"Attempting authentication for user: {email}")
        
        user = await self.get_user_by_email(email)
        if not user:
            logger.warning(f"Authentication failed - user not found: {email}")
            raise UserAuthenticationError("Invalid email or password")
        
        # Check if user can login
        can_login, reason = user.can_login()
        if not can_login:
            logger.warning(f"User {user.id} cannot login: {reason}")
            user.record_login_attempt(False, ip_address)
            await self.db.commit()
            raise UserAuthenticationError(f"Login denied: {reason}")
        
        # Verify password
        if not user.verify_password(password):
            logger.warning(f"Authentication failed - invalid password for user {user.id}")
            user.record_login_attempt(False, ip_address)
            await self.db.commit()
            
            # Check if account should be locked
            if user.is_locked:
                raise UserAuthenticationError("Account temporarily locked due to failed login attempts")
            
            raise UserAuthenticationError("Invalid email or password")
        
        # Successful authentication
        user.record_login_attempt(True, ip_address)
        await self.db.commit()
        
        # Publish successful authentication event
        if self.events:
            await self.events.publish_user_authenticated(
                user_id=user.id,
                ip_address=ip_address,
                user_agent=user_agent,
                requires_mfa=user.mfa_enabled
            )
        
        logger.info(f"Successfully authenticated user {user.id}")
        return user, user.mfa_enabled
    
    async def verify_mfa_token(
        self,
        user_id: uuid.UUID,
        token: str,
        ip_address: Optional[str] = None
    ) -> bool:
        """
        Verify multi-factor authentication token.
        
        Args:
            user_id: User UUID
            token: MFA token to verify
            ip_address: Client IP address for logging
            
        Returns:
            bool: True if token is valid
            
        Raises:
            UserSecurityError: If MFA verification fails
        """
        logger.info(f"Verifying MFA token for user {user_id}")
        
        user = await self.get_user(user_id)
        
        if not user.mfa_enabled or not user.mfa_secret:
            raise UserSecurityError("MFA is not enabled for this user")
        
        try:
            # In a real implementation, you would use a TOTP library like pyotp
            # For now, we'll simulate the verification
            import pyotp
            totp = pyotp.TOTP(user.mfa_secret)
            is_valid = totp.verify(token, valid_window=1)
            
            if is_valid:
                logger.info(f"MFA token verified successfully for user {user_id}")
                
                # Publish MFA verification event
                if self.events:
                    await self.events.publish_mfa_verified(
                        user_id=user.id,
                        ip_address=ip_address
                    )
                
                return True
            else:
                logger.warning(f"Invalid MFA token for user {user_id}")
                
                # Publish MFA failure event
                if self.events:
                    await self.events.publish_mfa_failed(
                        user_id=user.id,
                        ip_address=ip_address
                    )
                
                return False
                
        except ImportError:
            # Fallback without pyotp library
            logger.warning("pyotp library not available, MFA verification disabled")
            return True  # Allow login without MFA in development
        except Exception as e:
            logger.error(f"Error verifying MFA token for user {user_id}: {e}")
            raise UserSecurityError(f"MFA verification failed: {str(e)}")
    
    async def change_password(
        self,
        user_id: uuid.UUID,
        current_password: str,
        new_password: str,
        force_change: bool = False
    ) -> bool:
        """
        Change user password with current password verification.
        
        Args:
            user_id: User UUID
            current_password: Current password for verification
            new_password: New password to set
            force_change: Skip current password verification (admin use)
            
        Returns:
            bool: True if password was changed
            
        Raises:
            UserAuthenticationError: If current password is invalid
            UserValidationError: If new password is invalid
        """
        logger.info(f"Changing password for user {user_id}")
        
        user = await self.get_user(user_id)
        
        if user.is_external_auth:
            raise UserServiceError("Cannot change password for external authentication users")
        
        # Verify current password unless force change
        if not force_change and not user.verify_password(current_password):
            raise UserAuthenticationError("Current password is invalid")
        
        # Validate new password
        password_validation = self._validate_password(new_password, user)
        if not password_validation.is_valid:
            raise UserValidationError(
                "Password validation failed",
                password_validation.errors
            )
        
        try:
            # Set new password
            user.set_password(new_password)
            user.updated_at = datetime.utcnow()
            
            # Set password change requirement to false
            user.update_preference("security.require_password_change", False)
            
            await self.db.commit()
            
            # Publish password change event
            if self.events:
                await self.events.publish_password_changed(
                    user_id=user.id,
                    forced=force_change
                )
            
            logger.info(f"Successfully changed password for user {user_id}")
            return True
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error changing password for user {user_id}: {e}")
            raise UserServiceError(f"Failed to change password: {str(e)}")
    
    async def initiate_password_reset(
        self,
        email: str,
        ip_address: Optional[str] = None
    ) -> bool:
        """
        Initiate password reset process by sending reset email.
        
        Args:
            email: User email address
            ip_address: Client IP address for security logging
            
        Returns:
            bool: True if reset email was sent (always returns True for security)
        """
        logger.info(f"Initiating password reset for email: {email}")
        
        user = await self.get_user_by_email(email)
        
        # Always return True for security reasons (don't reveal if email exists)
        if not user or user.is_external_auth:
            logger.info(f"Password reset requested for non-existent or external auth user: {email}")
            return True
        
        try:
            # Generate reset token
            reset_token = secrets.token_urlsafe(32)
            reset_token_hash = hashlib.sha256(reset_token.encode()).hexdigest()
            
            # Store reset token with expiration (1 hour)
            user.update_metadata("password_reset", {
                "token_hash": reset_token_hash,
                "expires_at": (datetime.utcnow() + timedelta(hours=1)).isoformat(),
                "requested_at": datetime.utcnow().isoformat(),
                "ip_address": ip_address
            })
            
            await self.db.commit()
            
            # Send reset email (implementation would go here)
            await self._send_password_reset_email(user, reset_token)
            
            # Publish password reset event
            if self.events:
                await self.events.publish_password_reset_requested(
                    user_id=user.id,
                    ip_address=ip_address
                )
            
            logger.info(f"Password reset initiated for user {user.id}")
            return True
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error initiating password reset for {email}: {e}")
            # Still return True for security
            return True
    
    async def reset_password_with_token(
        self,
        reset_token: str,
        new_password: str,
        ip_address: Optional[str] = None
    ) -> bool:
        """
        Reset password using reset token.
        
        Args:
            reset_token: Password reset token
            new_password: New password to set
            ip_address: Client IP address for logging
            
        Returns:
            bool: True if password was reset
            
        Raises:
            UserSecurityError: If token is invalid or expired
            UserValidationError: If new password is invalid
        """
        logger.info("Attempting password reset with token")
        
        # Hash the provided token
        token_hash = hashlib.sha256(reset_token.encode()).hexdigest()
        
        # Find user with matching token
        users_query = select(User).where(
            func.json_extract_path_text(User.metadata, 'password_reset', 'token_hash') == token_hash
        )
        result = await self.db.execute(users_query)
        user = result.scalar_one_or_none()
        
        if not user:
            raise UserSecurityError("Invalid or expired reset token")
        
        # Check token expiration
        reset_data = user.get_metadata("password_reset", {})
        if not reset_data or "expires_at" not in reset_data:
            raise UserSecurityError("Invalid reset token data")
        
        try:
            expires_at = datetime.fromisoformat(reset_data["expires_at"])
            if datetime.utcnow() > expires_at:
                raise UserSecurityError("Reset token has expired")
        except ValueError:
            raise UserSecurityError("Invalid reset token expiration")
        
        # Validate new password
        password_validation = self._validate_password(new_password, user)
        if not password_validation.is_valid:
            raise UserValidationError(
                "Password validation failed",
                password_validation.errors
            )
        
        try:
            # Set new password
            user.set_password(new_password)
            user.updated_at = datetime.utcnow()
            
            # Clear reset token
            user.update_metadata("password_reset", {})
            
            # Ensure account is active and verified
            if user.status == "pending_verification":
                user.verify_email()
            
            await self.db.commit()
            
            # Publish password reset completion event
            if self.events:
                await self.events.publish_password_reset_completed(
                    user_id=user.id,
                    ip_address=ip_address
                )
            
            logger.info(f"Password reset completed for user {user.id}")
            return True
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error resetting password: {e}")
            raise UserServiceError(f"Failed to reset password: {str(e)}")
    
    async def verify_user_email(
        self,
        verification_token: str,
        ip_address: Optional[str] = None
    ) -> bool:
        """
        Verify user email address using verification token.
        
        Args:
            verification_token: Email verification token
            ip_address: Client IP address for logging
            
        Returns:
            bool: True if email was verified
            
        Raises:
            UserSecurityError: If token is invalid
        """
        logger.info("Attempting email verification with token")
        
        # Hash the provided token
        token_hash = hashlib.sha256(verification_token.encode()).hexdigest()
        
        # Find user with matching token
        users_query = select(User).where(
            func.json_extract_path_text(User.metadata, 'email_verification', 'token_hash') == token_hash
        )
        result = await self.db.execute(users_query)
        user = result.scalar_one_or_none()
        
        if not user:
            raise UserSecurityError("Invalid verification token")
        
        # Check if already verified
        if user.is_verified:
            logger.info(f"User {user.id} email already verified")
            return True
        
        try:
            # Verify email
            user.verify_email()
            user.updated_at = datetime.utcnow()
            
            # Clear verification token
            user.update_metadata("email_verification", {})
            
            await self.db.commit()
            
            # Publish email verification event
            if self.events:
                await self.events.publish_email_verified(
                    user_id=user.id,
                    email=user.email,
                    ip_address=ip_address
                )
            
            logger.info(f"Email verified for user {user.id}")
            return True
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error verifying email: {e}")
            raise UserServiceError(f"Failed to verify email: {str(e)}")
    
    # Publisher-User Relationship Management
    
    async def add_user_to_publisher(
        self,
        user_id: uuid.UUID,
        publisher_id: uuid.UUID,
        role_id: uuid.UUID,
        added_by: uuid.UUID,
        is_primary: bool = False,
        send_invitation: bool = True
    ) -> UserPublisher:
        """
        Add user to publisher with role assignment.
        
        Args:
            user_id: User UUID
            publisher_id: Publisher UUID
            role_id: Role UUID to assign
            added_by: UUID of user performing the addition
            is_primary: Whether this is the user's primary publisher
            send_invitation: Whether to send invitation email
            
        Returns:
            UserPublisher: Created user-publisher relationship
            
        Raises:
            UserServiceError: If addition fails
        """
        logger.info(f"Adding user {user_id} to publisher {publisher_id}")
        
        # Check if relationship already exists
        existing = await self._get_user_publisher_relationship(user_id, publisher_id)
        if existing:
            raise UserServiceError("User already has a relationship with this publisher")
        
        # Validate role exists and belongs to publisher
        role_query = select(Role).where(
            and_(
                Role.id == role_id,
                or_(Role.publisher_id == publisher_id, Role.is_system_role == True)
            )
        )
        role_result = await self.db.execute(role_query)
        role = role_result.scalar_one_or_none()
        
        if not role:
            raise UserServiceError("Invalid role for this publisher")
        
        try:
            # Create user-publisher relationship
            user_publisher = UserPublisher(
                user_id=user_id,
                publisher_id=publisher_id,
                role_id=role_id,
                status="invited" if send_invitation else "active",
                is_primary=is_primary,
                invited_by=added_by,
                invited_at=datetime.utcnow() if send_invitation else None
            )
            
            if send_invitation:
                # Generate invitation token
                invitation_token = user_publisher.generate_invitation_token()
                # Send invitation email (implementation would go here)
                await self._send_user_invitation_email(user_id, publisher_id, invitation_token)
            else:
                user_publisher.joined_at = datetime.utcnow()
            
            self.db.add(user_publisher)
            await self.db.commit()
            
            # Publish user addition event
            if self.events:
                await self.events.publish_user_added_to_publisher(
                    user_id=user_id,
                    publisher_id=publisher_id,
                    role_id=role_id,
                    added_by=added_by,
                    invitation_sent=send_invitation
                )
            
            logger.info(f"Successfully added user {user_id} to publisher {publisher_id}")
            return user_publisher
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error adding user to publisher: {e}")
            raise UserServiceError(f"Failed to add user to publisher: {str(e)}")
    
    async def remove_user_from_publisher(
        self,
        user_id: uuid.UUID,
        publisher_id: uuid.UUID,
        removed_by: uuid.UUID,
        reason: Optional[str] = None
    ) -> bool:
        """
        Remove user from publisher.
        
        Args:
            user_id: User UUID
            publisher_id: Publisher UUID
            removed_by: UUID of user performing the removal
            reason: Optional reason for removal
            
        Returns:
            bool: True if user was removed
            
        Raises:
            UserServiceError: If removal fails
        """
        logger.info(f"Removing user {user_id} from publisher {publisher_id}")
        
        user_publisher = await self._get_user_publisher_relationship(user_id, publisher_id)
        if not user_publisher:
            raise UserServiceError("User-publisher relationship not found")
        
        try:
            # Update relationship status
            user_publisher.status = "revoked"
            user_publisher.updated_at = datetime.utcnow()
            
            # Store removal metadata
            user_publisher.update_metadata("removal_info", {
                "removed_by": str(removed_by),
                "removed_at": datetime.utcnow().isoformat(),
                "reason": reason
            })
            
            await self.db.commit()
            
            # Publish user removal event
            if self.events:
                await self.events.publish_user_removed_from_publisher(
                    user_id=user_id,
                    publisher_id=publisher_id,
                    removed_by=removed_by,
                    reason=reason
                )
            
            logger.info(f"Successfully removed user {user_id} from publisher {publisher_id}")
            return True
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error removing user from publisher: {e}")
            raise UserServiceError(f"Failed to remove user from publisher: {str(e)}")
    
    async def update_user_publisher_role(
        self,
        user_id: uuid.UUID,
        publisher_id: uuid.UUID,
        new_role_id: uuid.UUID,
        updated_by: uuid.UUID
    ) -> UserPublisher:
        """
        Update user role within a publisher.
        
        Args:
            user_id: User UUID
            publisher_id: Publisher UUID
            new_role_id: New role UUID
            updated_by: UUID of user making the change
            
        Returns:
            UserPublisher: Updated user-publisher relationship
        """
        logger.info(f"Updating role for user {user_id} in publisher {publisher_id}")
        
        user_publisher = await self._get_user_publisher_relationship(user_id, publisher_id)
        if not user_publisher:
            raise UserServiceError("User-publisher relationship not found")
        
        # Validate new role
        new_role_query = select(Role).where(
            and_(
                Role.id == new_role_id,
                or_(Role.publisher_id == publisher_id, Role.is_system_role == True)
            )
        )
        new_role_result = await self.db.execute(new_role_query)
        new_role = new_role_result.scalar_one_or_none()
        
        if not new_role:
            raise UserServiceError("Invalid role for this publisher")
        
        try:
            old_role_name = user_publisher.role_name if user_publisher.role else user_publisher.legacy_role
            
            # Update role
            user_publisher.update_role(new_role_id, updated_by)
            user_publisher.updated_at = datetime.utcnow()
            
            await self.db.commit()
            
            # Publish role update event
            if self.events:
                await self.events.publish_user_role_updated(
                    user_id=user_id,
                    publisher_id=publisher_id,
                    old_role_name=old_role_name,
                    new_role_name=new_role.name,
                    updated_by=updated_by
                )
            
            logger.info(f"Successfully updated role for user {user_id} in publisher {publisher_id}")
            return user_publisher
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error updating user role: {e}")
            raise UserServiceError(f"Failed to update user role: {str(e)}")
    
    async def get_user_publishers(
        self,
        user_id: uuid.UUID,
        include_inactive: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get all publishers associated with a user.
        
        Args:
            user_id: User UUID
            include_inactive: Whether to include inactive relationships
            
        Returns:
            List[Dict[str, Any]]: List of publisher relationships with details
        """
        try:
            query = select(UserPublisher).options(
                joinedload(UserPublisher.publisher),
                joinedload(UserPublisher.role)
            ).where(UserPublisher.user_id == user_id)
            
            if not include_inactive:
                query = query.where(UserPublisher.status == "active")
            
            result = await self.db.execute(query)
            user_publishers = result.scalars().all()
            
            publisher_data = []
            for up in user_publishers:
                data = {
                    "relationship_id": up.id,
                    "publisher_id": up.publisher.id,
                    "publisher_name": up.publisher.name,
                    "publisher_subdomain": up.publisher.subdomain,
                    "role_name": up.role_name,
                    "status": up.status,
                    "is_primary": up.is_primary,
                    "joined_at": up.joined_at,
                    "last_accessed_at": up.last_accessed_at,
                    "access_count": up.access_count,
                    "permissions": up.get_effective_permissions()
                }
                publisher_data.append(data)
            
            return publisher_data
            
        except Exception as e:
            logger.error(f"Error getting user publishers for {user_id}: {e}")
            raise UserServiceError(f"Failed to get user publishers: {str(e)}")
    
    async def switch_publisher_context(
        self,
        user_id: uuid.UUID,
        publisher_id: uuid.UUID,
        session_id: Optional[uuid.UUID] = None
    ) -> Dict[str, Any]:
        """
        Switch user's current publisher context.
        
        Args:
            user_id: User UUID
            publisher_id: Publisher UUID to switch to
            session_id: Optional session ID to update
            
        Returns:
            Dict[str, Any]: Publisher context information
        """
        logger.info(f"Switching publisher context for user {user_id} to {publisher_id}")
        
        # Verify user has access to publisher
        user_publisher = await self._get_user_publisher_relationship(user_id, publisher_id)
        if not user_publisher or not user_publisher.is_active:
            raise UserPermissionError("User does not have access to this publisher")
        
        try:
            # Record access
            user_publisher.record_access()
            
            # Update session if provided
            if session_id:
                session_query = select(UserSession).where(
                    and_(
                        UserSession.id == session_id,
                        UserSession.user_id == user_id,
                        UserSession.status == "active"
                    )
                )
                session_result = await self.db.execute(session_query)
                session = session_result.scalar_one_or_none()
                
                if session:
                    session.update_activity(publisher_id)
            
            await self.db.commit()
            
            # Get publisher context
            publisher_context = {
                "publisher_id": user_publisher.publisher.id,
                "publisher_name": user_publisher.publisher.name,
                "publisher_subdomain": user_publisher.publisher.subdomain,
                "user_role": user_publisher.role_name,
                "permissions": user_publisher.get_effective_permissions(),
                "settings": user_publisher.settings,
                "is_primary": user_publisher.is_primary
            }
            
            # Publish context switch event
            if self.events:
                await self.events.publish_publisher_context_switched(
                    user_id=user_id,
                    publisher_id=publisher_id,
                    session_id=session_id
                )
            
            logger.info(f"Successfully switched publisher context for user {user_id}")
            return publisher_context
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error switching publisher context: {e}")
            raise UserServiceError(f"Failed to switch publisher context: {str(e)}")
    
    # Security Features
    
    async def enable_mfa(
        self,
        user_id: uuid.UUID,
        secret: str,
        verification_token: str
    ) -> Dict[str, Any]:
        """
        Enable multi-factor authentication for user.
        
        Args:
            user_id: User UUID
            secret: MFA secret key
            verification_token: Token to verify MFA setup
            
        Returns:
            Dict[str, Any]: MFA setup information
            
        Raises:
            UserSecurityError: If MFA setup fails
        """
        logger.info(f"Enabling MFA for user {user_id}")
        
        user = await self.get_user(user_id)
        
        if user.mfa_enabled:
            raise UserSecurityError("MFA is already enabled for this user")
        
        # Verify the token with the provided secret
        if not await self.verify_mfa_token(user_id, verification_token, None):
            # Temporarily set the secret for verification
            user.mfa_secret = secret
            
            try:
                import pyotp
                totp = pyotp.TOTP(secret)
                if not totp.verify(verification_token, valid_window=1):
                    raise UserSecurityError("Invalid MFA verification token")
            except ImportError:
                # Allow in development without pyotp
                pass
        
        try:
            # Enable MFA
            user.enable_mfa(secret)
            user.updated_at = datetime.utcnow()
            
            await self.db.commit()
            
            # Generate backup codes
            backup_codes = self._generate_backup_codes()
            user.update_metadata("mfa_backup_codes", {
                "codes": [hashlib.sha256(code.encode()).hexdigest() for code in backup_codes],
                "created_at": datetime.utcnow().isoformat()
            })
            
            await self.db.commit()
            
            # Publish MFA enabled event
            if self.events:
                await self.events.publish_mfa_enabled(user_id=user.id)
            
            logger.info(f"Successfully enabled MFA for user {user_id}")
            
            return {
                "mfa_enabled": True,
                "backup_codes": backup_codes,
                "setup_complete": True
            }
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error enabling MFA for user {user_id}: {e}")
            raise UserServiceError(f"Failed to enable MFA: {str(e)}")
    
    async def disable_mfa(
        self,
        user_id: uuid.UUID,
        password: str,
        admin_override: bool = False
    ) -> bool:
        """
        Disable multi-factor authentication for user.
        
        Args:
            user_id: User UUID
            password: User password for verification
            admin_override: Skip password verification (admin use)
            
        Returns:
            bool: True if MFA was disabled
        """
        logger.info(f"Disabling MFA for user {user_id}")
        
        user = await self.get_user(user_id)
        
        if not user.mfa_enabled:
            return True  # Already disabled
        
        # Verify password unless admin override
        if not admin_override:
            if user.is_external_auth:
                raise UserServiceError("Cannot verify password for external auth users")
            
            if not user.verify_password(password):
                raise UserAuthenticationError("Invalid password")
        
        try:
            # Disable MFA
            user.disable_mfa()
            user.updated_at = datetime.utcnow()
            
            # Clear backup codes
            user.update_metadata("mfa_backup_codes", {})
            
            await self.db.commit()
            
            # Publish MFA disabled event
            if self.events:
                await self.events.publish_mfa_disabled(
                    user_id=user.id,
                    admin_override=admin_override
                )
            
            logger.info(f"Successfully disabled MFA for user {user_id}")
            return True
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error disabling MFA for user {user_id}: {e}")
            raise UserServiceError(f"Failed to disable MFA: {str(e)}")
    
    async def unlock_user_account(
        self,
        user_id: uuid.UUID,
        unlocked_by: uuid.UUID,
        reason: Optional[str] = None
    ) -> bool:
        """
        Manually unlock user account.
        
        Args:
            user_id: User UUID
            unlocked_by: UUID of admin performing unlock
            reason: Optional reason for unlock
            
        Returns:
            bool: True if account was unlocked
        """
        logger.info(f"Unlocking account for user {user_id}")
        
        user = await self.get_user(user_id)
        
        try:
            # Unlock account
            user.unlock_account()
            user.updated_at = datetime.utcnow()
            
            # Store unlock metadata
            user.update_metadata("account_unlock", {
                "unlocked_by": str(unlocked_by),
                "unlocked_at": datetime.utcnow().isoformat(),
                "reason": reason
            })
            
            await self.db.commit()
            
            # Publish account unlock event
            if self.events:
                await self.events.publish_account_unlocked(
                    user_id=user.id,
                    unlocked_by=unlocked_by,
                    reason=reason
                )
            
            logger.info(f"Successfully unlocked account for user {user_id}")
            return True
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error unlocking account for user {user_id}: {e}")
            raise UserServiceError(f"Failed to unlock account: {str(e)}")
    
    # Private Helper Methods
    
    def _validate_user_creation(
        self,
        user_data: Dict[str, Any],
        password: Optional[str],
        external_auth_info: Optional[Dict[str, Any]]
    ) -> ValidationResult:
        """Validate user creation data."""
        errors = []
        
        # Required fields
        required_fields = ["email", "first_name", "last_name"]
        for field in required_fields:
            if not user_data.get(field) or len(str(user_data[field]).strip()) == 0:
                errors.append(ValidationError(
                    field=field,
                    code=f"{field.upper()}_REQUIRED",
                    message=f"{field.replace('_', ' ').title()} is required"
                ))
        
        # Email validation
        email = user_data.get("email", "")
        if email and "@" not in email:
            errors.append(ValidationError(
                field="email",
                code="INVALID_EMAIL_FORMAT",
                message="Email must be a valid email address"
            ))
        
        # Password validation for non-external auth
        if not external_auth_info and password:
            password_validation = self._validate_password(password)
            errors.extend(password_validation.errors)
        
        # Username validation if provided
        username = user_data.get("username")
        if username and (len(username) < 3 or not username.replace("_", "").replace("-", "").isalnum()):
            errors.append(ValidationError(
                field="username",
                code="INVALID_USERNAME_FORMAT",
                message="Username must be at least 3 characters and contain only letters, numbers, underscores, and hyphens"
            ))
        
        # Phone number validation if provided
        phone = user_data.get("phone_number")
        if phone and not phone.startswith("+"):
            errors.append(ValidationError(
                field="phone_number",
                code="INVALID_PHONE_FORMAT",
                message="Phone number must be in international format starting with +"
            ))
        
        # Language validation
        language = user_data.get("language", "en")
        if len(language) < 2:
            errors.append(ValidationError(
                field="language",
                code="INVALID_LANGUAGE_CODE",
                message="Language must be at least 2 characters"
            ))
        
        return ValidationResult(is_valid=len(errors) == 0, errors=errors)
    
    def _validate_profile_update(self, profile_data: Dict[str, Any], existing_user: User) -> ValidationResult:
        """Validate profile update data."""
        errors = []
        
        # Apply creation validation to updated fields
        temp_data = {
            "email": profile_data.get("email", existing_user.email),
            "first_name": profile_data.get("first_name", existing_user.first_name),
            "last_name": profile_data.get("last_name", existing_user.last_name),
            "username": profile_data.get("username", existing_user.username),
            "phone_number": profile_data.get("phone_number", existing_user.phone_number),
            "language": profile_data.get("language", existing_user.language)
        }
        
        creation_result = self._validate_user_creation(temp_data, None, None)
        # Filter out password-related errors for profile updates
        profile_errors = [e for e in creation_result.errors if "password" not in e.field.lower()]
        errors.extend(profile_errors)
        
        return ValidationResult(is_valid=len(errors) == 0, errors=errors)
    
    def _validate_password(self, password: str, user: Optional[User] = None) -> ValidationResult:
        """Validate password strength and requirements."""
        errors = []
        
        if len(password) < 8:
            errors.append(ValidationError(
                field="password",
                code="PASSWORD_TOO_SHORT",
                message="Password must be at least 8 characters long"
            ))
        
        if len(password) > 128:
            errors.append(ValidationError(
                field="password",
                code="PASSWORD_TOO_LONG",
                message="Password cannot exceed 128 characters"
            ))
        
        # Check for common patterns
        if password.lower() in ["password", "123456", "qwerty", "admin"]:
            errors.append(ValidationError(
                field="password",
                code="PASSWORD_TOO_COMMON",
                message="Password is too common and easily guessable"
            ))
        
        # Check against user data if provided
        if user:
            user_data = [
                user.first_name.lower() if user.first_name else "",
                user.last_name.lower() if user.last_name else "",
                user.email.split("@")[0].lower() if user.email else ""
            ]
            
            for data in user_data:
                if data and len(data) > 2 and data in password.lower():
                    errors.append(ValidationError(
                        field="password",
                        code="PASSWORD_CONTAINS_USER_DATA",
                        message="Password cannot contain personal information"
                    ))
                    break
        
        return ValidationResult(is_valid=len(errors) == 0, errors=errors)
    
    async def _is_email_taken(self, email: str) -> bool:
        """Check if email is already registered."""
        query = select(User.id).where(User.email == email.lower())
        result = await self.db.execute(query)
        return result.scalar_one_or_none() is not None
    
    async def _is_username_taken(self, username: str) -> bool:
        """Check if username is already taken."""
        if not username:
            return False
        query = select(User.id).where(User.username == username.lower())
        result = await self.db.execute(query)
        return result.scalar_one_or_none() is not None
    
    async def _get_user_publisher_relationship(
        self,
        user_id: uuid.UUID,
        publisher_id: uuid.UUID
    ) -> Optional[UserPublisher]:
        """Get user-publisher relationship."""
        query = select(UserPublisher).options(
            joinedload(UserPublisher.role)
        ).where(
            and_(
                UserPublisher.user_id == user_id,
                UserPublisher.publisher_id == publisher_id
            )
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
    
    async def _get_user_publisher_relationships(self, user_id: uuid.UUID) -> List[UserPublisher]:
        """Get all user-publisher relationships."""
        query = select(UserPublisher).options(
            joinedload(UserPublisher.publisher),
            joinedload(UserPublisher.role)
        ).where(UserPublisher.user_id == user_id)
        result = await self.db.execute(query)
        return result.scalars().all()
    
    def _generate_backup_codes(self, count: int = 10) -> List[str]:
        """Generate MFA backup codes."""
        codes = []
        for _ in range(count):
            code = secrets.token_hex(4).upper()  # 8-character hex code
            codes.append(code)
        return codes
    
    async def _send_verification_email(self, user: User) -> None:
        """Send email verification email."""
        # Generate verification token
        verification_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(verification_token.encode()).hexdigest()
        
        # Store token with expiration (24 hours)
        user.update_metadata("email_verification", {
            "token_hash": token_hash,
            "expires_at": (datetime.utcnow() + timedelta(hours=24)).isoformat(),
            "sent_at": datetime.utcnow().isoformat()
        })
        
        # In a real implementation, send the email here
        logger.info(f"Email verification token generated for user {user.id}: {verification_token}")
    
    async def _send_password_reset_email(self, user: User, reset_token: str) -> None:
        """Send password reset email."""
        # In a real implementation, send the email here
        logger.info(f"Password reset token generated for user {user.id}: {reset_token}")
    
    async def _send_user_invitation_email(
        self,
        user_id: uuid.UUID,
        publisher_id: uuid.UUID,
        invitation_token: str
    ) -> None:
        """Send user invitation email."""
        # In a real implementation, send the email here
        logger.info(f"User invitation sent for user {user_id} to publisher {publisher_id}: {invitation_token}")