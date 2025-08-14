"""Account service layer for comprehensive billing and subscription management.

This service provides complete business logic for account operations, subscription management,
billing operations, usage tracking, and financial management. It follows established service
patterns and integrates with Account and Publisher models.
"""

import logging
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, List, Dict, Any, Tuple, Union

from sqlalchemy import and_, or_, func, desc, asc, text
from sqlalchemy.orm import AsyncSession, selectinload, joinedload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError, NoResultFound

from src.models.account import Account
from src.models.publisher import Publisher
from src.services.business_rules import ValidationResult, ValidationError, TenantContext
from src.services.events import EventPublisher

logger = logging.getLogger(__name__)


class AccountServiceError(Exception):
    """Base exception for account service errors."""
    pass


class AccountNotFoundError(AccountServiceError):
    """Raised when an account cannot be found."""
    pass


class AccountValidationError(AccountServiceError):
    """Raised when account data validation fails."""
    
    def __init__(self, message: str, validation_errors: List[ValidationError] = None):
        super().__init__(message)
        self.validation_errors = validation_errors or []


class AccountPermissionError(AccountServiceError):
    """Raised when user lacks permission for account operation."""
    pass


class PaymentError(AccountServiceError):
    """Raised when payment operations fail."""
    pass


class UsageLimitError(AccountServiceError):
    """Raised when usage limits are exceeded."""
    pass


class SubscriptionError(AccountServiceError):
    """Raised when subscription operations fail."""
    pass


