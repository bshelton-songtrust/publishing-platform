"""Account model for billing and subscription management in the multi-tenant publishing platform."""

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, Dict, Any, List

from sqlalchemy import (
    Column, String, Boolean, Integer, DateTime, Numeric, CheckConstraint,
    Index, UUID, ForeignKey, func
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from .base import TimestampMixin
from src.core.database import Base


class Account(Base, TimestampMixin):
    """
    Account model representing billing and subscription management for publishers.
    
    This model handles subscription plans, billing information, usage tracking,
    and financial operations for each publisher/tenant in the system.
    
    Key Features:
    - Multi-tier subscription plans (starter, professional, enterprise, custom)
    - Flexible billing cycles (monthly, annual, custom)
    - Seat-based licensing with usage tracking
    - Trial period management
    - Usage monitoring (API calls, storage, features)
    - Payment method management
    - Account status lifecycle management
    - Billing address and tax information
    - Plan upgrade/downgrade workflows
    """
    
    __tablename__ = "accounts"
    
    # Core Identity Fields
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Primary key UUID for account identity"
    )
    
    publisher_id = Column(
        UUID(as_uuid=True),
        ForeignKey("publishers.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        comment="Associated publisher UUID (one-to-one relationship)"
    )
    
    # Subscription Fields
    plan_type = Column(
        String(20),
        nullable=False,
        default="starter",
        comment="Subscription plan: starter, professional, enterprise, custom"
    )
    
    plan_name = Column(
        String(100),
        nullable=True,
        comment="Custom plan name for enterprise/custom plans"
    )
    
    billing_cycle = Column(
        String(20),
        nullable=False,
        default="monthly",
        comment="Billing frequency: monthly, annual, custom"
    )
    
    status = Column(
        String(20),
        nullable=False,
        default="trial",
        comment="Account status: trial, active, suspended, cancelled, past_due"
    )
    
    # Licensing Fields
    seats_licensed = Column(
        Integer,
        nullable=False,
        default=1,
        comment="Total number of user seats licensed"
    )
    
    seats_used = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Current number of seats in use"
    )
    
    # Pricing Fields
    monthly_price = Column(
        Numeric(10, 2),
        nullable=False,
        default=0.00,
        comment="Monthly subscription price in USD"
    )
    
    annual_price = Column(
        Numeric(10, 2),
        nullable=True,
        comment="Annual subscription price in USD (if applicable)"
    )
    
    currency = Column(
        String(3),
        nullable=False,
        default="USD",
        comment="Billing currency code (ISO 4217 format)"
    )
    
    # Trial Management
    trial_starts_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Trial period start timestamp"
    )
    
    trial_ends_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Trial period end timestamp"
    )
    
    trial_extended = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="True if trial has been extended beyond standard period"
    )
    
    # Billing Timeline
    current_period_start = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Current billing period start date"
    )
    
    current_period_end = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Current billing period end date"
    )
    
    next_billing_date = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Next scheduled billing date"
    )
    
    last_billing_date = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last successful billing date"
    )
    
    # Billing Information
    billing_email = Column(
        String(255),
        nullable=True,
        comment="Email address for billing notifications"
    )
    
    billing_address = Column(
        JSONB,
        default=dict,
        comment="Complete billing address information in JSON format"
    )
    
    tax_id = Column(
        String(50),
        nullable=True,
        comment="Tax identification number for billing"
    )
    
    payment_method = Column(
        JSONB,
        default=dict,
        comment="Payment method details (encrypted/tokenized)"
    )
    
    # Usage Tracking
    monthly_api_calls = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Current month API calls count"
    )
    
    api_call_limit = Column(
        Integer,
        nullable=True,
        comment="Monthly API call limit (null for unlimited)"
    )
    
    storage_used_mb = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Current storage usage in megabytes"
    )
    
    storage_limit_mb = Column(
        Integer,
        nullable=True,
        comment="Storage limit in megabytes (null for unlimited)"
    )
    
    # Feature Limits
    catalog_limit = Column(
        Integer,
        nullable=True,
        comment="Maximum number of works in catalog (null for unlimited)"
    )
    
    user_limit = Column(
        Integer,
        nullable=True,
        comment="Maximum number of users (null for unlimited)"
    )
    
    # Financial Tracking
    total_revenue = Column(
        Numeric(12, 2),
        nullable=False,
        default=0.00,
        comment="Total revenue collected from this account"
    )
    
    last_payment_amount = Column(
        Numeric(10, 2),
        nullable=True,
        comment="Amount of last successful payment"
    )
    
    outstanding_balance = Column(
        Numeric(10, 2),
        nullable=False,
        default=0.00,
        comment="Current outstanding balance"
    )
    
    # Metadata Fields
    metadata = Column(
        JSONB,
        default=dict,
        comment="Additional account metadata and flexible attributes"
    )
    
    # Table-level constraints and indexes
    __table_args__ = (
        # Check constraints for enum-like fields
        CheckConstraint(
            "plan_type IN ('starter', 'professional', 'enterprise', 'custom')",
            name="valid_plan_type"
        ),
        CheckConstraint(
            "billing_cycle IN ('monthly', 'annual', 'custom')",
            name="valid_billing_cycle"
        ),
        CheckConstraint(
            "status IN ('trial', 'active', 'suspended', 'cancelled', 'past_due')",
            name="valid_account_status"
        ),
        CheckConstraint(
            "currency ~ '^[A-Z]{3}$'",
            name="valid_currency_code"
        ),
        
        # Business rules constraints
        CheckConstraint(
            "seats_licensed >= 1",
            name="minimum_licensed_seats"
        ),
        CheckConstraint(
            "seats_used >= 0 AND seats_used <= seats_licensed",
            name="valid_seats_usage"
        ),
        CheckConstraint(
            "monthly_price >= 0",
            name="non_negative_monthly_price"
        ),
        CheckConstraint(
            "annual_price IS NULL OR annual_price >= 0",
            name="non_negative_annual_price"
        ),
        CheckConstraint(
            "monthly_api_calls >= 0",
            name="non_negative_api_calls"
        ),
        CheckConstraint(
            "api_call_limit IS NULL OR api_call_limit > 0",
            name="positive_api_call_limit"
        ),
        CheckConstraint(
            "storage_used_mb >= 0",
            name="non_negative_storage_used"
        ),
        CheckConstraint(
            "storage_limit_mb IS NULL OR storage_limit_mb > 0",
            name="positive_storage_limit"
        ),
        CheckConstraint(
            "total_revenue >= 0",
            name="non_negative_total_revenue"
        ),
        CheckConstraint(
            "billing_email IS NULL OR billing_email ~ '^[^@]+@[^@]+\\.[^@]+$'",
            name="valid_billing_email_format"
        ),
        
        # Trial and billing date constraints
        CheckConstraint(
            "trial_ends_at IS NULL OR trial_starts_at IS NULL OR trial_ends_at > trial_starts_at",
            name="valid_trial_period"
        ),
        CheckConstraint(
            "current_period_end IS NULL OR current_period_start IS NULL OR current_period_end > current_period_start",
            name="valid_billing_period"
        ),
        
        # Performance indexes
        Index("idx_accounts_publisher_id", "publisher_id"),
        Index("idx_accounts_status", "status"),
        Index("idx_accounts_plan_type", "plan_type"),
        Index("idx_accounts_billing_cycle", "billing_cycle"),
        Index("idx_accounts_next_billing_date", "next_billing_date"),
        Index("idx_accounts_trial_ends_at", "trial_ends_at"),
        Index("idx_accounts_current_period_end", "current_period_end"),
        Index("idx_accounts_billing_email", "billing_email"),
        
        # Composite indexes for common query patterns
        Index("idx_accounts_status_plan", "status", "plan_type"),
        Index("idx_accounts_status_billing", "status", "next_billing_date"),
        Index("idx_accounts_trial_status", "status", "trial_ends_at"),
    )

    # Relationships
    publisher = relationship("Publisher", back_populates="account")

    def __init__(self, **kwargs):
        """
        Initialize Account with default settings and metadata.
        
        Sets up default billing address structure, payment method template,
        and metadata for new account instances.
        """
        super().__init__(**kwargs)
        
        # Initialize default billing address structure if not provided
        if not self.billing_address:
            self.billing_address = {
                "company_name": None,
                "street_address": None,
                "city": None,
                "state_province": None,
                "postal_code": None,
                "country": None
            }
        
        # Initialize default payment method structure if not provided
        if not self.payment_method:
            self.payment_method = {
                "type": None,  # "card", "bank_account", "paypal", etc.
                "provider": None,  # "stripe", "paypal", "square", etc.
                "provider_id": None,  # External payment method ID
                "last_four": None,
                "expires_at": None,
                "is_default": True
            }
        
        # Initialize default metadata if not provided
        if not self.metadata:
            self.metadata = {
                "plan_features": {},
                "billing_history": [],
                "discount_codes": [],
                "referral_source": None,
                "account_manager": None,
                "custom_terms": False,
                "auto_renewal": True
            }

    @property
    def is_trial(self) -> bool:
        """Check if account is in trial status."""
        return self.status == "trial"
    
    @property
    def is_active(self) -> bool:
        """Check if account is in active status."""
        return self.status == "active"
    
    @property
    def is_suspended(self) -> bool:
        """Check if account is suspended."""
        return self.status == "suspended"
    
    @property
    def is_cancelled(self) -> bool:
        """Check if account is cancelled."""
        return self.status == "cancelled"
    
    @property
    def is_past_due(self) -> bool:
        """Check if account is past due."""
        return self.status == "past_due"
    
    @property
    def trial_days_remaining(self) -> Optional[int]:
        """Get number of trial days remaining."""
        if not self.is_trial or not self.trial_ends_at:
            return None
        
        remaining = (self.trial_ends_at - datetime.utcnow()).days
        return max(0, remaining)
    
    @property
    def is_trial_expired(self) -> bool:
        """Check if trial period has expired."""
        if not self.trial_ends_at:
            return False
        return datetime.utcnow() > self.trial_ends_at
    
    @property
    def seats_available(self) -> int:
        """Get number of available seats."""
        return max(0, self.seats_licensed - self.seats_used)
    
    @property
    def seat_utilization_percentage(self) -> int:
        """Get seat utilization as percentage."""
        if self.seats_licensed == 0:
            return 0
        return int((self.seats_used / self.seats_licensed) * 100)
    
    @property
    def api_usage_percentage(self) -> Optional[int]:
        """Get API usage as percentage of limit."""
        if not self.api_call_limit:
            return None
        return int((self.monthly_api_calls / self.api_call_limit) * 100)
    
    @property
    def storage_usage_percentage(self) -> Optional[int]:
        """Get storage usage as percentage of limit."""
        if not self.storage_limit_mb:
            return None
        return int((self.storage_used_mb / self.storage_limit_mb) * 100)

    def start_trial(self, days: int = 14) -> None:
        """
        Start trial period for the account.
        
        Args:
            days: Number of trial days to grant (default 14)
        """
        now = datetime.utcnow()
        self.status = "trial"
        self.trial_starts_at = now
        self.trial_ends_at = now + timedelta(days=days)

    def extend_trial(self, additional_days: int) -> None:
        """
        Extend trial period by additional days.
        
        Args:
            additional_days: Number of additional days to add
        """
        if not self.trial_ends_at:
            raise ValueError("Cannot extend trial - no trial end date set")
        
        self.trial_ends_at += timedelta(days=additional_days)
        self.trial_extended = True

    def activate_subscription(self, plan_type: str, billing_cycle: str = "monthly") -> None:
        """
        Activate paid subscription and end trial period.
        
        Args:
            plan_type: New subscription plan type
            billing_cycle: Billing frequency
        """
        now = datetime.utcnow()
        
        self.status = "active"
        self.plan_type = plan_type
        self.billing_cycle = billing_cycle
        
        # Set current billing period
        self.current_period_start = now
        
        if billing_cycle == "monthly":
            self.current_period_end = now + timedelta(days=30)
            self.next_billing_date = self.current_period_end
        elif billing_cycle == "annual":
            self.current_period_end = now + timedelta(days=365)
            self.next_billing_date = self.current_period_end

    def suspend_account(self, reason: str = None) -> None:
        """
        Suspend account due to payment issues or violations.
        
        Args:
            reason: Reason for suspension (stored in metadata)
        """
        self.status = "suspended"
        
        if reason:
            if not self.metadata:
                self.metadata = {}
            self.metadata["suspension_reason"] = reason
            self.metadata["suspended_at"] = datetime.utcnow().isoformat()

    def reactivate_account(self) -> None:
        """Reactivate suspended account."""
        if self.is_trial_expired and self.trial_ends_at:
            # If trial was expired, move to cancelled instead
            self.status = "cancelled"
        else:
            self.status = "active"
        
        # Clear suspension metadata
        if self.metadata:
            self.metadata.pop("suspension_reason", None)
            self.metadata.pop("suspended_at", None)

    def cancel_subscription(self, immediate: bool = False) -> None:
        """
        Cancel subscription.
        
        Args:
            immediate: If True, cancel immediately. If False, cancel at period end.
        """
        self.status = "cancelled"
        
        if not immediate and self.current_period_end:
            # Schedule cancellation at end of current period
            if not self.metadata:
                self.metadata = {}
            self.metadata["cancellation_scheduled"] = True
            self.metadata["cancellation_effective_date"] = self.current_period_end.isoformat()

    def upgrade_plan(self, new_plan_type: str, new_seats: int = None) -> None:
        """
        Upgrade to a higher tier plan.
        
        Args:
            new_plan_type: New plan type to upgrade to
            new_seats: New number of seats (if applicable)
        """
        # Store previous plan in metadata for billing calculation
        if not self.metadata:
            self.metadata = {}
        
        self.metadata["previous_plan"] = {
            "plan_type": self.plan_type,
            "seats_licensed": self.seats_licensed,
            "upgraded_at": datetime.utcnow().isoformat()
        }
        
        self.plan_type = new_plan_type
        
        if new_seats:
            self.seats_licensed = new_seats

    def record_payment(self, amount: Decimal, payment_date: datetime = None) -> None:
        """
        Record successful payment.
        
        Args:
            amount: Payment amount
            payment_date: Payment timestamp (defaults to now)
        """
        if payment_date is None:
            payment_date = datetime.utcnow()
        
        self.last_payment_amount = amount
        self.last_billing_date = payment_date
        self.total_revenue += amount
        
        # Clear outstanding balance if payment covers it
        if amount >= self.outstanding_balance:
            self.outstanding_balance = max(0, self.outstanding_balance - amount)
        
        # If account was past due, reactivate it
        if self.is_past_due:
            self.status = "active"

    def add_outstanding_balance(self, amount: Decimal) -> None:
        """
        Add to outstanding balance (for failed payments).
        
        Args:
            amount: Amount to add to balance
        """
        self.outstanding_balance += amount
        
        # Mark as past due if there's an outstanding balance
        if self.outstanding_balance > 0 and self.is_active:
            self.status = "past_due"

    def increment_api_usage(self, calls: int = 1) -> bool:
        """
        Increment API call usage.
        
        Args:
            calls: Number of API calls to add
            
        Returns:
            bool: True if under limit, False if over limit
        """
        self.monthly_api_calls += calls
        
        if self.api_call_limit:
            return self.monthly_api_calls <= self.api_call_limit
        
        return True

    def reset_monthly_usage(self) -> None:
        """Reset monthly usage counters at billing cycle."""
        self.monthly_api_calls = 0

    def can_add_seat(self) -> bool:
        """Check if account can add another user seat."""
        return self.seats_used < self.seats_licensed

    def allocate_seat(self) -> bool:
        """
        Allocate a user seat.
        
        Returns:
            bool: True if seat was allocated, False if no seats available
        """
        if not self.can_add_seat():
            return False
        
        self.seats_used += 1
        return True

    def deallocate_seat(self) -> None:
        """Deallocate a user seat."""
        if self.seats_used > 0:
            self.seats_used -= 1

    def get_feature_limit(self, feature: str) -> Optional[int]:
        """
        Get limit for a specific feature based on plan.
        
        Args:
            feature: Feature name to check
            
        Returns:
            Optional[int]: Limit value or None for unlimited
        """
        feature_limits = {
            "starter": {
                "works": 1000,
                "users": 3,
                "api_calls": 10000,
                "storage_mb": 1024,  # 1 GB
            },
            "professional": {
                "works": 10000,
                "users": 10,
                "api_calls": 50000,
                "storage_mb": 10240,  # 10 GB
            },
            "enterprise": {
                "works": None,  # Unlimited
                "users": None,
                "api_calls": None,
                "storage_mb": None,
            },
            "custom": {
                "works": None,
                "users": None,
                "api_calls": None,
                "storage_mb": None,
            }
        }
        
        plan_limits = feature_limits.get(self.plan_type, {})
        return plan_limits.get(feature)

    def is_over_limit(self, feature: str, current_usage: int) -> bool:
        """
        Check if current usage exceeds plan limit for feature.
        
        Args:
            feature: Feature name to check
            current_usage: Current usage count
            
        Returns:
            bool: True if over limit
        """
        limit = self.get_feature_limit(feature)
        if limit is None:  # Unlimited
            return False
        return current_usage > limit

    def get_billing_summary(self) -> Dict[str, Any]:
        """
        Get comprehensive billing summary.
        
        Returns:
            Dict: Complete billing information
        """
        return {
            "account_id": str(self.id),
            "plan_type": self.plan_type,
            "plan_name": self.plan_name,
            "status": self.status,
            "billing_cycle": self.billing_cycle,
            "monthly_price": float(self.monthly_price),
            "annual_price": float(self.annual_price) if self.annual_price else None,
            "currency": self.currency,
            "seats_licensed": self.seats_licensed,
            "seats_used": self.seats_used,
            "current_period": {
                "start": self.current_period_start.isoformat() if self.current_period_start else None,
                "end": self.current_period_end.isoformat() if self.current_period_end else None,
            },
            "next_billing_date": self.next_billing_date.isoformat() if self.next_billing_date else None,
            "outstanding_balance": float(self.outstanding_balance),
            "trial_info": {
                "is_trial": self.is_trial,
                "trial_ends_at": self.trial_ends_at.isoformat() if self.trial_ends_at else None,
                "days_remaining": self.trial_days_remaining
            },
            "usage": {
                "api_calls": self.monthly_api_calls,
                "api_call_limit": self.api_call_limit,
                "storage_used_mb": self.storage_used_mb,
                "storage_limit_mb": self.storage_limit_mb,
                "api_usage_percentage": self.api_usage_percentage,
                "storage_usage_percentage": self.storage_usage_percentage
            }
        }

    def __repr__(self) -> str:
        """String representation of the Account."""
        return (f"<Account(id={self.id}, publisher_id={self.publisher_id}, "
                f"plan='{self.plan_type}', status='{self.status}', "
                f"seats={self.seats_used}/{self.seats_licensed})>")

    def __str__(self) -> str:
        """Human-readable string representation."""
        return f"{self.plan_type.title()} Account ({self.status.title()})"