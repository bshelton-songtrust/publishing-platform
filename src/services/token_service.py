"""Token service for managing all types of authentication tokens."""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple, Union
import secrets
import hashlib
from jose import jwt, JWTError

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models import User, Publisher, ServiceAccount, ServiceToken, PersonalAccessToken, UserSession
from src.core.settings import get_settings
from src.services.events import get_event_publisher

logger = logging.getLogger(__name__)
settings = get_settings()


class TokenValidationResult:
    """Result of token validation."""
    
    def __init__(self, is_valid: bool, user_id: str = None, publisher_id: str = None,
                 token_type: str = None, permissions: List[str] = None,
                 error: str = None, token_data: Dict[str, Any] = None):
        self.is_valid = is_valid
        self.user_id = user_id
        self.publisher_id = publisher_id
        self.token_type = token_type
        self.permissions = permissions or []
        self.error = error
        self.token_data = token_data or {}


class TokenService:
    """
    Comprehensive token service for managing all types of authentication tokens.
    
    Handles:
    - User JWT tokens (access/refresh)
    - Service tokens (API keys)
    - Personal Access Tokens (PATs)
    - Token validation and verification
    - Token rotation and revocation
    """
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.event_publisher = get_event_publisher()
    
    # JWT Token Methods
    
    async def create_user_token(self, user: User, publisher_id: str = None,
                               session_id: str = None, expires_delta: timedelta = None) -> str:
        """Create a JWT access token for a user."""
        if expires_delta is None:
            expires_delta = timedelta(minutes=settings.jwt_access_token_expire_minutes)
        
        # Get user's publisher relationships and permissions
        publisher_data = await self._get_user_publisher_data(user.id, publisher_id)
        
        # Create token payload
        payload = {
            "sub": str(user.id),
            "type": "user",
            "email": user.email,
            "publisher_id": publisher_id,
            "publishers": [str(p["id"]) for p in publisher_data],
            "role": publisher_data[0]["role"] if publisher_data else None,
            "permissions": publisher_data[0]["permissions"] if publisher_data else [],
            "session_id": session_id,
            "exp": datetime.utcnow() + expires_delta,
            "iat": datetime.utcnow(),
            "nbf": datetime.utcnow()
        }
        
        token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
        
        # Log token creation
        logger.info(f"Created user token for user {user.id}, publisher {publisher_id}")
        
        return token
    
    async def create_refresh_token(self, user: User, publisher_id: str = None,
                                  session_id: str = None) -> str:
        """Create a refresh token for token renewal."""
        expires_delta = timedelta(days=settings.jwt_refresh_token_expire_days)
        
        payload = {
            "sub": str(user.id),
            "type": "refresh",
            "publisher_id": publisher_id,
            "session_id": session_id,
            "exp": datetime.utcnow() + expires_delta,
            "iat": datetime.utcnow()
        }
        
        return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    
    # Service Token Methods
    
    async def create_service_token(self, service_account: ServiceAccount, name: str,
                                  expires_at: datetime = None, scopes: List[str] = None) -> Tuple[str, ServiceToken]:
        """Create a new service token."""
        # Generate the actual token
        raw_token, token_hash = ServiceToken.generate_token(prefix="srv")
        
        # Create token record
        service_token = ServiceToken(
            service_account_id=service_account.id,
            name=name,
            token_prefix="srv",
            token_hash=token_hash,
            token_suffix=ServiceToken.extract_suffix(raw_token),
            expires_at=expires_at,
            scopes=scopes
        )
        
        self.session.add(service_token)
        await self.session.commit()
        await self.session.refresh(service_token)
        
        # Publish event
        await self.event_publisher.publish("service_token.created", {
            "service_account_id": str(service_account.id),
            "token_id": str(service_token.id),
            "name": name,
            "publisher_id": str(service_account.publisher_id) if service_account.publisher_id else None
        })
        
        logger.info(f"Created service token {service_token.id} for service account {service_account.id}")
        
        return raw_token, service_token
    
    async def create_personal_access_token(self, user: User, name: str, description: str = None,
                                          publisher_id: str = None, scopes: List[str] = None,
                                          expires_at: datetime = None) -> Tuple[str, PersonalAccessToken]:
        """Create a new personal access token."""
        # Generate the actual token
        raw_token, token_hash = PersonalAccessToken.generate_token(prefix="pat")
        
        # Create token record
        pat = PersonalAccessToken(
            user_id=user.id,
            publisher_id=publisher_id,
            name=name,
            description=description,
            token_hash=token_hash,
            token_suffix=PersonalAccessToken.extract_suffix(raw_token),
            expires_at=expires_at,
            scopes=scopes
        )
        
        self.session.add(pat)
        await self.session.commit()
        await self.session.refresh(pat)
        
        # Publish event
        await self.event_publisher.publish("personal_access_token.created", {
            "user_id": str(user.id),
            "token_id": str(pat.id),
            "name": name,
            "publisher_id": publisher_id
        })
        
        logger.info(f"Created personal access token {pat.id} for user {user.id}")
        
        return raw_token, pat
    
    # Token Validation Methods
    
    async def validate_token(self, token: str, token_type: str = None) -> TokenValidationResult:
        """
        Validate any type of token and return validation result.
        
        Args:
            token: The token to validate
            token_type: Expected token type ('user', 'service', 'pat') or None for auto-detect
        """
        try:
            # Try to detect token type if not specified
            if token_type is None:
                token_type = self._detect_token_type(token)
            
            if token_type == "user" or token.startswith("eyJ"):  # JWT tokens
                return await self._validate_jwt_token(token)
            elif token_type == "service" or token.startswith("srv_"):
                return await self._validate_service_token(token)
            elif token_type == "pat" or token.startswith("pat_"):
                return await self._validate_personal_access_token(token)
            else:
                return TokenValidationResult(False, error="Unknown token type")
                
        except Exception as e:
            logger.error(f"Token validation error: {e}")
            return TokenValidationResult(False, error="Token validation failed")
    
    async def _validate_jwt_token(self, token: str) -> TokenValidationResult:
        """Validate a JWT token."""
        try:
            payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
            
            user_id = payload.get("sub")
            publisher_id = payload.get("publisher_id")
            token_type = payload.get("type", "user")
            permissions = payload.get("permissions", [])
            
            # Verify user still exists and is active
            user = await self.session.get(User, user_id)
            if not user or not user.can_login():
                return TokenValidationResult(False, error="User not found or inactive")
            
            # Verify publisher access if specified
            if publisher_id:
                has_access = await self._verify_user_publisher_access(user_id, publisher_id)
                if not has_access:
                    return TokenValidationResult(False, error="No access to specified publisher")
            
            return TokenValidationResult(
                is_valid=True,
                user_id=user_id,
                publisher_id=publisher_id,
                token_type=token_type,
                permissions=permissions,
                token_data=payload
            )
            
        except JWTError as e:
            return TokenValidationResult(False, error=f"Invalid JWT: {str(e)}")
    
    async def _validate_service_token(self, token: str) -> TokenValidationResult:
        """Validate a service token."""
        token_hash = ServiceToken.hash_token(token)
        
        stmt = select(ServiceToken).options(
            selectinload(ServiceToken.service_account)
        ).where(ServiceToken.token_hash == token_hash)
        
        result = await self.session.execute(stmt)
        service_token = result.scalar_one_or_none()
        
        if not service_token:
            return TokenValidationResult(False, error="Service token not found")
        
        if not service_token.is_valid():
            return TokenValidationResult(False, error="Service token is invalid or expired")
        
        if not service_token.service_account.is_valid():
            return TokenValidationResult(False, error="Service account is invalid or suspended")
        
        # Record usage
        service_token.record_usage()
        service_token.service_account.increment_usage()
        await self.session.commit()
        
        return TokenValidationResult(
            is_valid=True,
            user_id=None,  # Service tokens don't have users
            publisher_id=str(service_token.service_account.publisher_id) if service_token.service_account.publisher_id else None,
            token_type="service",
            permissions=service_token.get_effective_scopes(),
            token_data={
                "service_account_id": str(service_token.service_account.id),
                "service_name": service_token.service_account.name,
                "token_id": str(service_token.id)
            }
        )
    
    async def _validate_personal_access_token(self, token: str) -> TokenValidationResult:
        """Validate a personal access token."""
        token_hash = PersonalAccessToken.hash_token(token)
        
        stmt = select(PersonalAccessToken).options(
            selectinload(PersonalAccessToken.user),
            selectinload(PersonalAccessToken.publisher)
        ).where(PersonalAccessToken.token_hash == token_hash)
        
        result = await self.session.execute(stmt)
        pat = result.scalar_one_or_none()
        
        if not pat:
            return TokenValidationResult(False, error="Personal access token not found")
        
        if not pat.is_valid():
            return TokenValidationResult(False, error="Personal access token is invalid or expired")
        
        if not pat.user.can_login():
            return TokenValidationResult(False, error="Associated user is inactive")
        
        # Verify publisher access if token is scoped to a publisher
        if pat.publisher_id:
            has_access = await self._verify_user_publisher_access(str(pat.user_id), str(pat.publisher_id))
            if not has_access:
                return TokenValidationResult(False, error="User no longer has access to token's publisher")
        
        # Record usage
        pat.record_usage()
        await self.session.commit()
        
        # Get effective permissions
        if pat.inherit_user_permissions:
            permissions = await self._get_user_permissions(str(pat.user_id), str(pat.publisher_id) if pat.publisher_id else None)
        else:
            permissions = pat.get_effective_scopes()
        
        return TokenValidationResult(
            is_valid=True,
            user_id=str(pat.user_id),
            publisher_id=str(pat.publisher_id) if pat.publisher_id else None,
            token_type="pat",
            permissions=permissions,
            token_data={
                "token_id": str(pat.id),
                "token_name": pat.name,
                "inherit_user_permissions": pat.inherit_user_permissions
            }
        )
    
    # Token Management Methods
    
    async def rotate_service_token(self, token_id: str, new_name: str = None) -> Tuple[str, ServiceToken]:
        """Rotate a service token."""
        stmt = select(ServiceToken).options(
            selectinload(ServiceToken.service_account)
        ).where(ServiceToken.id == token_id)
        
        result = await self.session.execute(stmt)
        old_token = result.scalar_one_or_none()
        
        if not old_token:
            raise ValueError("Service token not found")
        
        # Create new token
        new_name = new_name or f"{old_token.name} (rotated)"
        raw_token, new_token = await self.create_service_token(
            old_token.service_account,
            new_name,
            old_token.expires_at,
            old_token.scopes
        )
        
        # Start rotation on old token
        old_token.start_rotation()
        new_token.rotated_from_id = old_token.id
        old_token.rotated_to_id = new_token.id
        
        await self.session.commit()
        
        # Publish event
        await self.event_publisher.publish("service_token.rotated", {
            "old_token_id": str(old_token.id),
            "new_token_id": str(new_token.id),
            "service_account_id": str(old_token.service_account.id)
        })
        
        logger.info(f"Rotated service token {old_token.id} to {new_token.id}")
        
        return raw_token, new_token
    
    async def revoke_token(self, token_id: str, token_type: str, user_id: str = None, reason: str = None) -> bool:
        """Revoke a token by ID."""
        if token_type == "service":
            stmt = select(ServiceToken).where(ServiceToken.id == token_id)
            result = await self.session.execute(stmt)
            token = result.scalar_one_or_none()
        elif token_type == "pat":
            stmt = select(PersonalAccessToken).where(PersonalAccessToken.id == token_id)
            result = await self.session.execute(stmt)
            token = result.scalar_one_or_none()
        else:
            raise ValueError(f"Unsupported token type for revocation: {token_type}")
        
        if not token:
            return False
        
        token.revoke(user_id, reason)
        await self.session.commit()
        
        # Publish event
        await self.event_publisher.publish(f"{token_type}_token.revoked", {
            "token_id": str(token.id),
            "revoked_by": user_id,
            "reason": reason
        })
        
        logger.info(f"Revoked {token_type} token {token.id}")
        
        return True
    
    async def cleanup_expired_tokens(self) -> Dict[str, int]:
        """Clean up expired tokens."""
        now = datetime.utcnow()
        counts = {"service_tokens": 0, "personal_access_tokens": 0}
        
        # Service tokens
        stmt = select(ServiceToken).where(
            and_(
                ServiceToken.expires_at.isnot(None),
                ServiceToken.expires_at < now,
                ServiceToken.status != "revoked"
            )
        )
        result = await self.session.execute(stmt)
        expired_service_tokens = result.scalars().all()
        
        for token in expired_service_tokens:
            token.status = "expired"
            token.is_active = False
            counts["service_tokens"] += 1
        
        # Personal access tokens
        stmt = select(PersonalAccessToken).where(
            and_(
                PersonalAccessToken.expires_at.isnot(None),
                PersonalAccessToken.expires_at < now,
                PersonalAccessToken.status != "revoked"
            )
        )
        result = await self.session.execute(stmt)
        expired_pats = result.scalars().all()
        
        for token in expired_pats:
            token.status = "expired"
            token.is_active = False
            counts["personal_access_tokens"] += 1
        
        if counts["service_tokens"] > 0 or counts["personal_access_tokens"] > 0:
            await self.session.commit()
            logger.info(f"Cleaned up expired tokens: {counts}")
        
        return counts
    
    # Helper Methods
    
    def _detect_token_type(self, token: str) -> str:
        """Detect token type from token format."""
        if token.startswith("eyJ"):  # JWT tokens start with eyJ
            return "user"
        elif token.startswith("srv_"):
            return "service"
        elif token.startswith("pat_"):
            return "pat"
        else:
            return "unknown"
    
    async def _get_user_publisher_data(self, user_id: str, publisher_id: str = None) -> List[Dict[str, Any]]:
        """Get user's publisher relationships and permissions."""
        from src.models import UserPublisher, Role
        
        stmt = select(UserPublisher).options(
            selectinload(UserPublisher.publisher),
            selectinload(UserPublisher.role)
        ).where(UserPublisher.user_id == user_id)
        
        if publisher_id:
            stmt = stmt.where(UserPublisher.publisher_id == publisher_id)
        
        result = await self.session.execute(stmt)
        user_publishers = result.scalars().all()
        
        publisher_data = []
        for up in user_publishers:
            role_permissions = []
            if up.role:
                role_permissions = up.role.permissions or []
            
            # Add individual permissions
            individual_permissions = up.permissions or []
            all_permissions = list(set(role_permissions + individual_permissions))
            
            publisher_data.append({
                "id": up.publisher_id,
                "name": up.publisher.name if up.publisher else None,
                "role": up.role.name if up.role else up.legacy_role,
                "permissions": all_permissions
            })
        
        return publisher_data
    
    async def _verify_user_publisher_access(self, user_id: str, publisher_id: str) -> bool:
        """Verify user has access to a publisher."""
        from src.models import UserPublisher
        
        stmt = select(UserPublisher).where(
            and_(
                UserPublisher.user_id == user_id,
                UserPublisher.publisher_id == publisher_id,
                UserPublisher.status == "active"
            )
        )
        
        result = await self.session.execute(stmt)
        user_publisher = result.scalar_one_or_none()
        
        return user_publisher is not None
    
    async def _get_user_permissions(self, user_id: str, publisher_id: str = None) -> List[str]:
        """Get effective permissions for a user in a publisher context."""
        publisher_data = await self._get_user_publisher_data(user_id, publisher_id)
        
        if not publisher_data:
            return []
        
        # Return permissions from the first (or specified) publisher
        return publisher_data[0]["permissions"]