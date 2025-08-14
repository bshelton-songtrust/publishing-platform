"""Publisher service layer for comprehensive publisher management in the multi-tenant platform.

This service provides complete business logic for publisher CRUD operations, settings management,
user management, and business rule enforcement. It follows established service patterns and
integrates with all publisher-related models.
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple, Union
from decimal import Decimal

from sqlalchemy import and_, or_, func, desc, asc
from sqlalchemy.orm import AsyncSession, selectinload, joinedload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError, NoResultFound

from src.models.publisher import Publisher
from src.models.account import Account
from src.models.user import User
from src.models.user_publisher import UserPublisher
from src.models.role import Role
from src.services.business_rules import ValidationResult, ValidationError, TenantContext
from src.services.events import EventPublisher

logger = logging.getLogger(__name__)


class PublisherServiceError(Exception):
    """Base exception for publisher service errors."""
    pass


class PublisherNotFoundError(PublisherServiceError):
    """Raised when a publisher cannot be found."""
    pass


class PublisherValidationError(PublisherServiceError):
    """Raised when publisher data validation fails."""
    
    def __init__(self, message: str, validation_errors: List[ValidationError] = None):
        super().__init__(message)
        self.validation_errors = validation_errors or []


class PublisherPermissionError(PublisherServiceError):
    """Raised when user lacks permission for publisher operation."""
    pass


class PublisherService:
    """
    Comprehensive Publisher service for multi-tenant publishing platform.
    
    This service provides complete business logic for:
    - Publisher CRUD operations with validation
    - Settings and configuration management
    - User relationship management
    - Business model and type changes
    - Account integration and billing
    - Multi-tenant security enforcement
    """
    
    def __init__(self, db_session: AsyncSession, event_publisher: EventPublisher = None):
        """
        Initialize the PublisherService.
        
        Args:
            db_session: Async database session
            event_publisher: Optional event publisher for async operations
        """
        self.db = db_session
        self.events = event_publisher
        
    # Core CRUD Operations
    
    async def create_publisher(
        self,
        publisher_data: Dict[str, Any],
        creator_user_id: Optional[uuid.UUID] = None,
        account_data: Optional[Dict[str, Any]] = None
    ) -> Tuple[Publisher, Account]:
        """
        Create a new publisher with account setup and validation.
        
        Args:
            publisher_data: Publisher information
            creator_user_id: UUID of user creating the publisher
            account_data: Optional account/billing information
            
        Returns:
            Tuple[Publisher, Account]: Created publisher and account
            
        Raises:
            PublisherValidationError: If validation fails
            PublisherServiceError: If creation fails
        """
        logger.info(f"Creating new publisher: {publisher_data.get('name')}")
        
        # Validate publisher data
        validation_result = self._validate_publisher_creation(publisher_data)
        if not validation_result.is_valid:
            raise PublisherValidationError(
                "Publisher validation failed",
                validation_result.errors
            )
        
        # Check subdomain availability
        if await self._is_subdomain_taken(publisher_data["subdomain"]):
            raise PublisherValidationError("Subdomain is already taken")
        
        try:
            # Create publisher
            publisher = Publisher(**publisher_data)
            self.db.add(publisher)
            await self.db.flush()  # Get publisher ID
            
            # Create associated account
            account_data = account_data or {}
            account_defaults = {
                "publisher_id": publisher.id,
                "plan_type": "starter",
                "billing_cycle": "monthly",
                "status": "trial",
                "seats_licensed": 5,
                "monthly_price": Decimal("0.00")
            }
            account_data = {**account_defaults, **account_data}
            
            account = Account(**account_data)
            account.start_trial(days=14)  # Default 14-day trial
            self.db.add(account)
            
            # Create default roles for this publisher
            await self._create_default_roles(publisher.id)
            
            # If creator_user_id provided, add them as owner
            if creator_user_id:
                await self._add_creator_as_owner(publisher.id, creator_user_id)
            
            await self.db.commit()
            
            # Publish creation event
            if self.events:
                await self.events.publish_publisher_created(
                    publisher_id=publisher.id,
                    created_by=creator_user_id
                )
            
            logger.info(f"Successfully created publisher {publisher.id}")
            return publisher, account
            
        except IntegrityError as e:
            await self.db.rollback()
            logger.error(f"Database integrity error creating publisher: {e}")
            raise PublisherServiceError("Failed to create publisher due to data constraint violation")
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error creating publisher: {e}")
            raise PublisherServiceError(f"Failed to create publisher: {str(e)}")
    
    async def get_publisher(
        self,
        publisher_id: uuid.UUID,
        include_relationships: bool = False
    ) -> Publisher:
        """
        Get publisher by ID with optional relationship loading.
        
        Args:
            publisher_id: Publisher UUID
            include_relationships: Whether to load related entities
            
        Returns:
            Publisher: Found publisher
            
        Raises:
            PublisherNotFoundError: If publisher not found
        """
        try:
            query = select(Publisher).where(Publisher.id == publisher_id)
            
            if include_relationships:
                query = query.options(
                    joinedload(Publisher.account),
                    selectinload(Publisher.user_relationships).joinedload(UserPublisher.user),
                    selectinload(Publisher.roles)
                )
            
            result = await self.db.execute(query)
            publisher = result.scalar_one()
            
            return publisher
            
        except NoResultFound:
            logger.warning(f"Publisher {publisher_id} not found")
            raise PublisherNotFoundError(f"Publisher {publisher_id} not found")
        except Exception as e:
            logger.error(f"Error retrieving publisher {publisher_id}: {e}")
            raise PublisherServiceError(f"Failed to retrieve publisher: {str(e)}")
    
    async def get_publisher_by_subdomain(self, subdomain: str) -> Optional[Publisher]:
        """
        Get publisher by subdomain.
        
        Args:
            subdomain: Publisher subdomain
            
        Returns:
            Optional[Publisher]: Found publisher or None
        """
        try:
            query = select(Publisher).where(Publisher.subdomain == subdomain.lower())
            result = await self.db.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error retrieving publisher by subdomain {subdomain}: {e}")
            raise PublisherServiceError(f"Failed to retrieve publisher: {str(e)}")
    
    async def update_publisher(
        self,
        publisher_id: uuid.UUID,
        update_data: Dict[str, Any],
        updated_by: uuid.UUID
    ) -> Publisher:
        """
        Update publisher information with validation.
        
        Args:
            publisher_id: Publisher UUID
            update_data: Fields to update
            updated_by: UUID of user making the update
            
        Returns:
            Publisher: Updated publisher
            
        Raises:
            PublisherNotFoundError: If publisher not found
            PublisherValidationError: If validation fails
        """
        logger.info(f"Updating publisher {publisher_id}")
        
        publisher = await self.get_publisher(publisher_id)
        
        # Validate update data
        validation_result = self._validate_publisher_update(update_data, publisher)
        if not validation_result.is_valid:
            raise PublisherValidationError(
                "Publisher update validation failed",
                validation_result.errors
            )
        
        # Check subdomain availability if changing
        if ("subdomain" in update_data and 
            update_data["subdomain"] != publisher.subdomain and
            await self._is_subdomain_taken(update_data["subdomain"])):
            raise PublisherValidationError("Subdomain is already taken")
        
        try:
            # Update allowed fields
            updatable_fields = {
                "name", "primary_contact_email", "support_email", 
                "business_address", "tax_id", "business_license",
                "subdomain"
            }
            
            for field, value in update_data.items():
                if field in updatable_fields:
                    setattr(publisher, field, value)
            
            publisher.updated_at = datetime.utcnow()
            
            await self.db.commit()
            
            # Publish update event
            if self.events:
                await self.events.publish_publisher_updated(
                    publisher_id=publisher.id,
                    updated_by=updated_by,
                    changes=list(update_data.keys())
                )
            
            logger.info(f"Successfully updated publisher {publisher_id}")
            return publisher
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error updating publisher {publisher_id}: {e}")
            raise PublisherServiceError(f"Failed to update publisher: {str(e)}")
    
    async def archive_publisher(
        self,
        publisher_id: uuid.UUID,
        archived_by: uuid.UUID,
        reason: Optional[str] = None
    ) -> Publisher:
        """
        Archive (soft delete) a publisher.
        
        Args:
            publisher_id: Publisher UUID
            archived_by: UUID of user performing the archive
            reason: Optional reason for archiving
            
        Returns:
            Publisher: Archived publisher
        """
        logger.info(f"Archiving publisher {publisher_id}")
        
        publisher = await self.get_publisher(publisher_id)
        
        try:
            # Update status to archived
            publisher.status = "archived"
            publisher.updated_at = datetime.utcnow()
            
            # Update account status as well
            if publisher.account:
                publisher.account.status = "cancelled"
            
            # Store archive metadata
            if not publisher.additional_data:
                publisher.additional_data = {}
            
            publisher.additional_data["archive_info"] = {
                "archived_by": str(archived_by),
                "archived_at": datetime.utcnow().isoformat(),
                "reason": reason
            }
            
            await self.db.commit()
            
            # Publish archive event
            if self.events:
                await self.events.publish_publisher_archived(
                    publisher_id=publisher.id,
                    archived_by=archived_by,
                    reason=reason
                )
            
            logger.info(f"Successfully archived publisher {publisher_id}")
            return publisher
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error archiving publisher {publisher_id}: {e}")
            raise PublisherServiceError(f"Failed to archive publisher: {str(e)}")
    
    async def suspend_publisher(
        self,
        publisher_id: uuid.UUID,
        suspended_by: uuid.UUID,
        reason: str
    ) -> Publisher:
        """
        Suspend a publisher for policy violations or payment issues.
        
        Args:
            publisher_id: Publisher UUID
            suspended_by: UUID of user performing the suspension
            reason: Reason for suspension
            
        Returns:
            Publisher: Suspended publisher
        """
        logger.info(f"Suspending publisher {publisher_id}")
        
        publisher = await self.get_publisher(publisher_id)
        
        try:
            # Update status to suspended
            publisher.status = "suspended"
            publisher.updated_at = datetime.utcnow()
            
            # Store suspension metadata
            if not publisher.additional_data:
                publisher.additional_data = {}
            
            publisher.additional_data["suspension_info"] = {
                "suspended_by": str(suspended_by),
                "suspended_at": datetime.utcnow().isoformat(),
                "reason": reason
            }
            
            await self.db.commit()
            
            # Publish suspension event
            if self.events:
                await self.events.publish_publisher_suspended(
                    publisher_id=publisher.id,
                    suspended_by=suspended_by,
                    reason=reason
                )
            
            logger.info(f"Successfully suspended publisher {publisher_id}")
            return publisher
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error suspending publisher {publisher_id}: {e}")
            raise PublisherServiceError(f"Failed to suspend publisher: {str(e)}")
    
    async def list_publishers(
        self,
        filters: Optional[Dict[str, Any]] = None,
        pagination: Optional[Dict[str, Any]] = None
    ) -> Tuple[List[Publisher], int]:
        """
        List publishers with filtering and pagination.
        
        Args:
            filters: Optional filters (status, publisher_type, business_model, etc.)
            pagination: Optional pagination (limit, offset, sort_by, sort_order)
            
        Returns:
            Tuple[List[Publisher], int]: (publishers, total_count)
        """
        try:
            query = select(Publisher).options(
                joinedload(Publisher.account)
            )
            
            # Apply filters
            if filters:
                if "status" in filters:
                    query = query.where(Publisher.status == filters["status"])
                if "publisher_type" in filters:
                    query = query.where(Publisher.publisher_type == filters["publisher_type"])
                if "business_model" in filters:
                    query = query.where(Publisher.business_model == filters["business_model"])
                if "search" in filters:
                    search_term = f"%{filters['search']}%"
                    query = query.where(
                        or_(
                            Publisher.name.ilike(search_term),
                            Publisher.subdomain.ilike(search_term),
                            Publisher.primary_contact_email.ilike(search_term)
                        )
                    )
            
            # Get total count
            count_query = select(func.count(Publisher.id))
            if filters:
                # Apply same filters to count query
                if "status" in filters:
                    count_query = count_query.where(Publisher.status == filters["status"])
                if "publisher_type" in filters:
                    count_query = count_query.where(Publisher.publisher_type == filters["publisher_type"])
                if "business_model" in filters:
                    count_query = count_query.where(Publisher.business_model == filters["business_model"])
                if "search" in filters:
                    search_term = f"%{filters['search']}%"
                    count_query = count_query.where(
                        or_(
                            Publisher.name.ilike(search_term),
                            Publisher.subdomain.ilike(search_term),
                            Publisher.primary_contact_email.ilike(search_term)
                        )
                    )
            
            total_count_result = await self.db.execute(count_query)
            total_count = total_count_result.scalar()
            
            # Apply pagination and sorting
            if pagination:
                sort_by = pagination.get("sort_by", "created_at")
                sort_order = pagination.get("sort_order", "desc")
                
                if hasattr(Publisher, sort_by):
                    order_col = getattr(Publisher, sort_by)
                    if sort_order.lower() == "desc":
                        query = query.order_by(desc(order_col))
                    else:
                        query = query.order_by(asc(order_col))
                
                if "limit" in pagination:
                    query = query.limit(pagination["limit"])
                
                if "offset" in pagination:
                    query = query.offset(pagination["offset"])
            
            result = await self.db.execute(query)
            publishers = result.scalars().all()
            
            return list(publishers), total_count
            
        except Exception as e:
            logger.error(f"Error listing publishers: {e}")
            raise PublisherServiceError(f"Failed to list publishers: {str(e)}")
    
    # Settings Management
    
    async def get_publisher_settings(
        self,
        publisher_id: uuid.UUID
    ) -> Dict[str, Any]:
        """
        Get complete publisher settings.
        
        Args:
            publisher_id: Publisher UUID
            
        Returns:
            Dict[str, Any]: Complete settings dictionary
        """
        publisher = await self.get_publisher(publisher_id)
        return publisher.settings or {}
    
    async def update_publisher_settings(
        self,
        publisher_id: uuid.UUID,
        settings_update: Dict[str, Any],
        updated_by: uuid.UUID
    ) -> Dict[str, Any]:
        """
        Update publisher settings with validation.
        
        Args:
            publisher_id: Publisher UUID
            settings_update: Settings to update
            updated_by: UUID of user making the update
            
        Returns:
            Dict[str, Any]: Updated settings
        """
        logger.info(f"Updating settings for publisher {publisher_id}")
        
        publisher = await self.get_publisher(publisher_id)
        
        try:
            # Validate settings update
            validation_result = self._validate_settings_update(settings_update, publisher)
            if not validation_result.is_valid:
                raise PublisherValidationError(
                    "Settings validation failed",
                    validation_result.errors
                )
            
            # Update settings using dot notation support
            for key, value in settings_update.items():
                publisher.update_setting(key, value)
            
            publisher.updated_at = datetime.utcnow()
            
            await self.db.commit()
            
            # Publish settings update event
            if self.events:
                await self.events.publish_publisher_settings_updated(
                    publisher_id=publisher.id,
                    updated_by=updated_by,
                    settings_changed=list(settings_update.keys())
                )
            
            logger.info(f"Successfully updated settings for publisher {publisher_id}")
            return publisher.settings
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error updating settings for publisher {publisher_id}: {e}")
            raise PublisherServiceError(f"Failed to update publisher settings: {str(e)}")
    
    async def get_branding_config(
        self,
        publisher_id: uuid.UUID
    ) -> Dict[str, Any]:
        """
        Get publisher branding configuration.
        
        Args:
            publisher_id: Publisher UUID
            
        Returns:
            Dict[str, Any]: Branding configuration
        """
        publisher = await self.get_publisher(publisher_id)
        return publisher.get_branding_config()
    
    async def update_branding_config(
        self,
        publisher_id: uuid.UUID,
        branding_update: Dict[str, Any],
        updated_by: uuid.UUID
    ) -> Dict[str, Any]:
        """
        Update publisher branding configuration.
        
        Args:
            publisher_id: Publisher UUID
            branding_update: Branding updates
            updated_by: UUID of user making the update
            
        Returns:
            Dict[str, Any]: Updated branding config
        """
        logger.info(f"Updating branding for publisher {publisher_id}")
        
        publisher = await self.get_publisher(publisher_id)
        
        try:
            # Validate branding update
            validation_result = self._validate_branding_update(branding_update)
            if not validation_result.is_valid:
                raise PublisherValidationError(
                    "Branding validation failed",
                    validation_result.errors
                )
            
            # Update branding
            current_branding = publisher.branding or {}
            updated_branding = {**current_branding, **branding_update}
            publisher.branding = updated_branding
            
            publisher.updated_at = datetime.utcnow()
            
            await self.db.commit()
            
            # Publish branding update event
            if self.events:
                await self.events.publish_publisher_branding_updated(
                    publisher_id=publisher.id,
                    updated_by=updated_by,
                    changes=list(branding_update.keys())
                )
            
            logger.info(f"Successfully updated branding for publisher {publisher_id}")
            return publisher.get_branding_config()
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error updating branding for publisher {publisher_id}: {e}")
            raise PublisherServiceError(f"Failed to update publisher branding: {str(e)}")
    
    # Business Model and Type Management
    
    async def update_business_model(
        self,
        publisher_id: uuid.UUID,
        new_business_model: str,
        updated_by: uuid.UUID,
        migration_plan: Optional[Dict[str, Any]] = None
    ) -> Publisher:
        """
        Update publisher business model with workflow validation.
        
        Args:
            publisher_id: Publisher UUID
            new_business_model: New business model (traditional, platform, hybrid)
            updated_by: UUID of user making the change
            migration_plan: Optional migration plan details
            
        Returns:
            Publisher: Updated publisher
        """
        logger.info(f"Updating business model for publisher {publisher_id} to {new_business_model}")
        
        publisher = await self.get_publisher(publisher_id)
        
        # Validate business model change
        validation_result = self._validate_business_model_change(
            publisher, new_business_model, migration_plan
        )
        if not validation_result.is_valid:
            raise PublisherValidationError(
                "Business model change validation failed",
                validation_result.errors
            )
        
        try:
            old_business_model = publisher.business_model
            publisher.business_model = new_business_model
            publisher.updated_at = datetime.utcnow()
            
            # Store migration metadata
            if not publisher.additional_data:
                publisher.additional_data = {}
            
            publisher.additional_data["business_model_changes"] = publisher.additional_data.get("business_model_changes", [])
            publisher.additional_data["business_model_changes"].append({
                "from": old_business_model,
                "to": new_business_model,
                "changed_by": str(updated_by),
                "changed_at": datetime.utcnow().isoformat(),
                "migration_plan": migration_plan
            })
            
            await self.db.commit()
            
            # Publish business model change event
            if self.events:
                await self.events.publish_business_model_changed(
                    publisher_id=publisher.id,
                    old_model=old_business_model,
                    new_model=new_business_model,
                    updated_by=updated_by
                )
            
            logger.info(f"Successfully updated business model for publisher {publisher_id}")
            return publisher
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error updating business model for publisher {publisher_id}: {e}")
            raise PublisherServiceError(f"Failed to update business model: {str(e)}")
    
    async def update_publisher_type(
        self,
        publisher_id: uuid.UUID,
        new_publisher_type: str,
        updated_by: uuid.UUID
    ) -> Publisher:
        """
        Update publisher type with feature access validation.
        
        Args:
            publisher_id: Publisher UUID
            new_publisher_type: New publisher type (enterprise, professional, platform, boutique)
            updated_by: UUID of user making the change
            
        Returns:
            Publisher: Updated publisher
        """
        logger.info(f"Updating publisher type for {publisher_id} to {new_publisher_type}")
        
        publisher = await self.get_publisher(publisher_id)
        
        # Validate publisher type change
        validation_result = self._validate_publisher_type_change(publisher, new_publisher_type)
        if not validation_result.is_valid:
            raise PublisherValidationError(
                "Publisher type change validation failed",
                validation_result.errors
            )
        
        try:
            old_publisher_type = publisher.publisher_type
            publisher.publisher_type = new_publisher_type
            publisher.updated_at = datetime.utcnow()
            
            # Store type change metadata
            if not publisher.additional_data:
                publisher.additional_data = {}
            
            publisher.additional_data["type_changes"] = publisher.additional_data.get("type_changes", [])
            publisher.additional_data["type_changes"].append({
                "from": old_publisher_type,
                "to": new_publisher_type,
                "changed_by": str(updated_by),
                "changed_at": datetime.utcnow().isoformat()
            })
            
            await self.db.commit()
            
            # Publish publisher type change event
            if self.events:
                await self.events.publish_publisher_type_changed(
                    publisher_id=publisher.id,
                    old_type=old_publisher_type,
                    new_type=new_publisher_type,
                    updated_by=updated_by
                )
            
            logger.info(f"Successfully updated publisher type for {publisher_id}")
            return publisher
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error updating publisher type for {publisher_id}: {e}")
            raise PublisherServiceError(f"Failed to update publisher type: {str(e)}")
    
    # User Management
    
    async def get_publisher_users(
        self,
        publisher_id: uuid.UUID,
        filters: Optional[Dict[str, Any]] = None,
        pagination: Optional[Dict[str, Any]] = None
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Get users associated with a publisher with roles and permissions.
        
        Args:
            publisher_id: Publisher UUID
            filters: Optional filters (status, role, etc.)
            pagination: Optional pagination parameters
            
        Returns:
            Tuple[List[Dict], int]: (user_data_list, total_count)
        """
        try:
            query = select(UserPublisher).options(
                joinedload(UserPublisher.user),
                joinedload(UserPublisher.role)
            ).where(UserPublisher.publisher_id == publisher_id)
            
            # Apply filters
            if filters:
                if "status" in filters:
                    query = query.where(UserPublisher.status == filters["status"])
                if "role_name" in filters:
                    query = query.join(Role).where(Role.name == filters["role_name"])
                if "search" in filters:
                    search_term = f"%{filters['search']}%"
                    query = query.join(User).where(
                        or_(
                            User.email.ilike(search_term),
                            User.first_name.ilike(search_term),
                            User.last_name.ilike(search_term)
                        )
                    )
            
            # Get total count
            count_query = select(func.count(UserPublisher.id)).where(
                UserPublisher.publisher_id == publisher_id
            )
            if filters:
                if "status" in filters:
                    count_query = count_query.where(UserPublisher.status == filters["status"])
                if "role_name" in filters:
                    count_query = count_query.join(Role).where(Role.name == filters["role_name"])
                if "search" in filters:
                    search_term = f"%{filters['search']}%"
                    count_query = count_query.join(User).where(
                        or_(
                            User.email.ilike(search_term),
                            User.first_name.ilike(search_term),
                            User.last_name.ilike(search_term)
                        )
                    )
            
            total_count_result = await self.db.execute(count_query)
            total_count = total_count_result.scalar()
            
            # Apply pagination and sorting
            if pagination:
                sort_by = pagination.get("sort_by", "created_at")
                sort_order = pagination.get("sort_order", "desc")
                
                if hasattr(UserPublisher, sort_by):
                    order_col = getattr(UserPublisher, sort_by)
                    if sort_order.lower() == "desc":
                        query = query.order_by(desc(order_col))
                    else:
                        query = query.order_by(asc(order_col))
                
                if "limit" in pagination:
                    query = query.limit(pagination["limit"])
                
                if "offset" in pagination:
                    query = query.offset(pagination["offset"])
            
            result = await self.db.execute(query)
            user_publishers = result.scalars().all()
            
            # Format response data
            user_data_list = []
            for up in user_publishers:
                user_data = {
                    "user_id": up.user.id,
                    "email": up.user.email,
                    "first_name": up.user.first_name,
                    "last_name": up.user.last_name,
                    "full_name": up.user.full_name,
                    "status": up.user.status,
                    "is_verified": up.user.is_verified,
                    "last_login_at": up.user.last_login_at,
                    "publisher_relationship": {
                        "id": up.id,
                        "role_name": up.role_name,
                        "status": up.status,
                        "is_primary": up.is_primary,
                        "joined_at": up.joined_at,
                        "last_accessed_at": up.last_accessed_at,
                        "access_count": up.access_count,
                        "permissions": up.permissions
                    }
                }
                user_data_list.append(user_data)
            
            return user_data_list, total_count
            
        except Exception as e:
            logger.error(f"Error getting users for publisher {publisher_id}: {e}")
            raise PublisherServiceError(f"Failed to get publisher users: {str(e)}")
    
    async def add_user_to_publisher(
        self,
        publisher_id: uuid.UUID,
        user_id: uuid.UUID,
        role_id: uuid.UUID,
        added_by: uuid.UUID,
        is_primary: bool = False,
        send_invitation: bool = True
    ) -> UserPublisher:
        """
        Add a user to a publisher with role assignment.
        
        Args:
            publisher_id: Publisher UUID
            user_id: User UUID
            role_id: Role UUID to assign
            added_by: UUID of user performing the addition
            is_primary: Whether this is the user's primary publisher
            send_invitation: Whether to send invitation email
            
        Returns:
            UserPublisher: Created user-publisher relationship
        """
        logger.info(f"Adding user {user_id} to publisher {publisher_id}")
        
        # Validate publisher and user exist
        publisher = await self.get_publisher(publisher_id, include_relationships=True)
        
        # Check if user already has relationship with this publisher
        existing_query = select(UserPublisher).where(
            and_(
                UserPublisher.user_id == user_id,
                UserPublisher.publisher_id == publisher_id
            )
        )
        existing_result = await self.db.execute(existing_query)
        existing_relationship = existing_result.scalar_one_or_none()
        
        if existing_relationship:
            raise PublisherServiceError("User already has a relationship with this publisher")
        
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
            raise PublisherServiceError("Invalid role for this publisher")
        
        # Check if role is at capacity
        can_assign, reason = role.can_assign_to_user()
        if not can_assign:
            raise PublisherServiceError(f"Cannot assign role: {reason}")
        
        # Check account seat availability
        if publisher.account and not publisher.account.can_add_seat():
            raise PublisherServiceError("Publisher has no available seats")
        
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
                # In a real implementation, you'd send the email here
                logger.info(f"Generated invitation token for user {user_id}")
            else:
                user_publisher.joined_at = datetime.utcnow()
            
            self.db.add(user_publisher)
            
            # Update role user count
            role.update_user_count(1)
            
            # Allocate account seat
            if publisher.account:
                publisher.account.allocate_seat()
            
            await self.db.commit()
            
            # Publish user addition event
            if self.events:
                await self.events.publish_user_added_to_publisher(
                    publisher_id=publisher_id,
                    user_id=user_id,
                    role_id=role_id,
                    added_by=added_by,
                    invitation_sent=send_invitation
                )
            
            logger.info(f"Successfully added user {user_id} to publisher {publisher_id}")
            return user_publisher
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error adding user to publisher: {e}")
            raise PublisherServiceError(f"Failed to add user to publisher: {str(e)}")
    
    async def remove_user_from_publisher(
        self,
        publisher_id: uuid.UUID,
        user_id: uuid.UUID,
        removed_by: uuid.UUID,
        reason: Optional[str] = None
    ) -> bool:
        """
        Remove a user from a publisher.
        
        Args:
            publisher_id: Publisher UUID
            user_id: User UUID
            removed_by: UUID of user performing the removal
            reason: Optional reason for removal
            
        Returns:
            bool: True if user was removed
        """
        logger.info(f"Removing user {user_id} from publisher {publisher_id}")
        
        # Get the relationship
        query = select(UserPublisher).options(
            joinedload(UserPublisher.role)
        ).where(
            and_(
                UserPublisher.user_id == user_id,
                UserPublisher.publisher_id == publisher_id
            )
        )
        result = await self.db.execute(query)
        user_publisher = result.scalar_one_or_none()
        
        if not user_publisher:
            raise PublisherServiceError("User-publisher relationship not found")
        
        # Check if user is owner (prevent removal of last owner)
        if user_publisher.is_owner:
            owner_count_query = select(func.count(UserPublisher.id)).join(Role).where(
                and_(
                    UserPublisher.publisher_id == publisher_id,
                    Role.name == "owner",
                    UserPublisher.status == "active"
                )
            )
            owner_count_result = await self.db.execute(owner_count_query)
            owner_count = owner_count_result.scalar()
            
            if owner_count <= 1:
                raise PublisherServiceError("Cannot remove the last owner from publisher")
        
        try:
            # Get publisher for seat management
            publisher = await self.get_publisher(publisher_id, include_relationships=True)
            
            # Update relationship status
            user_publisher.status = "revoked"
            user_publisher.updated_at = datetime.utcnow()
            
            # Store removal metadata
            if not user_publisher.metadata:
                user_publisher.metadata = {}
            
            user_publisher.metadata["removal_info"] = {
                "removed_by": str(removed_by),
                "removed_at": datetime.utcnow().isoformat(),
                "reason": reason
            }
            
            # Update role user count
            if user_publisher.role:
                user_publisher.role.update_user_count(-1)
            
            # Deallocate account seat
            if publisher.account:
                publisher.account.deallocate_seat()
            
            await self.db.commit()
            
            # Publish user removal event
            if self.events:
                await self.events.publish_user_removed_from_publisher(
                    publisher_id=publisher_id,
                    user_id=user_id,
                    removed_by=removed_by,
                    reason=reason
                )
            
            logger.info(f"Successfully removed user {user_id} from publisher {publisher_id}")
            return True
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error removing user from publisher: {e}")
            raise PublisherServiceError(f"Failed to remove user from publisher: {str(e)}")
    
    async def update_user_role(
        self,
        publisher_id: uuid.UUID,
        user_id: uuid.UUID,
        new_role_id: uuid.UUID,
        updated_by: uuid.UUID
    ) -> UserPublisher:
        """
        Update user role within a publisher.
        
        Args:
            publisher_id: Publisher UUID
            user_id: User UUID
            new_role_id: New role UUID
            updated_by: UUID of user making the change
            
        Returns:
            UserPublisher: Updated user-publisher relationship
        """
        logger.info(f"Updating role for user {user_id} in publisher {publisher_id}")
        
        # Get current relationship
        query = select(UserPublisher).options(
            joinedload(UserPublisher.role)
        ).where(
            and_(
                UserPublisher.user_id == user_id,
                UserPublisher.publisher_id == publisher_id
            )
        )
        result = await self.db.execute(query)
        user_publisher = result.scalar_one_or_none()
        
        if not user_publisher:
            raise PublisherServiceError("User-publisher relationship not found")
        
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
            raise PublisherServiceError("Invalid role for this publisher")
        
        # Check if new role is at capacity
        can_assign, reason = new_role.can_assign_to_user()
        if not can_assign:
            raise PublisherServiceError(f"Cannot assign new role: {reason}")
        
        # Check if user is last owner
        if user_publisher.is_owner and new_role.name != "owner":
            owner_count_query = select(func.count(UserPublisher.id)).join(Role).where(
                and_(
                    UserPublisher.publisher_id == publisher_id,
                    Role.name == "owner",
                    UserPublisher.status == "active"
                )
            )
            owner_count_result = await self.db.execute(owner_count_query)
            owner_count = owner_count_result.scalar()
            
            if owner_count <= 1:
                raise PublisherServiceError("Cannot change role of the last owner")
        
        try:
            old_role = user_publisher.role
            
            # Update role user counts
            if old_role:
                old_role.update_user_count(-1)
            new_role.update_user_count(1)
            
            # Update relationship
            user_publisher.update_role(new_role_id, updated_by)
            user_publisher.updated_at = datetime.utcnow()
            
            await self.db.commit()
            
            # Publish role update event
            if self.events:
                await self.events.publish_user_role_updated(
                    publisher_id=publisher_id,
                    user_id=user_id,
                    old_role_name=old_role.name if old_role else None,
                    new_role_name=new_role.name,
                    updated_by=updated_by
                )
            
            logger.info(f"Successfully updated role for user {user_id} in publisher {publisher_id}")
            return user_publisher
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error updating user role: {e}")
            raise PublisherServiceError(f"Failed to update user role: {str(e)}")
    
    # Private Helper Methods
    
    def _validate_publisher_creation(self, publisher_data: Dict[str, Any]) -> ValidationResult:
        """Validate publisher creation data."""
        errors = []
        
        # Required fields
        required_fields = ["name", "subdomain", "primary_contact_email"]
        for field in required_fields:
            if not publisher_data.get(field) or len(str(publisher_data[field]).strip()) == 0:
                errors.append(ValidationError(
                    field=field,
                    code=f"{field.upper()}_REQUIRED",
                    message=f"{field.replace('_', ' ').title()} is required"
                ))
        
        # Subdomain validation
        subdomain = publisher_data.get("subdomain", "")
        if len(subdomain) < 3:
            errors.append(ValidationError(
                field="subdomain",
                code="SUBDOMAIN_TOO_SHORT",
                message="Subdomain must be at least 3 characters"
            ))
        
        if not subdomain.replace("-", "").replace("_", "").isalnum():
            errors.append(ValidationError(
                field="subdomain",
                code="INVALID_SUBDOMAIN_FORMAT",
                message="Subdomain can only contain letters, numbers, hyphens, and underscores"
            ))
        
        # Email validation
        email = publisher_data.get("primary_contact_email", "")
        if email and "@" not in email:
            errors.append(ValidationError(
                field="primary_contact_email",
                code="INVALID_EMAIL_FORMAT",
                message="Primary contact email must be a valid email address"
            ))
        
        # Publisher type validation
        publisher_type = publisher_data.get("publisher_type", "professional")
        valid_types = ["enterprise", "professional", "platform", "boutique"]
        if publisher_type not in valid_types:
            errors.append(ValidationError(
                field="publisher_type",
                code="INVALID_PUBLISHER_TYPE",
                message=f"Publisher type must be one of: {valid_types}"
            ))
        
        # Business model validation
        business_model = publisher_data.get("business_model", "traditional")
        valid_models = ["traditional", "platform", "hybrid"]
        if business_model not in valid_models:
            errors.append(ValidationError(
                field="business_model",
                code="INVALID_BUSINESS_MODEL",
                message=f"Business model must be one of: {valid_models}"
            ))
        
        return ValidationResult(is_valid=len(errors) == 0, errors=errors)
    
    def _validate_publisher_update(self, update_data: Dict[str, Any], existing_publisher: Publisher) -> ValidationResult:
        """Validate publisher update data."""
        errors = []
        
        # Status change validation
        if "status" in update_data:
            new_status = update_data["status"]
            valid_statuses = ["active", "suspended", "archived", "trial"]
            if new_status not in valid_statuses:
                errors.append(ValidationError(
                    field="status",
                    code="INVALID_STATUS",
                    message=f"Status must be one of: {valid_statuses}"
                ))
        
        # Apply same validation as creation for updated fields
        if any(field in update_data for field in ["name", "subdomain", "primary_contact_email", "publisher_type", "business_model"]):
            # Create temporary data for validation
            temp_data = {
                "name": update_data.get("name", existing_publisher.name),
                "subdomain": update_data.get("subdomain", existing_publisher.subdomain),
                "primary_contact_email": update_data.get("primary_contact_email", existing_publisher.primary_contact_email),
                "publisher_type": update_data.get("publisher_type", existing_publisher.publisher_type),
                "business_model": update_data.get("business_model", existing_publisher.business_model)
            }
            
            creation_result = self._validate_publisher_creation(temp_data)
            errors.extend(creation_result.errors)
        
        return ValidationResult(is_valid=len(errors) == 0, errors=errors)
    
    def _validate_settings_update(self, settings_update: Dict[str, Any], publisher: Publisher) -> ValidationResult:
        """Validate settings update."""
        errors = []
        
        # Currency validation
        if "currency" in settings_update:
            currency = settings_update["currency"]
            if len(currency) != 3 or not currency.isupper():
                errors.append(ValidationError(
                    field="currency",
                    code="INVALID_CURRENCY",
                    message="Currency must be a 3-letter uppercase code"
                ))
        
        # Language validation
        if "language" in settings_update:
            language = settings_update["language"]
            if len(language) < 2:
                errors.append(ValidationError(
                    field="language",
                    code="INVALID_LANGUAGE",
                    message="Language must be at least 2 characters"
                ))
        
        return ValidationResult(is_valid=len(errors) == 0, errors=errors)
    
    def _validate_branding_update(self, branding_update: Dict[str, Any]) -> ValidationResult:
        """Validate branding configuration update."""
        errors = []
        
        # Color validation (basic hex color check)
        for color_field in ["primary_color", "secondary_color", "accent_color"]:
            if color_field in branding_update:
                color = branding_update[color_field]
                if color and not (color.startswith("#") and len(color) == 7):
                    errors.append(ValidationError(
                        field=color_field,
                        code="INVALID_COLOR_FORMAT",
                        message=f"{color_field.replace('_', ' ').title()} must be a valid hex color"
                    ))
        
        # Theme validation
        if "theme" in branding_update:
            theme = branding_update["theme"]
            valid_themes = ["light", "dark", "auto"]
            if theme not in valid_themes:
                errors.append(ValidationError(
                    field="theme",
                    code="INVALID_THEME",
                    message=f"Theme must be one of: {valid_themes}"
                ))
        
        return ValidationResult(is_valid=len(errors) == 0, errors=errors)
    
    def _validate_business_model_change(
        self,
        publisher: Publisher,
        new_business_model: str,
        migration_plan: Optional[Dict[str, Any]]
    ) -> ValidationResult:
        """Validate business model change."""
        errors = []
        
        valid_models = ["traditional", "platform", "hybrid"]
        if new_business_model not in valid_models:
            errors.append(ValidationError(
                field="business_model",
                code="INVALID_BUSINESS_MODEL",
                message=f"Business model must be one of: {valid_models}"
            ))
        
        # Check if change is actually needed
        if publisher.business_model == new_business_model:
            errors.append(ValidationError(
                field="business_model",
                code="NO_CHANGE_NEEDED",
                message="Publisher already has this business model"
            ))
        
        # Validate migration plan if provided
        if migration_plan and "implementation_date" in migration_plan:
            try:
                datetime.fromisoformat(migration_plan["implementation_date"])
            except ValueError:
                errors.append(ValidationError(
                    field="migration_plan.implementation_date",
                    code="INVALID_DATE_FORMAT",
                    message="Implementation date must be in ISO format"
                ))
        
        return ValidationResult(is_valid=len(errors) == 0, errors=errors)
    
    def _validate_publisher_type_change(self, publisher: Publisher, new_publisher_type: str) -> ValidationResult:
        """Validate publisher type change."""
        errors = []
        
        valid_types = ["enterprise", "professional", "platform", "boutique"]
        if new_publisher_type not in valid_types:
            errors.append(ValidationError(
                field="publisher_type",
                code="INVALID_PUBLISHER_TYPE",
                message=f"Publisher type must be one of: {valid_types}"
            ))
        
        # Check if change is actually needed
        if publisher.publisher_type == new_publisher_type:
            errors.append(ValidationError(
                field="publisher_type",
                code="NO_CHANGE_NEEDED",
                message="Publisher already has this type"
            ))
        
        return ValidationResult(is_valid=len(errors) == 0, errors=errors)
    
    async def _is_subdomain_taken(self, subdomain: str) -> bool:
        """Check if a subdomain is already taken."""
        query = select(Publisher.id).where(Publisher.subdomain == subdomain.lower())
        result = await self.db.execute(query)
        return result.scalar_one_or_none() is not None
    
    async def _create_default_roles(self, publisher_id: uuid.UUID) -> None:
        """Create default roles for a new publisher."""
        default_roles = [
            {
                "name": "owner",
                "display_name": "Owner",
                "description": "Full ownership and administrative access",
                "category": "admin",
                "is_default": False,
                "max_users": 2
            },
            {
                "name": "admin",
                "display_name": "Administrator", 
                "description": "Administrative access with some restrictions",
                "category": "admin",
                "is_default": False,
                "max_users": 5
            },
            {
                "name": "editor",
                "display_name": "Editor",
                "description": "Content creation and editing access",
                "category": "content",
                "is_default": True,
                "max_users": None
            },
            {
                "name": "viewer",
                "display_name": "Viewer",
                "description": "Read-only access to catalog and reports",
                "category": "general",
                "is_default": False,
                "max_users": None
            }
        ]
        
        for role_data in default_roles:
            role = Role(
                publisher_id=publisher_id,
                role_type="publisher",
                **role_data
            )
            self.db.add(role)
    
    async def _add_creator_as_owner(self, publisher_id: uuid.UUID, user_id: uuid.UUID) -> None:
        """Add the creator as the publisher owner."""
        # Get the owner role
        owner_role_query = select(Role).where(
            and_(
                Role.publisher_id == publisher_id,
                Role.name == "owner"
            )
        )
        owner_role_result = await self.db.execute(owner_role_query)
        owner_role = owner_role_result.scalar_one()
        
        # Create user-publisher relationship
        user_publisher = UserPublisher(
            user_id=user_id,
            publisher_id=publisher_id,
            role_id=owner_role.id,
            status="active",
            is_primary=True,
            joined_at=datetime.utcnow()
        )
        
        self.db.add(user_publisher)
        
        # Update role user count
        owner_role.update_user_count(1)