"""Service for managing service accounts and their tokens."""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from uuid import UUID

from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models import Publisher, User, ServiceAccount, ServiceToken
from src.services.events import get_event_publisher

logger = logging.getLogger(__name__)


class ServiceAccountService:
    """
    Service for managing service accounts and their API tokens.
    
    Handles:
    - Service account lifecycle (create, update, suspend, delete)
    - Token management (create, rotate, revoke)
    - Usage tracking and analytics
    - Security monitoring and alerts
    - Rate limiting configuration
    """
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.event_publisher = get_event_publisher()
    
    # Service Account Management
    
    async def create_service_account(
        self,
        name: str,
        display_name: str,
        description: str,
        service_type: str,
        publisher_id: str = None,
        owner_user_id: str = None,
        owner_email: str = None,
        scopes: List[str] = None,
        **kwargs
    ) -> ServiceAccount:
        """Create a new service account."""
        
        # Validate publisher exists if specified
        if publisher_id:
            publisher = await self.session.get(Publisher, publisher_id)
            if not publisher:
                raise ValueError(f"Publisher {publisher_id} not found")
        
        # Validate owner user exists if specified
        if owner_user_id:
            owner = await self.session.get(User, owner_user_id)
            if not owner:
                raise ValueError(f"Owner user {owner_user_id} not found")
            if not owner_email:
                owner_email = owner.email
        
        # Create service account
        service_account = ServiceAccount(
            name=name,
            display_name=display_name,
            description=description,
            service_type=service_type,
            publisher_id=publisher_id,
            owner_user_id=owner_user_id,
            owner_email=owner_email or f"{name}@example.com",
            scopes=scopes or [],
            **kwargs
        )
        
        self.session.add(service_account)
        await self.session.commit()
        await self.session.refresh(service_account)
        
        # Publish event
        await self.event_publisher.publish("service_account.created", {
            "service_account_id": str(service_account.id),
            "name": name,
            "service_type": service_type,
            "publisher_id": publisher_id,
            "owner_user_id": owner_user_id
        })
        
        logger.info(f"Created service account {service_account.id}: {name}")
        
        return service_account
    
    async def get_service_account(
        self,
        service_account_id: str,
        include_tokens: bool = False,
        include_publisher: bool = False
    ) -> Optional[ServiceAccount]:
        """Get a service account by ID."""
        
        stmt = select(ServiceAccount).where(ServiceAccount.id == service_account_id)
        
        if include_tokens:
            stmt = stmt.options(selectinload(ServiceAccount.tokens))
        if include_publisher:
            stmt = stmt.options(selectinload(ServiceAccount.publisher))
        
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_service_account_by_name(self, name: str) -> Optional[ServiceAccount]:
        """Get a service account by name."""
        stmt = select(ServiceAccount).where(ServiceAccount.name == name)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def list_service_accounts(
        self,
        publisher_id: str = None,
        service_type: str = None,
        status: str = None,
        owner_user_id: str = None,
        limit: int = 50,
        offset: int = 0,
        include_usage: bool = False
    ) -> List[ServiceAccount]:
        """List service accounts with filtering."""
        
        stmt = select(ServiceAccount)
        
        # Apply filters
        filters = []
        if publisher_id:
            filters.append(ServiceAccount.publisher_id == publisher_id)
        if service_type:
            filters.append(ServiceAccount.service_type == service_type)
        if status:
            filters.append(ServiceAccount.status == status)
        if owner_user_id:
            filters.append(ServiceAccount.owner_user_id == owner_user_id)
        
        if filters:
            stmt = stmt.where(and_(*filters))
        
        # Apply pagination
        stmt = stmt.offset(offset).limit(limit)
        
        # Order by created date
        stmt = stmt.order_by(ServiceAccount.created_at.desc())
        
        if include_usage:
            stmt = stmt.options(selectinload(ServiceAccount.tokens))
        
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
    
    async def update_service_account(
        self,
        service_account_id: str,
        **updates
    ) -> Optional[ServiceAccount]:
        """Update a service account."""
        
        service_account = await self.get_service_account(service_account_id)
        if not service_account:
            return None
        
        # Track changes for audit
        changes = {}
        for key, value in updates.items():
            if hasattr(service_account, key) and getattr(service_account, key) != value:
                changes[key] = {
                    "old": getattr(service_account, key),
                    "new": value
                }
                setattr(service_account, key, value)
        
        if changes:
            await self.session.commit()
            
            # Publish event
            await self.event_publisher.publish("service_account.updated", {
                "service_account_id": str(service_account.id),
                "changes": changes
            })
            
            logger.info(f"Updated service account {service_account.id}: {list(changes.keys())}")
        
        return service_account
    
    async def suspend_service_account(
        self,
        service_account_id: str,
        reason: str,
        suspended_by: str = None
    ) -> bool:
        """Suspend a service account."""
        
        service_account = await self.get_service_account(service_account_id, include_tokens=True)
        if not service_account:
            return False
        
        service_account.suspend(reason)
        
        # Also suspend all active tokens
        if service_account.tokens:
            for token in service_account.tokens:
                if token.is_active:
                    token.suspend(f"Service account suspended: {reason}")
        
        await self.session.commit()
        
        # Publish event
        await self.event_publisher.publish("service_account.suspended", {
            "service_account_id": str(service_account.id),
            "reason": reason,
            "suspended_by": suspended_by
        })
        
        logger.warning(f"Suspended service account {service_account.id}: {reason}")
        
        return True
    
    async def reactivate_service_account(
        self,
        service_account_id: str,
        reactivated_by: str = None
    ) -> bool:
        """Reactivate a suspended service account."""
        
        service_account = await self.get_service_account(service_account_id, include_tokens=True)
        if not service_account:
            return False
        
        if service_account.status != "suspended":
            return False
        
        service_account.reactivate()
        await self.session.commit()
        
        # Publish event
        await self.event_publisher.publish("service_account.reactivated", {
            "service_account_id": str(service_account.id),
            "reactivated_by": reactivated_by
        })
        
        logger.info(f"Reactivated service account {service_account.id}")
        
        return True
    
    async def delete_service_account(self, service_account_id: str) -> bool:
        """Delete a service account (soft delete by revoking)."""
        
        service_account = await self.get_service_account(service_account_id, include_tokens=True)
        if not service_account:
            return False
        
        # Revoke all tokens
        if service_account.tokens:
            for token in service_account.tokens:
                if token.is_active:
                    token.revoke(reason="Service account deleted")
        
        # Revoke the service account
        service_account.revoke()
        await self.session.commit()
        
        # Publish event
        await self.event_publisher.publish("service_account.deleted", {
            "service_account_id": str(service_account.id)
        })
        
        logger.warning(f"Deleted service account {service_account.id}")
        
        return True
    
    # Token Management
    
    async def create_token(
        self,
        service_account_id: str,
        name: str,
        expires_at: datetime = None,
        scopes: List[str] = None
    ) -> tuple[str, ServiceToken]:
        """Create a new token for a service account."""
        
        service_account = await self.get_service_account(service_account_id)
        if not service_account:
            raise ValueError(f"Service account {service_account_id} not found")
        
        if not service_account.is_valid():
            raise ValueError("Service account is not active")
        
        # Import here to avoid circular imports
        from src.services.token_service import TokenService
        token_service = TokenService(self.session)
        
        return await token_service.create_service_token(
            service_account, name, expires_at, scopes
        )
    
    async def list_tokens(
        self,
        service_account_id: str,
        include_inactive: bool = False
    ) -> List[ServiceToken]:
        """List tokens for a service account."""
        
        stmt = select(ServiceToken).where(ServiceToken.service_account_id == service_account_id)
        
        if not include_inactive:
            stmt = stmt.where(ServiceToken.is_active == True)
        
        stmt = stmt.order_by(ServiceToken.created_at.desc())
        
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
    
    async def rotate_token(self, token_id: str, new_name: str = None) -> tuple[str, ServiceToken]:
        """Rotate a service token."""
        from src.services.token_service import TokenService
        token_service = TokenService(self.session)
        
        return await token_service.rotate_service_token(token_id, new_name)
    
    async def revoke_token(self, token_id: str, reason: str = None) -> bool:
        """Revoke a service token."""
        from src.services.token_service import TokenService
        token_service = TokenService(self.session)
        
        return await token_service.revoke_token(token_id, "service", reason=reason)
    
    # Usage and Analytics
    
    async def get_usage_stats(
        self,
        service_account_id: str,
        period_days: int = 30
    ) -> Dict[str, Any]:
        """Get usage statistics for a service account."""
        
        service_account = await self.get_service_account(service_account_id, include_tokens=True)
        if not service_account:
            return {}
        
        # Calculate period start
        period_start = datetime.utcnow() - timedelta(days=period_days)
        
        # Aggregate token usage
        total_requests = 0
        total_errors = 0
        active_tokens = 0
        
        for token in service_account.tokens or []:
            if token.is_active:
                active_tokens += 1
            total_requests += token.total_requests or 0
            total_errors += token.total_errors or 0
        
        # Calculate error rate
        error_rate = (total_errors / total_requests * 100) if total_requests > 0 else 0
        
        return {
            "service_account_id": str(service_account.id),
            "period_days": period_days,
            "total_requests": service_account.total_requests or 0,
            "total_errors": service_account.total_errors or 0,
            "error_rate": error_rate,
            "active_tokens": active_tokens,
            "total_tokens": len(service_account.tokens or []),
            "last_used_at": service_account.last_used_at.isoformat() if service_account.last_used_at else None,
            "monthly_usage": service_account.monthly_usage or {},
            "rate_limits": {
                "per_minute": service_account.rate_limit_per_minute,
                "per_hour": service_account.rate_limit_per_hour,
                "per_day": service_account.rate_limit_per_day,
                "burst": service_account.burst_limit
            }
        }
    
    async def get_security_events(
        self,
        service_account_id: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get security events for a service account and its tokens."""
        
        service_account = await self.get_service_account(service_account_id, include_tokens=True)
        if not service_account:
            return []
        
        events = []
        
        # Collect events from all tokens
        for token in service_account.tokens or []:
            if token.security_events:
                for event in token.security_events[-limit:]:  # Get recent events
                    events.append({
                        **event,
                        "token_id": str(token.id),
                        "token_name": token.name
                    })
        
        # Sort by timestamp (most recent first)
        events.sort(key=lambda x: x["timestamp"], reverse=True)
        
        return events[:limit]
    
    # IP and Security Management
    
    async def add_allowed_ip(self, service_account_id: str, ip_address: str) -> bool:
        """Add an IP address to the allowed list."""
        
        service_account = await self.get_service_account(service_account_id)
        if not service_account:
            return False
        
        if not service_account.allowed_ips:
            service_account.allowed_ips = []
        
        if ip_address not in service_account.allowed_ips:
            service_account.allowed_ips.append(ip_address)
            await self.session.commit()
            
            logger.info(f"Added allowed IP {ip_address} to service account {service_account.id}")
        
        return True
    
    async def remove_allowed_ip(self, service_account_id: str, ip_address: str) -> bool:
        """Remove an IP address from the allowed list."""
        
        service_account = await self.get_service_account(service_account_id)
        if not service_account:
            return False
        
        if service_account.allowed_ips and ip_address in service_account.allowed_ips:
            service_account.allowed_ips.remove(ip_address)
            await self.session.commit()
            
            logger.info(f"Removed allowed IP {ip_address} from service account {service_account.id}")
        
        return True
    
    async def update_rate_limits(
        self,
        service_account_id: str,
        per_minute: int = None,
        per_hour: int = None,
        per_day: int = None,
        burst: int = None
    ) -> bool:
        """Update rate limits for a service account."""
        
        service_account = await self.get_service_account(service_account_id)
        if not service_account:
            return False
        
        changes = {}
        if per_minute is not None:
            changes["rate_limit_per_minute"] = per_minute
            service_account.rate_limit_per_minute = per_minute
        if per_hour is not None:
            changes["rate_limit_per_hour"] = per_hour
            service_account.rate_limit_per_hour = per_hour
        if per_day is not None:
            changes["rate_limit_per_day"] = per_day
            service_account.rate_limit_per_day = per_day
        if burst is not None:
            changes["burst_limit"] = burst
            service_account.burst_limit = burst
        
        if changes:
            await self.session.commit()
            
            # Publish event
            await self.event_publisher.publish("service_account.rate_limits_updated", {
                "service_account_id": str(service_account.id),
                "changes": changes
            })
            
            logger.info(f"Updated rate limits for service account {service_account.id}: {changes}")
        
        return True
    
    # Webhook Management
    
    async def update_webhook_config(
        self,
        service_account_id: str,
        webhook_url: str = None,
        webhook_events: List[str] = None,
        regenerate_secret: bool = False
    ) -> Optional[str]:
        """Update webhook configuration."""
        
        service_account = await self.get_service_account(service_account_id)
        if not service_account:
            return None
        
        webhook_secret = None
        
        if webhook_url is not None:
            service_account.webhook_url = webhook_url
        
        if webhook_events is not None:
            service_account.webhook_events = webhook_events
        
        if regenerate_secret or (webhook_url and not service_account.webhook_secret):
            webhook_secret = service_account.generate_webhook_secret()
        
        await self.session.commit()
        
        logger.info(f"Updated webhook config for service account {service_account.id}")
        
        return webhook_secret
    
    # Utility Methods
    
    async def validate_service_access(
        self,
        service_account_id: str,
        publisher_id: str = None,
        resource_type: str = None,
        resource_id: str = None
    ) -> bool:
        """Validate if a service account has access to specific resources."""
        
        service_account = await self.get_service_account(service_account_id)
        if not service_account or not service_account.is_valid():
            return False
        
        # Check publisher access
        if publisher_id and not service_account.can_access_publisher(publisher_id):
            return False
        
        # Check resource access
        if resource_type and resource_id:
            if not service_account.can_access_resource(resource_type, resource_id):
                return False
        
        return True