class AccountService:
    """
    Comprehensive Account service for billing and subscription management.
    
    This service provides complete business logic for:
    - Subscription plan management (create, upgrade, downgrade, cancel)
    - Billing operations (payment methods, invoicing, collections)
    - Usage tracking and limit enforcement
    - Account lifecycle management
    - Financial reporting and analytics
    - Seat-based licensing management
    - Trial period management
    - Multi-tenant billing isolation
    """
    
    def __init__(self, db_session: AsyncSession, event_publisher: EventPublisher = None):
        """
        Initialize the AccountService.
        
        Args:
            db_session: Async database session
            event_publisher: Optional event publisher for async operations
        """
        self.db = db_session
        self.events = event_publisher
        
    # Core Account Management Operations
    
    async def create_account(
        self,
        publisher_id: uuid.UUID,
        account_data: Dict[str, Any],
        created_by: Optional[uuid.UUID] = None,
        start_trial: bool = True,
        trial_days: int = 14
    ) -> Account:
        """
        Create a new account for a publisher with default plan setup.
        
        Args:
            publisher_id: Publisher UUID
            account_data: Account configuration data
            created_by: UUID of user creating the account
            start_trial: Whether to start with trial period
            trial_days: Number of trial days to grant
            
        Returns:
            Account: Created account
            
        Raises:
            AccountValidationError: If validation fails
            AccountServiceError: If creation fails
        """
        logger.info(f"Creating new account for publisher {publisher_id}")
        
        # Validate account creation data
        validation_result = self._validate_account_creation(account_data)
        if not validation_result.is_valid:
            raise AccountValidationError(
                "Account validation failed",
                validation_result.errors
            )
        
        # Check if account already exists for publisher
        existing_account = await self.get_account_by_publisher_id(publisher_id, raise_if_not_found=False)
        if existing_account:
            raise AccountServiceError(f"Account already exists for publisher {publisher_id}")
        
        try:
            # Set up default account configuration
            default_config = {
                "publisher_id": publisher_id,
                "plan_type": "starter",
                "billing_cycle": "monthly",
                "status": "trial" if start_trial else "active",
                "seats_licensed": 5,
                "monthly_price": Decimal("0.00"),
                "currency": "USD",
                "api_call_limit": 10000,
                "storage_limit_mb": 1024
            }
            
            # Merge with provided data (allowing overrides)
            final_data = {**default_config, **account_data}
            
            # Create account
            account = Account(**final_data)
            
            # Start trial if requested
            if start_trial:
                account.start_trial(days=trial_days)
            
            # Initialize plan-specific settings
            self._apply_plan_defaults(account)
            
            self.db.add(account)
            await self.db.commit()
            
            # Publish account creation event
            if self.events:
                await self.events.publish_account_created(
                    account_id=account.id,
                    publisher_id=publisher_id,
                    created_by=created_by,
                    plan_type=account.plan_type
                )
            
            logger.info(f"Successfully created account {account.id} for publisher {publisher_id}")
            return account
            
        except IntegrityError as e:
            await self.db.rollback()
            logger.error(f"Database integrity error creating account: {e}")
            raise AccountServiceError("Failed to create account due to data constraint violation")
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error creating account: {e}")
            raise AccountServiceError(f"Failed to create account: {str(e)}")
    
    async def get_account(
        self,
        account_id: uuid.UUID,
        include_relationships: bool = False
    ) -> Account:
        """
        Get account by ID with optional relationship loading.
        
        Args:
            account_id: Account UUID
            include_relationships: Whether to load related entities
            
        Returns:
            Account: Found account
            
        Raises:
            AccountNotFoundError: If account not found
        """
        try:
            query = select(Account).where(Account.id == account_id)
            
            if include_relationships:
                query = query.options(
                    joinedload(Account.publisher)
                )
            
            result = await self.db.execute(query)
            account = result.scalar_one()
            
            return account
            
        except NoResultFound:
            logger.warning(f"Account {account_id} not found")
            raise AccountNotFoundError(f"Account {account_id} not found")
        except Exception as e:
            logger.error(f"Error retrieving account {account_id}: {e}")
            raise AccountServiceError(f"Failed to retrieve account: {str(e)}")
    
    async def get_account_by_publisher_id(
        self,
        publisher_id: uuid.UUID,
        raise_if_not_found: bool = True
    ) -> Optional[Account]:
        """
        Get account by publisher ID.
        
        Args:
            publisher_id: Publisher UUID
            raise_if_not_found: Whether to raise exception if not found
            
        Returns:
            Optional[Account]: Found account or None
            
        Raises:
            AccountNotFoundError: If account not found and raise_if_not_found is True
        """
        try:
            query = select(Account).where(Account.publisher_id == publisher_id)
            result = await self.db.execute(query)
            account = result.scalar_one_or_none()
            
            if not account and raise_if_not_found:
                raise AccountNotFoundError(f"No account found for publisher {publisher_id}")
            
            return account
            
        except Exception as e:
            logger.error(f"Error retrieving account for publisher {publisher_id}: {e}")
            raise AccountServiceError(f"Failed to retrieve account: {str(e)}")
    
    # Subscription Management
    
    async def upgrade_subscription(
        self,
        account_id: uuid.UUID,
        new_plan_type: str,
        new_billing_cycle: Optional[str] = None,
        new_seats: Optional[int] = None,
        updated_by: uuid.UUID = None,
        prorate: bool = True
    ) -> Account:
        """
        Upgrade account to higher tier subscription plan.
        
        Args:
            account_id: Account UUID
            new_plan_type: New subscription plan type
            new_billing_cycle: New billing cycle (optional)
            new_seats: New number of seats (optional)
            updated_by: UUID of user performing upgrade
            prorate: Whether to prorate charges
            
        Returns:
            Account: Updated account
            
        Raises:
            AccountValidationError: If upgrade validation fails
            SubscriptionError: If upgrade fails
        """
        logger.info(f"Upgrading account {account_id} to {new_plan_type}")
        
        account = await self.get_account(account_id, include_relationships=True)
        
        # Validate upgrade eligibility
        validation_result = self._validate_subscription_upgrade(account, new_plan_type, new_seats)
        if not validation_result.is_valid:
            raise AccountValidationError(
                "Subscription upgrade validation failed",
                validation_result.errors
            )
        
        try:
            old_plan = account.plan_type
            old_seats = account.seats_licensed
            old_price = account.monthly_price
            
            # Calculate prorated charges if applicable
            proration_credit = Decimal("0.00")
            if prorate and account.current_period_start and account.current_period_end:
                proration_credit = self._calculate_proration(account, new_plan_type, new_seats)
            
            # Apply plan upgrade
            account.upgrade_plan(new_plan_type, new_seats)
            
            # Update billing cycle if provided
            if new_billing_cycle:
                account.billing_cycle = new_billing_cycle
            
            # Apply new plan pricing and limits
            self._apply_plan_pricing(account)
            self._apply_plan_limits(account)
            
            # Store upgrade metadata
            if not account.metadata:
                account.metadata = {}
            
            account.metadata["upgrade_history"] = account.metadata.get("upgrade_history", [])
            account.metadata["upgrade_history"].append({
                "from_plan": old_plan,
                "to_plan": new_plan_type,
                "from_seats": old_seats,
                "to_seats": account.seats_licensed,
                "upgraded_by": str(updated_by) if updated_by else None,
                "upgraded_at": datetime.utcnow().isoformat(),
                "proration_credit": float(proration_credit)
            })
            
            await self.db.commit()
            
            # Publish subscription upgrade event
            if self.events:
                await self.events.publish_subscription_upgraded(
                    account_id=account.id,
                    publisher_id=account.publisher_id,
                    old_plan=old_plan,
                    new_plan=new_plan_type,
                    updated_by=updated_by
                )
            
            logger.info(f"Successfully upgraded account {account_id} from {old_plan} to {new_plan_type}")
            return account
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error upgrading subscription for account {account_id}: {e}")
            raise SubscriptionError(f"Failed to upgrade subscription: {str(e)}")
    
    async def downgrade_subscription(
        self,
        account_id: uuid.UUID,
        new_plan_type: str,
        new_seats: Optional[int] = None,
        updated_by: uuid.UUID = None,
        immediate: bool = False
    ) -> Account:
        """
        Downgrade account to lower tier subscription plan.
        
        Args:
            account_id: Account UUID
            new_plan_type: New subscription plan type
            new_seats: New number of seats (optional)
            updated_by: UUID of user performing downgrade
            immediate: Whether to apply downgrade immediately or at period end
            
        Returns:
            Account: Updated account
            
        Raises:
            AccountValidationError: If downgrade validation fails
            SubscriptionError: If downgrade fails
        """
        logger.info(f"Downgrading account {account_id} to {new_plan_type}")
        
        account = await self.get_account(account_id, include_relationships=True)
        
        # Validate downgrade eligibility
        validation_result = self._validate_subscription_downgrade(account, new_plan_type, new_seats)
        if not validation_result.is_valid:
            raise AccountValidationError(
                "Subscription downgrade validation failed",
                validation_result.errors
            )
        
        try:
            old_plan = account.plan_type
            old_seats = account.seats_licensed
            
            if immediate:
                # Apply downgrade immediately
                account.plan_type = new_plan_type
                if new_seats:
                    account.seats_licensed = new_seats
                
                # Apply new plan pricing and limits
                self._apply_plan_pricing(account)
                self._apply_plan_limits(account)
            else:
                # Schedule downgrade for end of current period
                if not account.metadata:
                    account.metadata = {}
                
                account.metadata["scheduled_downgrade"] = {
                    "to_plan": new_plan_type,
                    "to_seats": new_seats,
                    "scheduled_by": str(updated_by) if updated_by else None,
                    "scheduled_at": datetime.utcnow().isoformat(),
                    "effective_date": account.current_period_end.isoformat() if account.current_period_end else None
                }
            
            # Store downgrade metadata
            if not account.metadata:
                account.metadata = {}
            
            account.metadata["downgrade_history"] = account.metadata.get("downgrade_history", [])
            account.metadata["downgrade_history"].append({
                "from_plan": old_plan,
                "to_plan": new_plan_type,
                "from_seats": old_seats,
                "to_seats": new_seats or account.seats_licensed,
                "downgraded_by": str(updated_by) if updated_by else None,
                "downgraded_at": datetime.utcnow().isoformat(),
                "immediate": immediate
            })
            
            await self.db.commit()
            
            # Publish subscription downgrade event
            if self.events:
                await self.events.publish_subscription_downgraded(
                    account_id=account.id,
                    publisher_id=account.publisher_id,
                    old_plan=old_plan,
                    new_plan=new_plan_type,
                    updated_by=updated_by,
                    immediate=immediate
                )
            
            logger.info(f"Successfully downgraded account {account_id} from {old_plan} to {new_plan_type}")
            return account
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error downgrading subscription for account {account_id}: {e}")
            raise SubscriptionError(f"Failed to downgrade subscription: {str(e)}")
    
    async def change_billing_cycle(
        self,
        account_id: uuid.UUID,
        new_billing_cycle: str,
        updated_by: uuid.UUID = None
    ) -> Account:
        """
        Change account billing cycle (monthly/annual).
        
        Args:
            account_id: Account UUID
            new_billing_cycle: New billing cycle
            updated_by: UUID of user making change
            
        Returns:
            Account: Updated account
        """
        logger.info(f"Changing billing cycle for account {account_id} to {new_billing_cycle}")
        
        account = await self.get_account(account_id)
        
        # Validate billing cycle change
        validation_result = self._validate_billing_cycle_change(account, new_billing_cycle)
        if not validation_result.is_valid:
            raise AccountValidationError(
                "Billing cycle change validation failed",
                validation_result.errors
            )
        
        try:
            old_cycle = account.billing_cycle
            account.billing_cycle = new_billing_cycle
            
            # Update pricing based on new cycle
            self._apply_plan_pricing(account)
            
            # Update next billing date based on new cycle
            if account.current_period_start:
                if new_billing_cycle == "monthly":
                    account.next_billing_date = account.current_period_start + timedelta(days=30)
                elif new_billing_cycle == "annual":
                    account.next_billing_date = account.current_period_start + timedelta(days=365)
                
                account.current_period_end = account.next_billing_date
            
            await self.db.commit()
            
            # Publish billing cycle change event
            if self.events:
                await self.events.publish_billing_cycle_changed(
                    account_id=account.id,
                    publisher_id=account.publisher_id,
                    old_cycle=old_cycle,
                    new_cycle=new_billing_cycle,
                    updated_by=updated_by
                )
            
            logger.info(f"Successfully changed billing cycle for account {account_id}")
            return account
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error changing billing cycle for account {account_id}: {e}")
            raise SubscriptionError(f"Failed to change billing cycle: {str(e)}")
    
    # Trial Management
    
    async def extend_trial(
        self,
        account_id: uuid.UUID,
        additional_days: int,
        extended_by: uuid.UUID = None,
        reason: Optional[str] = None
    ) -> Account:
        """
        Extend trial period for account.
        
        Args:
            account_id: Account UUID
            additional_days: Number of additional days to add
            extended_by: UUID of user extending trial
            reason: Reason for extension
            
        Returns:
            Account: Updated account
        """
        logger.info(f"Extending trial for account {account_id} by {additional_days} days")
        
        account = await self.get_account(account_id)
        
        if not account.is_trial:
            raise AccountValidationError("Account is not in trial status")
        
        try:
            old_end_date = account.trial_ends_at
            account.extend_trial(additional_days)
            
            # Store extension metadata
            if not account.metadata:
                account.metadata = {}
            
            account.metadata["trial_extensions"] = account.metadata.get("trial_extensions", [])
            account.metadata["trial_extensions"].append({
                "extended_by": str(extended_by) if extended_by else None,
                "extended_at": datetime.utcnow().isoformat(),
                "additional_days": additional_days,
                "old_end_date": old_end_date.isoformat() if old_end_date else None,
                "new_end_date": account.trial_ends_at.isoformat() if account.trial_ends_at else None,
                "reason": reason
            })
            
            await self.db.commit()
            
            # Publish trial extension event
            if self.events:
                await self.events.publish_trial_extended(
                    account_id=account.id,
                    publisher_id=account.publisher_id,
                    additional_days=additional_days,
                    extended_by=extended_by
                )
            
            logger.info(f"Successfully extended trial for account {account_id}")
            return account
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error extending trial for account {account_id}: {e}")
            raise AccountServiceError(f"Failed to extend trial: {str(e)}")
    
    async def convert_trial_to_paid(
        self,
        account_id: uuid.UUID,
        plan_type: str,
        billing_cycle: str = "monthly",
        seats: Optional[int] = None,
        converted_by: uuid.UUID = None
    ) -> Account:
        """
        Convert trial account to paid subscription.
        
        Args:
            account_id: Account UUID
            plan_type: Subscription plan type
            billing_cycle: Billing cycle
            seats: Number of seats (optional)
            converted_by: UUID of user converting trial
            
        Returns:
            Account: Updated account
        """
        logger.info(f"Converting trial account {account_id} to paid {plan_type} subscription")
        
        account = await self.get_account(account_id)
        
        if not account.is_trial:
            raise AccountValidationError("Account is not in trial status")
        
        # Validate plan configuration
        validation_result = self._validate_plan_configuration(plan_type, billing_cycle, seats)
        if not validation_result.is_valid:
            raise AccountValidationError(
                "Plan configuration validation failed",
                validation_result.errors
            )
        
        try:
            # Activate subscription
            account.activate_subscription(plan_type, billing_cycle)
            
            if seats:
                account.seats_licensed = seats
            
            # Apply plan pricing and limits
            self._apply_plan_pricing(account)
            self._apply_plan_limits(account)
            
            # Store conversion metadata
            if not account.metadata:
                account.metadata = {}
            
            account.metadata["trial_conversion"] = {
                "converted_by": str(converted_by) if converted_by else None,
                "converted_at": datetime.utcnow().isoformat(),
                "trial_duration_days": (datetime.utcnow() - account.trial_starts_at).days if account.trial_starts_at else None,
                "converted_to_plan": plan_type,
                "billing_cycle": billing_cycle
            }
            
            await self.db.commit()
            
            # Publish trial conversion event
            if self.events:
                await self.events.publish_trial_converted(
                    account_id=account.id,
                    publisher_id=account.publisher_id,
                    plan_type=plan_type,
                    converted_by=converted_by
                )
            
            logger.info(f"Successfully converted trial account {account_id} to paid subscription")
            return account
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error converting trial for account {account_id}: {e}")
            raise SubscriptionError(f"Failed to convert trial: {str(e)}")
    
    # Billing Operations
    
    async def update_payment_method(
        self,
        account_id: uuid.UUID,
        payment_method_data: Dict[str, Any],
        updated_by: uuid.UUID = None
    ) -> Account:
        """
        Update payment method for account.
        
        Args:
            account_id: Account UUID
            payment_method_data: Payment method information
            updated_by: UUID of user updating payment method
            
        Returns:
            Account: Updated account
        """
        logger.info(f"Updating payment method for account {account_id}")
        
        account = await self.get_account(account_id)
        
        # Validate payment method data
        validation_result = self._validate_payment_method(payment_method_data)
        if not validation_result.is_valid:
            raise AccountValidationError(
                "Payment method validation failed",
                validation_result.errors
            )
        
        try:
            # Store old payment method for audit
            old_payment_method = account.payment_method.copy() if account.payment_method else {}
            
            # Update payment method (in real implementation, this would interact with payment gateway)
            account.payment_method.update(payment_method_data)
            
            # Store update metadata
            if not account.metadata:
                account.metadata = {}
            
            account.metadata["payment_method_updates"] = account.metadata.get("payment_method_updates", [])
            account.metadata["payment_method_updates"].append({
                "updated_by": str(updated_by) if updated_by else None,
                "updated_at": datetime.utcnow().isoformat(),
                "old_method_type": old_payment_method.get("type"),
                "new_method_type": payment_method_data.get("type")
            })
            
            await self.db.commit()
            
            # Publish payment method update event
            if self.events:
                await self.events.publish_payment_method_updated(
                    account_id=account.id,
                    publisher_id=account.publisher_id,
                    updated_by=updated_by
                )
            
            logger.info(f"Successfully updated payment method for account {account_id}")
            return account
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error updating payment method for account {account_id}: {e}")
            raise PaymentError(f"Failed to update payment method: {str(e)}")
    
    async def update_billing_address(
        self,
        account_id: uuid.UUID,
        billing_address_data: Dict[str, Any],
        updated_by: uuid.UUID = None
    ) -> Account:
        """
        Update billing address for account.
        
        Args:
            account_id: Account UUID
            billing_address_data: Billing address information
            updated_by: UUID of user updating address
            
        Returns:
            Account: Updated account
        """
        logger.info(f"Updating billing address for account {account_id}")
        
        account = await self.get_account(account_id)
        
        # Validate billing address data
        validation_result = self._validate_billing_address(billing_address_data)
        if not validation_result.is_valid:
            raise AccountValidationError(
                "Billing address validation failed",
                validation_result.errors
            )
        
        try:
            # Update billing address
            if not account.billing_address:
                account.billing_address = {}
            
            account.billing_address.update(billing_address_data)
            
            await self.db.commit()
            
            # Publish billing address update event
            if self.events:
                await self.events.publish_billing_address_updated(
                    account_id=account.id,
                    publisher_id=account.publisher_id,
                    updated_by=updated_by
                )
            
            logger.info(f"Successfully updated billing address for account {account_id}")
            return account
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error updating billing address for account {account_id}: {e}")
            raise AccountServiceError(f"Failed to update billing address: {str(e)}")
    
    async def process_payment(
        self,
        account_id: uuid.UUID,
        amount: Decimal,
        payment_method_id: Optional[str] = None,
        invoice_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Process payment for account (structure for future payment gateway integration).
        
        Args:
            account_id: Account UUID
            amount: Payment amount
            payment_method_id: Payment method identifier
            invoice_id: Associated invoice ID
            
        Returns:
            Dict: Payment processing result
        """
        logger.info(f"Processing payment of {amount} for account {account_id}")
        
        account = await self.get_account(account_id)
        
        try:
            # In real implementation, this would integrate with payment gateway
            # For now, we'll simulate successful payment processing
            
            payment_result = {
                "success": True,
                "transaction_id": f"txn_{uuid.uuid4().hex[:12]}",
                "amount": float(amount),
                "currency": account.currency,
                "processed_at": datetime.utcnow().isoformat(),
                "payment_method": account.payment_method.get("type") if account.payment_method else None
            }
            
            # Record successful payment
            account.record_payment(amount)
            
            # Store payment metadata
            if not account.metadata:
                account.metadata = {}
            
            account.metadata["payment_history"] = account.metadata.get("payment_history", [])
            account.metadata["payment_history"].append(payment_result)
            
            await self.db.commit()
            
            # Publish payment processed event
            if self.events:
                await self.events.publish_payment_processed(
                    account_id=account.id,
                    publisher_id=account.publisher_id,
                    amount=amount,
                    transaction_id=payment_result["transaction_id"]
                )
            
            logger.info(f"Successfully processed payment for account {account_id}")
            return payment_result
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error processing payment for account {account_id}: {e}")
            raise PaymentError(f"Failed to process payment: {str(e)}")
    
    # Usage Tracking
    
    async def track_api_usage(
        self,
        account_id: uuid.UUID,
        api_calls: int = 1,
        endpoint: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Track API usage for account and enforce limits.
        
        Args:
            account_id: Account UUID
            api_calls: Number of API calls to add
            endpoint: API endpoint that was called
            
        Returns:
            Dict: Usage tracking result with limit status
            
        Raises:
            UsageLimitError: If usage limit is exceeded
        """
        account = await self.get_account(account_id)
        
        try:
            # Increment usage
            within_limit = account.increment_api_usage(api_calls)
            
            # Store usage metadata
            if not account.metadata:
                account.metadata = {}
            
            if "usage_tracking" not in account.metadata:
                account.metadata["usage_tracking"] = {
                    "api_calls_by_endpoint": {},
                    "last_usage_reset": None
                }
            
            # Track by endpoint if provided
            if endpoint:
                endpoint_usage = account.metadata["usage_tracking"]["api_calls_by_endpoint"]
                endpoint_usage[endpoint] = endpoint_usage.get(endpoint, 0) + api_calls
            
            await self.db.commit()
            
            usage_result = {
                "account_id": str(account.id),
                "calls_added": api_calls,
                "total_monthly_calls": account.monthly_api_calls,
                "call_limit": account.api_call_limit,
                "within_limit": within_limit,
                "usage_percentage": account.api_usage_percentage,
                "endpoint": endpoint
            }
            
            # Raise error if over limit
            if not within_limit:
                logger.warning(f"API usage limit exceeded for account {account_id}")
                raise UsageLimitError(f"API call limit exceeded. Used: {account.monthly_api_calls}, Limit: {account.api_call_limit}")
            
            return usage_result
            
        except Exception as e:
            await self.db.rollback()
            if isinstance(e, UsageLimitError):
                raise
            logger.error(f"Error tracking API usage for account {account_id}: {e}")
            raise AccountServiceError(f"Failed to track API usage: {str(e)}")
    
    async def track_storage_usage(
        self,
        account_id: uuid.UUID,
        storage_mb: int,
        operation: str = "add"
    ) -> Dict[str, Any]:
        """
        Track storage usage for account.
        
        Args:
            account_id: Account UUID
            storage_mb: Storage amount in MB
            operation: Operation type (add, remove, set)
            
        Returns:
            Dict: Storage usage result
            
        Raises:
            UsageLimitError: If storage limit is exceeded
        """
        account = await self.get_account(account_id)
        
        try:
            old_usage = account.storage_used_mb
            
            # Apply storage change
            if operation == "add":
                account.storage_used_mb += storage_mb
            elif operation == "remove":
                account.storage_used_mb = max(0, account.storage_used_mb - storage_mb)
            elif operation == "set":
                account.storage_used_mb = storage_mb
            
            # Check storage limit
            if account.storage_limit_mb and account.storage_used_mb > account.storage_limit_mb:
                # Revert change
                account.storage_used_mb = old_usage
                raise UsageLimitError(f"Storage limit exceeded. Current: {account.storage_used_mb}MB, Limit: {account.storage_limit_mb}MB")
            
            await self.db.commit()
            
            usage_result = {
                "account_id": str(account.id),
                "operation": operation,
                "storage_change_mb": storage_mb,
                "total_storage_mb": account.storage_used_mb,
                "storage_limit_mb": account.storage_limit_mb,
                "usage_percentage": account.storage_usage_percentage
            }
            
            return usage_result
            
        except Exception as e:
            await self.db.rollback()
            if isinstance(e, UsageLimitError):
                raise
            logger.error(f"Error tracking storage usage for account {account_id}: {e}")
            raise AccountServiceError(f"Failed to track storage usage: {str(e)}")
    
    async def reset_monthly_usage(self, account_id: uuid.UUID) -> Account:
        """
        Reset monthly usage counters for account.
        
        Args:
            account_id: Account UUID
            
        Returns:
            Account: Updated account
        """
        logger.info(f"Resetting monthly usage for account {account_id}")
        
        account = await self.get_account(account_id)
        
        try:
            # Store usage before reset for reporting
            if not account.metadata:
                account.metadata = {}
            
            account.metadata["usage_history"] = account.metadata.get("usage_history", [])
            account.metadata["usage_history"].append({
                "period_end": datetime.utcnow().isoformat(),
                "api_calls": account.monthly_api_calls,
                "reset_type": "monthly_cycle"
            })
            
            # Reset counters
            account.reset_monthly_usage()
            
            # Update last reset timestamp
            if "usage_tracking" not in account.metadata:
                account.metadata["usage_tracking"] = {}
            account.metadata["usage_tracking"]["last_usage_reset"] = datetime.utcnow().isoformat()
            
            await self.db.commit()
            
            logger.info(f"Successfully reset monthly usage for account {account_id}")
            return account
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error resetting monthly usage for account {account_id}: {e}")
            raise AccountServiceError(f"Failed to reset monthly usage: {str(e)}")
    
    # Account Lifecycle
    
    async def suspend_account(
        self,
        account_id: uuid.UUID,
        reason: str,
        suspended_by: uuid.UUID = None
    ) -> Account:
        """
        Suspend account for payment issues or violations.
        
        Args:
            account_id: Account UUID
            reason: Reason for suspension
            suspended_by: UUID of user performing suspension
            
        Returns:
            Account: Suspended account
        """
        logger.info(f"Suspending account {account_id}")
        
        account = await self.get_account(account_id)
        
        try:
            account.suspend_account(reason)
            
            # Store suspension metadata
            if not account.metadata:
                account.metadata = {}
            
            account.metadata["suspension_history"] = account.metadata.get("suspension_history", [])
            account.metadata["suspension_history"].append({
                "suspended_by": str(suspended_by) if suspended_by else None,
                "suspended_at": datetime.utcnow().isoformat(),
                "reason": reason,
                "previous_status": account.status
            })
            
            await self.db.commit()
            
            # Publish account suspension event
            if self.events:
                await self.events.publish_account_suspended(
                    account_id=account.id,
                    publisher_id=account.publisher_id,
                    reason=reason,
                    suspended_by=suspended_by
                )
            
            logger.info(f"Successfully suspended account {account_id}")
            return account
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error suspending account {account_id}: {e}")
            raise AccountServiceError(f"Failed to suspend account: {str(e)}")
    
    async def reactivate_account(
        self,
        account_id: uuid.UUID,
        reactivated_by: uuid.UUID = None
    ) -> Account:
        """
        Reactivate suspended account.
        
        Args:
            account_id: Account UUID
            reactivated_by: UUID of user performing reactivation
            
        Returns:
            Account: Reactivated account
        """
        logger.info(f"Reactivating account {account_id}")
        
        account = await self.get_account(account_id)
        
        if not account.is_suspended:
            raise AccountValidationError("Account is not in suspended status")
        
        try:
            old_status = account.status
            account.reactivate_account()
            
            # Store reactivation metadata
            if not account.metadata:
                account.metadata = {}
            
            account.metadata["reactivation_history"] = account.metadata.get("reactivation_history", [])
            account.metadata["reactivation_history"].append({
                "reactivated_by": str(reactivated_by) if reactivated_by else None,
                "reactivated_at": datetime.utcnow().isoformat(),
                "previous_status": old_status
            })
            
            await self.db.commit()
            
            # Publish account reactivation event
            if self.events:
                await self.events.publish_account_reactivated(
                    account_id=account.id,
                    publisher_id=account.publisher_id,
                    reactivated_by=reactivated_by
                )
            
            logger.info(f"Successfully reactivated account {account_id}")
            return account
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error reactivating account {account_id}: {e}")
            raise AccountServiceError(f"Failed to reactivate account: {str(e)}")
    
    async def cancel_account(
        self,
        account_id: uuid.UUID,
        cancelled_by: uuid.UUID = None,
        immediate: bool = False,
        reason: Optional[str] = None
    ) -> Account:
        """
        Cancel account subscription.
        
        Args:
            account_id: Account UUID
            cancelled_by: UUID of user performing cancellation
            immediate: Whether to cancel immediately
            reason: Reason for cancellation
            
        Returns:
            Account: Cancelled account
        """
        logger.info(f"Cancelling account {account_id}")
        
        account = await self.get_account(account_id)
        
        try:
            old_status = account.status
            account.cancel_subscription(immediate)
            
            # Store cancellation metadata
            if not account.metadata:
                account.metadata = {}
            
            account.metadata["cancellation_info"] = {
                "cancelled_by": str(cancelled_by) if cancelled_by else None,
                "cancelled_at": datetime.utcnow().isoformat(),
                "reason": reason,
                "immediate": immediate,
                "previous_status": old_status,
                "effective_date": datetime.utcnow().isoformat() if immediate else (
                    account.current_period_end.isoformat() if account.current_period_end else None
                )
            }
            
            await self.db.commit()
            
            # Publish account cancellation event
            if self.events:
                await self.events.publish_account_cancelled(
                    account_id=account.id,
                    publisher_id=account.publisher_id,
                    cancelled_by=cancelled_by,
                    immediate=immediate,
                    reason=reason
                )
            
            logger.info(f"Successfully cancelled account {account_id}")
            return account
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error cancelling account {account_id}: {e}")
            raise AccountServiceError(f"Failed to cancel account: {str(e)}")
    
    # Seat Management
    
    async def allocate_seat(
        self,
        account_id: uuid.UUID,
        user_id: uuid.UUID,
        allocated_by: uuid.UUID = None
    ) -> bool:
        """
        Allocate a user seat for account.
        
        Args:
            account_id: Account UUID
            user_id: User UUID to allocate seat for
            allocated_by: UUID of user allocating seat
            
        Returns:
            bool: True if seat was allocated
            
        Raises:
            UsageLimitError: If no seats available
        """
        account = await self.get_account(account_id)
        
        if not account.can_add_seat():
            raise UsageLimitError(f"No available seats. Used: {account.seats_used}, Licensed: {account.seats_licensed}")
        
        try:
            success = account.allocate_seat()
            
            if success:
                # Store seat allocation metadata
                if not account.metadata:
                    account.metadata = {}
                
                account.metadata["seat_allocations"] = account.metadata.get("seat_allocations", [])
                account.metadata["seat_allocations"].append({
                    "user_id": str(user_id),
                    "allocated_by": str(allocated_by) if allocated_by else None,
                    "allocated_at": datetime.utcnow().isoformat()
                })
                
                await self.db.commit()
                
                logger.info(f"Successfully allocated seat for user {user_id} on account {account_id}")
            
            return success
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error allocating seat for account {account_id}: {e}")
            raise AccountServiceError(f"Failed to allocate seat: {str(e)}")
    
    async def deallocate_seat(
        self,
        account_id: uuid.UUID,
        user_id: uuid.UUID,
        deallocated_by: uuid.UUID = None
    ) -> None:
        """
        Deallocate a user seat from account.
        
        Args:
            account_id: Account UUID
            user_id: User UUID to deallocate seat from
            deallocated_by: UUID of user deallocating seat
        """
        account = await self.get_account(account_id)
        
        try:
            account.deallocate_seat()
            
            # Store seat deallocation metadata
            if not account.metadata:
                account.metadata = {}
            
            account.metadata["seat_deallocations"] = account.metadata.get("seat_deallocations", [])
            account.metadata["seat_deallocations"].append({
                "user_id": str(user_id),
                "deallocated_by": str(deallocated_by) if deallocated_by else None,
                "deallocated_at": datetime.utcnow().isoformat()
            })
            
            await self.db.commit()
            
            logger.info(f"Successfully deallocated seat for user {user_id} on account {account_id}")
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error deallocating seat for account {account_id}: {e}")
            raise AccountServiceError(f"Failed to deallocate seat: {str(e)}")
    
    # Financial Management and Reporting
    
    async def get_usage_report(
        self,
        account_id: uuid.UUID,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Generate comprehensive usage report for account.
        
        Args:
            account_id: Account UUID
            start_date: Report start date
            end_date: Report end date
            
        Returns:
            Dict: Comprehensive usage report
        """
        account = await self.get_account(account_id, include_relationships=True)
        
        report = {
            "account_id": str(account.id),
            "publisher_id": str(account.publisher_id),
            "publisher_name": account.publisher.name if account.publisher else None,
            "plan_type": account.plan_type,
            "report_period": {
                "start_date": start_date.isoformat() if start_date else None,
                "end_date": end_date.isoformat() if end_date else None,
                "generated_at": datetime.utcnow().isoformat()
            },
            "seat_usage": {
                "licensed_seats": account.seats_licensed,
                "used_seats": account.seats_used,
                "available_seats": account.seats_available,
                "utilization_percentage": account.seat_utilization_percentage
            },
            "api_usage": {
                "monthly_calls": account.monthly_api_calls,
                "call_limit": account.api_call_limit,
                "usage_percentage": account.api_usage_percentage,
                "calls_by_endpoint": account.metadata.get("usage_tracking", {}).get("api_calls_by_endpoint", {}) if account.metadata else {}
            },
            "storage_usage": {
                "used_mb": account.storage_used_mb,
                "limit_mb": account.storage_limit_mb,
                "usage_percentage": account.storage_usage_percentage
            },
            "feature_limits": {
                "catalog_limit": account.catalog_limit,
                "user_limit": account.user_limit
            },
            "billing_summary": account.get_billing_summary()
        }
        
        return report
    
    async def get_financial_summary(
        self,
        account_id: uuid.UUID,
        include_history: bool = False
    ) -> Dict[str, Any]:
        """
        Get financial summary for account.
        
        Args:
            account_id: Account UUID
            include_history: Whether to include payment history
            
        Returns:
            Dict: Financial summary
        """
        account = await self.get_account(account_id, include_relationships=True)
        
        summary = {
            "account_id": str(account.id),
            "publisher_id": str(account.publisher_id),
            "publisher_name": account.publisher.name if account.publisher else None,
            "current_plan": {
                "plan_type": account.plan_type,
                "plan_name": account.plan_name,
                "billing_cycle": account.billing_cycle,
                "monthly_price": float(account.monthly_price),
                "annual_price": float(account.annual_price) if account.annual_price else None,
                "currency": account.currency
            },
            "billing_status": {
                "status": account.status,
                "outstanding_balance": float(account.outstanding_balance),
                "last_payment_amount": float(account.last_payment_amount) if account.last_payment_amount else None,
                "last_billing_date": account.last_billing_date.isoformat() if account.last_billing_date else None,
                "next_billing_date": account.next_billing_date.isoformat() if account.next_billing_date else None
            },
            "revenue_metrics": {
                "total_revenue": float(account.total_revenue),
                "average_monthly_revenue": float(account.total_revenue) / 12 if account.total_revenue > 0 else 0
            },
            "trial_info": {
                "is_trial": account.is_trial,
                "trial_ends_at": account.trial_ends_at.isoformat() if account.trial_ends_at else None,
                "days_remaining": account.trial_days_remaining
            }
        }
        
        if include_history and account.metadata:
            summary["payment_history"] = account.metadata.get("payment_history", [])
            summary["upgrade_history"] = account.metadata.get("upgrade_history", [])
            summary["downgrade_history"] = account.metadata.get("downgrade_history", [])
        
        return summary
    
    async def list_accounts(
        self,
        filters: Optional[Dict[str, Any]] = None,
        pagination: Optional[Dict[str, Any]] = None
    ) -> Tuple[List[Account], int]:
        """
        List accounts with filtering and pagination.
        
        Args:
            filters: Optional filters (status, plan_type, etc.)
            pagination: Optional pagination parameters
            
        Returns:
            Tuple[List[Account], int]: (accounts, total_count)
        """
        try:
            query = select(Account).options(
                joinedload(Account.publisher)
            )
            
            # Apply filters
            if filters:
                if "status" in filters:
                    query = query.where(Account.status == filters["status"])
                if "plan_type" in filters:
                    query = query.where(Account.plan_type == filters["plan_type"])
                if "billing_cycle" in filters:
                    query = query.where(Account.billing_cycle == filters["billing_cycle"])
                if "trial_expiring_in_days" in filters:
                    days = filters["trial_expiring_in_days"]
                    expiry_threshold = datetime.utcnow() + timedelta(days=days)
                    query = query.where(
                        and_(
                            Account.status == "trial",
                            Account.trial_ends_at <= expiry_threshold,
                            Account.trial_ends_at > datetime.utcnow()
                        )
                    )
            
            # Get total count
            count_query = select(func.count(Account.id))
            if filters:
                # Apply same filters to count query
                if "status" in filters:
                    count_query = count_query.where(Account.status == filters["status"])
                if "plan_type" in filters:
                    count_query = count_query.where(Account.plan_type == filters["plan_type"])
                if "billing_cycle" in filters:
                    count_query = count_query.where(Account.billing_cycle == filters["billing_cycle"])
                if "trial_expiring_in_days" in filters:
                    days = filters["trial_expiring_in_days"]
                    expiry_threshold = datetime.utcnow() + timedelta(days=days)
                    count_query = count_query.where(
                        and_(
                            Account.status == "trial",
                            Account.trial_ends_at <= expiry_threshold,
                            Account.trial_ends_at > datetime.utcnow()
                        )
                    )
            
            total_count_result = await self.db.execute(count_query)
            total_count = total_count_result.scalar()
            
            # Apply pagination and sorting
            if pagination:
                sort_by = pagination.get("sort_by", "created_at")
                sort_order = pagination.get("sort_order", "desc")
                
                if hasattr(Account, sort_by):
                    order_col = getattr(Account, sort_by)
                    if sort_order.lower() == "desc":
                        query = query.order_by(desc(order_col))
                    else:
                        query = query.order_by(asc(order_col))
                
                if "limit" in pagination:
                    query = query.limit(pagination["limit"])
                
                if "offset" in pagination:
                    query = query.offset(pagination["offset"])
            
            result = await self.db.execute(query)
            accounts = result.scalars().all()
            
            return list(accounts), total_count
            
        except Exception as e:
            logger.error(f"Error listing accounts: {e}")
            raise AccountServiceError(f"Failed to list accounts: {str(e)}")
    
    # Private Helper Methods
    
    def _validate_account_creation(self, account_data: Dict[str, Any]) -> ValidationResult:
        """Validate account creation data."""
        errors = []
        
        # Plan type validation
        plan_type = account_data.get("plan_type", "starter")
        valid_plans = ["starter", "professional", "enterprise", "custom"]
        if plan_type not in valid_plans:
            errors.append(ValidationError(
                field="plan_type",
                code="INVALID_PLAN_TYPE",
                message=f"Plan type must be one of: {valid_plans}"
            ))
        
        # Billing cycle validation
        billing_cycle = account_data.get("billing_cycle", "monthly")
        valid_cycles = ["monthly", "annual", "custom"]
        if billing_cycle not in valid_cycles:
            errors.append(ValidationError(
                field="billing_cycle",
                code="INVALID_BILLING_CYCLE",
                message=f"Billing cycle must be one of: {valid_cycles}"
            ))
        
        # Seat validation
        seats = account_data.get("seats_licensed", 1)
        if not isinstance(seats, int) or seats < 1:
            errors.append(ValidationError(
                field="seats_licensed",
                code="INVALID_SEATS",
                message="Seats licensed must be a positive integer"
            ))
        
        return ValidationResult(is_valid=len(errors) == 0, errors=errors)
    
    def _validate_subscription_upgrade(self, account: Account, new_plan_type: str, new_seats: Optional[int]) -> ValidationResult:
        """Validate subscription upgrade."""
        errors = []
        
        plan_hierarchy = ["starter", "professional", "enterprise", "custom"]
        
        try:
            current_index = plan_hierarchy.index(account.plan_type)
            new_index = plan_hierarchy.index(new_plan_type)
            
            if new_index <= current_index:
                errors.append(ValidationError(
                    field="new_plan_type",
                    code="INVALID_UPGRADE",
                    message=f"Cannot upgrade from {account.plan_type} to {new_plan_type}"
                ))
        except ValueError:
            errors.append(ValidationError(
                field="new_plan_type",
                code="INVALID_PLAN_TYPE",
                message=f"Invalid plan type: {new_plan_type}"
            ))
        
        if new_seats and new_seats < account.seats_used:
            errors.append(ValidationError(
                field="new_seats",
                code="INSUFFICIENT_SEATS",
                message=f"Cannot reduce seats below current usage. Used: {account.seats_used}, New: {new_seats}"
            ))
        
        return ValidationResult(is_valid=len(errors) == 0, errors=errors)
    
    def _validate_subscription_downgrade(self, account: Account, new_plan_type: str, new_seats: Optional[int]) -> ValidationResult:
        """Validate subscription downgrade."""
        errors = []
        
        plan_hierarchy = ["starter", "professional", "enterprise", "custom"]
        
        try:
            current_index = plan_hierarchy.index(account.plan_type)
            new_index = plan_hierarchy.index(new_plan_type)
            
            if new_index >= current_index:
                errors.append(ValidationError(
                    field="new_plan_type",
                    code="INVALID_DOWNGRADE",
                    message=f"Cannot downgrade from {account.plan_type} to {new_plan_type}"
                ))
        except ValueError:
            errors.append(ValidationError(
                field="new_plan_type",
                code="INVALID_PLAN_TYPE",
                message=f"Invalid plan type: {new_plan_type}"
            ))
        
        if new_seats and new_seats < account.seats_used:
            errors.append(ValidationError(
                field="new_seats",
                code="INSUFFICIENT_SEATS",
                message=f"Cannot reduce seats below current usage. Used: {account.seats_used}, New: {new_seats}"
            ))
        
        return ValidationResult(is_valid=len(errors) == 0, errors=errors)
    
    def _validate_billing_cycle_change(self, account: Account, new_billing_cycle: str) -> ValidationResult:
        """Validate billing cycle change."""
        errors = []
        
        valid_cycles = ["monthly", "annual", "custom"]
        if new_billing_cycle not in valid_cycles:
            errors.append(ValidationError(
                field="billing_cycle",
                code="INVALID_BILLING_CYCLE",
                message=f"Billing cycle must be one of: {valid_cycles}"
            ))
        
        if account.billing_cycle == new_billing_cycle:
            errors.append(ValidationError(
                field="billing_cycle",
                code="NO_CHANGE_NEEDED",
                message="Account already has this billing cycle"
            ))
        
        return ValidationResult(is_valid=len(errors) == 0, errors=errors)
    
    def _validate_plan_configuration(self, plan_type: str, billing_cycle: str, seats: Optional[int]) -> ValidationResult:
        """Validate plan configuration."""
        errors = []
        
        valid_plans = ["starter", "professional", "enterprise", "custom"]
        if plan_type not in valid_plans:
            errors.append(ValidationError(
                field="plan_type",
                code="INVALID_PLAN_TYPE",
                message=f"Plan type must be one of: {valid_plans}"
            ))
        
        valid_cycles = ["monthly", "annual", "custom"]
        if billing_cycle not in valid_cycles:
            errors.append(ValidationError(
                field="billing_cycle",
                code="INVALID_BILLING_CYCLE",
                message=f"Billing cycle must be one of: {valid_cycles}"
            ))
        
        if seats and (not isinstance(seats, int) or seats < 1):
            errors.append(ValidationError(
                field="seats",
                code="INVALID_SEATS",
                message="Seats must be a positive integer"
            ))
        
        return ValidationResult(is_valid=len(errors) == 0, errors=errors)
    
    def _validate_payment_method(self, payment_method_data: Dict[str, Any]) -> ValidationResult:
        """Validate payment method data."""
        errors = []
        
        required_fields = ["type", "provider"]
        for field in required_fields:
            if not payment_method_data.get(field):
                errors.append(ValidationError(
                    field=field,
                    code=f"{field.upper()}_REQUIRED",
                    message=f"{field.replace('_', ' ').title()} is required"
                ))
        
        valid_types = ["card", "bank_account", "paypal", "stripe"]
        payment_type = payment_method_data.get("type")
        if payment_type and payment_type not in valid_types:
            errors.append(ValidationError(
                field="type",
                code="INVALID_PAYMENT_TYPE",
                message=f"Payment type must be one of: {valid_types}"
            ))
        
        return ValidationResult(is_valid=len(errors) == 0, errors=errors)
    
    def _validate_billing_address(self, billing_address_data: Dict[str, Any]) -> ValidationResult:
        """Validate billing address data."""
        errors = []
        
        required_fields = ["street_address", "city", "country"]
        for field in required_fields:
            if not billing_address_data.get(field) or len(str(billing_address_data[field]).strip()) == 0:
                errors.append(ValidationError(
                    field=field,
                    code=f"{field.upper()}_REQUIRED",
                    message=f"{field.replace('_', ' ').title()} is required"
                ))
        
        return ValidationResult(is_valid=len(errors) == 0, errors=errors)
    
    def _apply_plan_defaults(self, account: Account) -> None:
        """Apply plan-specific default settings."""
        plan_defaults = {
            "starter": {
                "api_call_limit": 10000,
                "storage_limit_mb": 1024,
                "catalog_limit": 1000,
                "user_limit": 3,
                "monthly_price": Decimal("29.99")
            },
            "professional": {
                "api_call_limit": 50000,
                "storage_limit_mb": 10240,
                "catalog_limit": 10000,
                "user_limit": 10,
                "monthly_price": Decimal("99.99")
            },
            "enterprise": {
                "api_call_limit": None,
                "storage_limit_mb": None,
                "catalog_limit": None,
                "user_limit": None,
                "monthly_price": Decimal("499.99")
            },
            "custom": {
                "api_call_limit": None,
                "storage_limit_mb": None,
                "catalog_limit": None,
                "user_limit": None,
                "monthly_price": Decimal("0.00")
            }
        }
        
        defaults = plan_defaults.get(account.plan_type, {})
        for field, value in defaults.items():
            if hasattr(account, field) and getattr(account, field) is None:
                setattr(account, field, value)
    
    def _apply_plan_pricing(self, account: Account) -> None:
        """Apply pricing based on plan and billing cycle."""
        plan_pricing = {
            "starter": {"monthly": Decimal("29.99"), "annual": Decimal("299.99")},
            "professional": {"monthly": Decimal("99.99"), "annual": Decimal("999.99")},
            "enterprise": {"monthly": Decimal("499.99"), "annual": Decimal("4999.99")},
            "custom": {"monthly": Decimal("0.00"), "annual": Decimal("0.00")}
        }
        
        pricing = plan_pricing.get(account.plan_type, {})
        if account.billing_cycle in pricing:
            if account.billing_cycle == "monthly":
                account.monthly_price = pricing["monthly"]
            elif account.billing_cycle == "annual":
                account.annual_price = pricing["annual"]
                account.monthly_price = pricing["annual"] / 12
    
    def _apply_plan_limits(self, account: Account) -> None:
        """Apply usage limits based on plan."""
        limits = account.get_feature_limit("api_calls")
        if limits is not None:
            account.api_call_limit = limits
        
        limits = account.get_feature_limit("storage_mb")
        if limits is not None:
            account.storage_limit_mb = limits
        
        limits = account.get_feature_limit("works")
        if limits is not None:
            account.catalog_limit = limits
        
        limits = account.get_feature_limit("users")
        if limits is not None:
            account.user_limit = limits
    
    def _calculate_proration(self, account: Account, new_plan_type: str, new_seats: Optional[int]) -> Decimal:
        """Calculate prorated charges for plan changes."""
        # This is a simplified proration calculation
        # In a real implementation, this would be more sophisticated
        
        if not account.current_period_start or not account.current_period_end:
            return Decimal("0.00")
        
        # Calculate remaining days in current period
        now = datetime.utcnow()
        total_days = (account.current_period_end - account.current_period_start).days
        remaining_days = (account.current_period_end - now).days
        
        if remaining_days <= 0:
            return Decimal("0.00")
        
        # Get current and new pricing
        current_monthly_price = account.monthly_price
        
        # Mock new pricing (in real implementation, this would come from pricing service)
        new_pricing = {
            "starter": Decimal("29.99"),
            "professional": Decimal("99.99"),
            "enterprise": Decimal("499.99"),
            "custom": Decimal("0.00")
        }
        
        new_monthly_price = new_pricing.get(new_plan_type, Decimal("0.00"))
        
        # Calculate daily rates
        current_daily_rate = current_monthly_price / 30
        new_daily_rate = new_monthly_price / 30
        
        # Calculate proration
        current_remaining_cost = current_daily_rate * remaining_days
        new_remaining_cost = new_daily_rate * remaining_days
        
        return new_remaining_cost - current_remaining_cost