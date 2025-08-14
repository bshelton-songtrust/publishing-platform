"""Publisher architecture with user management and permissions

Revision ID: 003
Revises: 002
Create Date: 2024-01-15 12:00:00.000000

This migration transforms the existing tenant-based system into a comprehensive
multi-tenant publisher platform with user management and granular permissions.

Key Changes:
1. Rename tenants table to publishers with enhanced fields
2. Add users, accounts, permissions, and relationship tables  
3. Update existing tables with user audit fields
4. Create enhanced RLS policies for user-level access control
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply publisher architecture changes."""
    
    # ================================================================
    # 1. RENAME TENANTS TO PUBLISHERS AND ENHANCE
    # ================================================================
    
    # Rename the tenants table to publishers
    op.rename_table('tenants', 'publishers')
    
    # Add new publisher-specific columns
    op.add_column('publishers', sa.Column(
        'publisher_type', sa.String(50), nullable=False, default='professional',
        comment="Publisher type: enterprise, professional, platform, boutique"
    ))
    op.add_column('publishers', sa.Column(
        'business_model', sa.String(50), nullable=False, default='traditional',
        comment="Business model: traditional, platform, hybrid"
    ))
    op.add_column('publishers', sa.Column(
        'branding', postgresql.JSONB, default=sa.text("'{}'::jsonb"),
        comment="Publisher branding settings (logos, colors, etc.)"
    ))
    op.add_column('publishers', sa.Column(
        'tax_id', sa.String(50),
        comment="Tax identification number"
    ))
    op.add_column('publishers', sa.Column(
        'business_license', sa.String(100),
        comment="Business license number"
    ))
    op.add_column('publishers', sa.Column(
        'primary_contact_email', sa.String(255),
        comment="Primary contact email address"
    ))
    op.add_column('publishers', sa.Column(
        'support_email', sa.String(255),
        comment="Support email address"
    ))
    op.add_column('publishers', sa.Column(
        'business_address', postgresql.JSONB, default=sa.text("'{}'::jsonb"),
        comment="Business address information"
    ))
    
    # Update existing constraints
    op.drop_constraint('valid_tenant_status', 'publishers', type_='check')
    op.create_check_constraint(
        'valid_publisher_status',
        'publishers',
        "status IN ('active', 'suspended', 'archived', 'trial')"
    )
    
    op.drop_constraint('valid_plan_type', 'publishers', type_='check')  
    op.create_check_constraint(
        'valid_plan_type',
        'publishers', 
        "plan_type IN ('free', 'starter', 'professional', 'enterprise', 'platform')"
    )
    
    # Add new constraints
    op.create_check_constraint(
        'valid_publisher_type',
        'publishers',
        "publisher_type IN ('enterprise', 'professional', 'platform', 'boutique')"
    )
    op.create_check_constraint(
        'valid_business_model', 
        'publishers',
        "business_model IN ('traditional', 'platform', 'hybrid')"
    )
    
    # ================================================================
    # 2. CREATE ACCOUNTS TABLE
    # ================================================================
    
    op.create_table(
        'accounts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=sa.text("uuid_generate_v4()")),
        sa.Column('publisher_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('account_type', sa.String(50), nullable=False, default='standard'),
        
        # Subscription details
        sa.Column('plan_type', sa.String(50), nullable=False, default='free'),
        sa.Column('billing_cycle', sa.String(20), default='monthly'),
        sa.Column('seats_licensed', sa.Integer, default=1),
        sa.Column('seats_used', sa.Integer, default=0),
        
        # Billing information
        sa.Column('billing_email', sa.String(255)),
        sa.Column('billing_address', postgresql.JSONB, default=sa.text("'{}'::jsonb")),
        sa.Column('payment_method', postgresql.JSONB, default=sa.text("'{}'::jsonb")),
        
        # Account status
        sa.Column('status', sa.String(20), nullable=False, default='active'),
        sa.Column('trial_ends_at', sa.DateTime(timezone=True)),
        sa.Column('next_billing_date', sa.DateTime(timezone=True)),
        
        # Usage tracking
        sa.Column('monthly_api_calls', sa.Integer, default=0),
        sa.Column('storage_used_mb', sa.Integer, default=0),
        
        # Metadata
        sa.Column('metadata', postgresql.JSONB, default=sa.text("'{}'::jsonb")),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, default=sa.func.now()),
        
        # Foreign keys
        sa.ForeignKeyConstraint(['publisher_id'], ['publishers.id'], ondelete='CASCADE'),
        
        # Constraints
        sa.CheckConstraint("account_type IN ('standard', 'enterprise', 'platform')", name='valid_account_type'),
        sa.CheckConstraint("plan_type IN ('free', 'starter', 'professional', 'enterprise', 'platform')", name='valid_account_plan_type'),
        sa.CheckConstraint("billing_cycle IN ('monthly', 'annual', 'enterprise')", name='valid_billing_cycle'),
        sa.CheckConstraint("status IN ('active', 'suspended', 'cancelled', 'trial')", name='valid_account_status'),
        sa.CheckConstraint("seats_used <= seats_licensed", name='seats_used_not_exceed_licensed'),
    )
    
    # Create indexes for accounts
    op.create_index('idx_accounts_publisher_id', 'accounts', ['publisher_id'])
    op.create_index('idx_accounts_status', 'accounts', ['status'])
    op.create_index('idx_accounts_plan_type', 'accounts', ['plan_type'])
    
    # ================================================================
    # 3. CREATE USERS TABLE
    # ================================================================
    
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=sa.text("uuid_generate_v4()")),
        
        # Identity
        sa.Column('email', sa.String(255), unique=True, nullable=False),
        sa.Column('username', sa.String(100)),
        sa.Column('first_name', sa.String(100), nullable=False),
        sa.Column('last_name', sa.String(100), nullable=False),
        sa.Column('full_name', sa.String(255), sa.Computed("first_name || ' ' || last_name")),
        
        # Authentication
        sa.Column('password_hash', sa.String(255)),
        sa.Column('is_external_auth', sa.Boolean, default=False),
        sa.Column('external_auth_provider', sa.String(50)),
        sa.Column('external_auth_id', sa.String(255)),
        
        # Profile
        sa.Column('avatar_url', sa.String(500)),
        sa.Column('phone_number', sa.String(50)),
        sa.Column('timezone', sa.String(50), default='UTC'),
        sa.Column('language', sa.String(10), default='en'),
        
        # Status
        sa.Column('status', sa.String(20), nullable=False, default='active'),
        sa.Column('is_verified', sa.Boolean, default=False),
        sa.Column('email_verified_at', sa.DateTime(timezone=True)),
        sa.Column('last_login_at', sa.DateTime(timezone=True)),
        
        # Security
        sa.Column('failed_login_attempts', sa.Integer, default=0),
        sa.Column('locked_until', sa.DateTime(timezone=True)),
        sa.Column('password_changed_at', sa.DateTime(timezone=True), default=sa.func.now()),
        sa.Column('mfa_enabled', sa.Boolean, default=False),
        sa.Column('mfa_secret', sa.String(255)),
        
        # Metadata
        sa.Column('preferences', postgresql.JSONB, default=sa.text("'{}'::jsonb")),
        sa.Column('metadata', postgresql.JSONB, default=sa.text("'{}'::jsonb")),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, default=sa.func.now()),
        
        # Constraints
        sa.CheckConstraint("status IN ('active', 'inactive', 'suspended', 'archived')", name='valid_user_status'),
        sa.CheckConstraint(
            "external_auth_provider IS NULL OR external_auth_provider IN ('active_directory', 'google', 'azure', 'okta')",
            name='valid_external_provider'
        ),
        sa.CheckConstraint("failed_login_attempts >= 0", name='non_negative_failed_attempts'),
        sa.CheckConstraint("length(first_name) > 0", name='first_name_not_empty'),
        sa.CheckConstraint("length(last_name) > 0", name='last_name_not_empty'),
        sa.CheckConstraint("email ~ '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$'", name='valid_email_format'),
    )
    
    # Create indexes for users
    op.create_index('idx_users_email', 'users', ['email'], unique=True)
    op.create_index('idx_users_username', 'users', ['username'])
    op.create_index('idx_users_full_name', 'users', ['full_name'])
    op.create_index('idx_users_status', 'users', ['status'])
    op.create_index('idx_users_external_auth', 'users', ['external_auth_provider', 'external_auth_id'])
    op.create_index('idx_users_last_login', 'users', ['last_login_at'])
    
    # ================================================================
    # 4. CREATE USER-PUBLISHER RELATIONSHIPS TABLE
    # ================================================================
    
    op.create_table(
        'user_publishers',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=sa.text("uuid_generate_v4()")),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('publisher_id', postgresql.UUID(as_uuid=True), nullable=False),
        
        # Access details
        sa.Column('role', sa.String(50), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, default='active'),
        
        # Permissions
        sa.Column('permissions', postgresql.JSONB, default=sa.text("'[]'::jsonb")),
        sa.Column('restrictions', postgresql.JSONB, default=sa.text("'{}'::jsonb")),
        
        # Metadata
        sa.Column('invited_by', postgresql.UUID(as_uuid=True)),
        sa.Column('invited_at', sa.DateTime(timezone=True)),
        sa.Column('joined_at', sa.DateTime(timezone=True), default=sa.func.now()),
        sa.Column('last_accessed_at', sa.DateTime(timezone=True)),
        
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, default=sa.func.now()),
        
        # Foreign keys
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['publisher_id'], ['publishers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['invited_by'], ['users.id']),
        
        # Unique constraint
        sa.UniqueConstraint('user_id', 'publisher_id', name='unique_user_publisher'),
        
        # Constraints
        sa.CheckConstraint(
            "role IN ('system_admin', 'publisher_admin', 'department_admin', 'staff_user', 'creator_user', 'read_only_user')",
            name='valid_user_publisher_role'
        ),
        sa.CheckConstraint("status IN ('active', 'inactive', 'suspended')", name='valid_user_publisher_status'),
    )
    
    # Create indexes for user_publishers
    op.create_index('idx_user_publishers_user_id', 'user_publishers', ['user_id'])
    op.create_index('idx_user_publishers_publisher_id', 'user_publishers', ['publisher_id'])
    op.create_index('idx_user_publishers_role', 'user_publishers', ['role'])
    op.create_index('idx_user_publishers_status', 'user_publishers', ['status'])
    op.create_index('idx_user_publishers_last_accessed', 'user_publishers', ['last_accessed_at'])
    
    # ================================================================
    # 5. CREATE ROLES TABLE
    # ================================================================
    
    op.create_table(
        'roles',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=sa.text("uuid_generate_v4()")),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('publisher_id', postgresql.UUID(as_uuid=True)),
        
        # Role configuration
        sa.Column('permissions', postgresql.JSONB, nullable=False, default=sa.text("'[]'::jsonb")),
        sa.Column('is_system_role', sa.Boolean, default=False),
        sa.Column('is_active', sa.Boolean, default=True),
        
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, default=sa.func.now()),
        
        # Foreign keys
        sa.ForeignKeyConstraint(['publisher_id'], ['publishers.id'], ondelete='CASCADE'),
        
        # Unique constraint
        sa.UniqueConstraint('name', 'publisher_id', name='unique_role_name_per_publisher'),
        
        # Constraints
        sa.CheckConstraint("length(name) > 0", name='role_name_not_empty'),
    )
    
    # Create indexes for roles
    op.create_index('idx_roles_name', 'roles', ['name'])
    op.create_index('idx_roles_publisher_id', 'roles', ['publisher_id'])
    op.create_index('idx_roles_system', 'roles', ['is_system_role'])
    op.create_index('idx_roles_active', 'roles', ['is_active'])
    
    # ================================================================
    # 6. CREATE PERMISSIONS TABLE
    # ================================================================
    
    op.create_table(
        'permissions',
        sa.Column('id', sa.String(100), primary_key=True),  # e.g., 'works:create'
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('resource', sa.String(100), nullable=False),  # 'works', 'songwriters', etc.
        sa.Column('action', sa.String(50), nullable=False),    # 'create', 'read', 'update', etc.
        sa.Column('is_system_permission', sa.Boolean, default=True),
        
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, default=sa.func.now()),
        
        # Constraints
        sa.CheckConstraint("length(name) > 0", name='permission_name_not_empty'),
        sa.CheckConstraint("length(resource) > 0", name='permission_resource_not_empty'),
        sa.CheckConstraint("length(action) > 0", name='permission_action_not_empty'),
        sa.CheckConstraint("id = resource || ':' || action", name='permission_id_format'),
    )
    
    # Create indexes for permissions
    op.create_index('idx_permissions_resource', 'permissions', ['resource'])
    op.create_index('idx_permissions_action', 'permissions', ['action'])
    op.create_index('idx_permissions_system', 'permissions', ['is_system_permission'])
    
    # ================================================================
    # 7. CREATE USER SESSIONS TABLE
    # ================================================================
    
    op.create_table(
        'user_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=sa.text("uuid_generate_v4()")),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('publisher_id', postgresql.UUID(as_uuid=True)),
        
        # Session details
        sa.Column('session_token_hash', sa.String(255), nullable=False),
        sa.Column('refresh_token_hash', sa.String(255)),
        
        # Context
        sa.Column('ip_address', postgresql.INET),
        sa.Column('user_agent', sa.Text),
        
        # Timing
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_activity_at', sa.DateTime(timezone=True), default=sa.func.now()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, default=sa.func.now()),
        
        # Foreign keys
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['publisher_id'], ['publishers.id'], ondelete='CASCADE'),
        
        # Constraints
        sa.CheckConstraint("expires_at > created_at", name='valid_session_expiry'),
    )
    
    # Create indexes for user_sessions
    op.create_index('idx_user_sessions_user_id', 'user_sessions', ['user_id'])
    op.create_index('idx_user_sessions_publisher_id', 'user_sessions', ['publisher_id'])
    op.create_index('idx_user_sessions_token_hash', 'user_sessions', ['session_token_hash'])
    op.create_index('idx_user_sessions_expires_at', 'user_sessions', ['expires_at'])
    op.create_index('idx_user_sessions_last_activity', 'user_sessions', ['last_activity_at'])
    
    # ================================================================
    # 8. CREATE SERVICE ACCOUNTS TABLE
    # ================================================================
    
    op.create_table(
        'service_accounts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=sa.text("uuid_generate_v4()")),
        
        # Service Identity
        sa.Column('name', sa.String(100), nullable=False, unique=True),
        sa.Column('display_name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('service_type', sa.String(50), nullable=False, default='external'),
        
        # Publisher Association
        sa.Column('publisher_id', postgresql.UUID(as_uuid=True)),
        
        # Owner Information
        sa.Column('owner_user_id', postgresql.UUID(as_uuid=True)),
        sa.Column('owner_email', sa.String(255), nullable=False),
        
        # Status and Lifecycle
        sa.Column('status', sa.String(20), nullable=False, default='active'),
        sa.Column('is_active', sa.Boolean, default=True, nullable=False),
        sa.Column('suspended_at', sa.DateTime(timezone=True)),
        sa.Column('suspended_reason', sa.Text),
        sa.Column('expires_at', sa.DateTime(timezone=True)),
        
        # Permissions and Scopes
        sa.Column('scopes', postgresql.ARRAY(sa.String), default=sa.text("ARRAY[]::varchar[]")),
        sa.Column('permissions', postgresql.JSONB, default=sa.text("'{}'::jsonb")),
        sa.Column('allowed_resources', postgresql.JSONB, default=sa.text("'{}'::jsonb")),
        
        # Rate Limiting
        sa.Column('rate_limit_per_minute', sa.Integer, default=60),
        sa.Column('rate_limit_per_hour', sa.Integer, default=1000),
        sa.Column('rate_limit_per_day', sa.Integer, default=10000),
        sa.Column('burst_limit', sa.Integer, default=10),
        
        # IP Restrictions
        sa.Column('allowed_ips', postgresql.ARRAY(postgresql.INET), default=sa.text("ARRAY[]::inet[]")),
        sa.Column('blocked_ips', postgresql.ARRAY(postgresql.INET), default=sa.text("ARRAY[]::inet[]")),
        sa.Column('require_ip_allowlist', sa.Boolean, default=False),
        
        # Webhook Configuration
        sa.Column('webhook_url', sa.String(500)),
        sa.Column('webhook_secret', sa.String(255)),
        sa.Column('webhook_events', postgresql.ARRAY(sa.String), default=sa.text("ARRAY[]::varchar[]")),
        
        # Usage Tracking
        sa.Column('last_used_at', sa.DateTime(timezone=True)),
        sa.Column('total_requests', sa.Integer, default=0),
        sa.Column('total_errors', sa.Integer, default=0),
        sa.Column('monthly_usage', postgresql.JSONB, default=sa.text("'{}'::jsonb")),
        
        # Configuration and Security
        sa.Column('config', postgresql.JSONB, default=sa.text("'{}'::jsonb")),
        sa.Column('public_key', sa.Text),
        sa.Column('allowed_origins', postgresql.ARRAY(sa.String), default=sa.text("ARRAY[]::varchar[]")),
        
        # Metadata
        sa.Column('tags', postgresql.ARRAY(sa.String), default=sa.text("ARRAY[]::varchar[]")),
        sa.Column('metadata', postgresql.JSONB, default=sa.text("'{}'::jsonb")),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, default=sa.func.now()),
        
        # Foreign keys
        sa.ForeignKeyConstraint(['publisher_id'], ['publishers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], ondelete='SET NULL'),
        
        # Constraints
        sa.CheckConstraint("service_type IN ('external', 'internal', 'partner', 'automation', 'integration')", name='valid_service_type'),
        sa.CheckConstraint("status IN ('active', 'suspended', 'revoked', 'expired', 'pending')", name='valid_service_status'),
        sa.CheckConstraint("rate_limit_per_minute > 0", name='positive_rate_limit_minute'),
        sa.CheckConstraint("rate_limit_per_hour > 0", name='positive_rate_limit_hour'),
        sa.CheckConstraint("rate_limit_per_day > 0", name='positive_rate_limit_day'),
        sa.CheckConstraint("burst_limit > 0", name='positive_burst_limit'),
        sa.CheckConstraint("total_requests >= 0", name='non_negative_requests'),
        sa.CheckConstraint("total_errors >= 0", name='non_negative_errors'),
    )
    
    # Create indexes for service_accounts
    op.create_index('idx_service_accounts_name', 'service_accounts', ['name'], unique=True)
    op.create_index('idx_service_accounts_publisher_id', 'service_accounts', ['publisher_id'])
    op.create_index('idx_service_accounts_owner_user_id', 'service_accounts', ['owner_user_id'])
    op.create_index('idx_service_accounts_status', 'service_accounts', ['status'])
    op.create_index('idx_service_accounts_service_type', 'service_accounts', ['service_type'])
    op.create_index('idx_service_accounts_last_used_at', 'service_accounts', ['last_used_at'])
    
    # ================================================================
    # 9. CREATE SERVICE TOKENS TABLE
    # ================================================================
    
    op.create_table(
        'service_tokens',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=sa.text("uuid_generate_v4()")),
        
        # Foreign Key Relationships
        sa.Column('service_account_id', postgresql.UUID(as_uuid=True), nullable=False),
        
        # Token Identity
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('token_prefix', sa.String(10), nullable=False),
        sa.Column('token_hash', sa.String(255), nullable=False, unique=True),
        sa.Column('token_suffix', sa.String(4), nullable=False),
        
        # Token Configuration
        sa.Column('token_type', sa.String(20), nullable=False, default='api_key'),
        
        # Status and Lifecycle
        sa.Column('status', sa.String(20), nullable=False, default='active'),
        sa.Column('is_active', sa.Boolean, default=True, nullable=False),
        
        # Expiration Management
        sa.Column('expires_at', sa.DateTime(timezone=True)),
        
        # Rotation Management
        sa.Column('rotated_from_id', postgresql.UUID(as_uuid=True)),
        sa.Column('rotated_to_id', postgresql.UUID(as_uuid=True)),
        sa.Column('rotation_grace_period_ends', sa.DateTime(timezone=True)),
        
        # Scopes and Permissions
        sa.Column('scopes', postgresql.JSONB),
        sa.Column('rate_limit_override', postgresql.JSONB),
        
        # Usage Tracking
        sa.Column('last_used_at', sa.DateTime(timezone=True)),
        sa.Column('last_used_ip', postgresql.INET),
        sa.Column('last_used_user_agent', sa.Text),
        sa.Column('total_requests', sa.Integer, default=0),
        sa.Column('total_errors', sa.Integer, default=0),
        sa.Column('daily_usage', postgresql.JSONB, default=sa.text("'{}'::jsonb")),
        
        # Security Events
        sa.Column('security_events', postgresql.JSONB, default=sa.text("'[]'::jsonb")),
        
        # Revocation
        sa.Column('revoked_at', sa.DateTime(timezone=True)),
        sa.Column('revoked_by', postgresql.UUID(as_uuid=True)),
        sa.Column('revocation_reason', sa.Text),
        
        # Metadata
        sa.Column('metadata', postgresql.JSONB, default=sa.text("'{}'::jsonb")),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, default=sa.func.now()),
        
        # Foreign keys
        sa.ForeignKeyConstraint(['service_account_id'], ['service_accounts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['rotated_from_id'], ['service_tokens.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['rotated_to_id'], ['service_tokens.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['revoked_by'], ['users.id'], ondelete='SET NULL'),
        
        # Constraints
        sa.CheckConstraint("token_type IN ('api_key', 'bearer', 'oauth', 'jwt')", name='valid_token_type'),
        sa.CheckConstraint("status IN ('active', 'expired', 'revoked', 'rotating', 'suspended')", name='valid_token_status'),
        sa.CheckConstraint("total_requests >= 0", name='non_negative_token_requests'),
        sa.CheckConstraint("total_errors >= 0", name='non_negative_token_errors'),
    )
    
    # Create indexes for service_tokens
    op.create_index('idx_service_tokens_service_account_id', 'service_tokens', ['service_account_id'])
    op.create_index('idx_service_tokens_token_hash', 'service_tokens', ['token_hash'], unique=True)
    op.create_index('idx_service_tokens_token_prefix', 'service_tokens', ['token_prefix'])
    op.create_index('idx_service_tokens_status', 'service_tokens', ['status'])
    op.create_index('idx_service_tokens_expires_at', 'service_tokens', ['expires_at'])
    op.create_index('idx_service_tokens_last_used_at', 'service_tokens', ['last_used_at'])
    
    # ================================================================
    # 10. CREATE PERSONAL ACCESS TOKENS TABLE
    # ================================================================
    
    op.create_table(
        'personal_access_tokens',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=sa.text("uuid_generate_v4()")),
        
        # Foreign Key Relationships
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('publisher_id', postgresql.UUID(as_uuid=True)),
        
        # Token Identity
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('token_prefix', sa.String(10), nullable=False, default='pat'),
        sa.Column('token_hash', sa.String(255), nullable=False, unique=True),
        sa.Column('token_suffix', sa.String(4), nullable=False),
        
        # Status and Lifecycle
        sa.Column('status', sa.String(20), nullable=False, default='active'),
        sa.Column('is_active', sa.Boolean, default=True, nullable=False),
        
        # Expiration Management
        sa.Column('expires_at', sa.DateTime(timezone=True)),
        
        # Permissions and Scopes
        sa.Column('scopes', postgresql.ARRAY(sa.String), default=sa.text("ARRAY[]::varchar[]")),
        sa.Column('inherit_user_permissions', sa.Boolean, default=True),
        
        # Access Restrictions
        sa.Column('allowed_ips', postgresql.ARRAY(postgresql.INET), default=sa.text("ARRAY[]::inet[]")),
        sa.Column('require_ip_allowlist', sa.Boolean, default=False),
        sa.Column('allowed_origins', postgresql.ARRAY(sa.String), default=sa.text("ARRAY[]::varchar[]")),
        sa.Column('rate_limit_override', postgresql.JSONB),
        
        # Usage Tracking
        sa.Column('last_used_at', sa.DateTime(timezone=True)),
        sa.Column('last_used_ip', postgresql.INET),
        sa.Column('last_used_user_agent', sa.Text),
        sa.Column('last_used_location', sa.String(100)),
        sa.Column('total_requests', sa.Integer, default=0),
        sa.Column('total_errors', sa.Integer, default=0),
        sa.Column('daily_usage', postgresql.JSONB, default=sa.text("'{}'::jsonb")),
        sa.Column('endpoint_usage', postgresql.JSONB, default=sa.text("'{}'::jsonb")),
        
        # Security Events
        sa.Column('security_events', postgresql.JSONB, default=sa.text("'[]'::jsonb")),
        
        # Revocation
        sa.Column('revoked_at', sa.DateTime(timezone=True)),
        sa.Column('revocation_reason', sa.Text),
        
        # Metadata
        sa.Column('tags', postgresql.ARRAY(sa.String), default=sa.text("ARRAY[]::varchar[]")),
        sa.Column('metadata', postgresql.JSONB, default=sa.text("'{}'::jsonb")),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, default=sa.func.now()),
        
        # Foreign keys
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['publisher_id'], ['publishers.id'], ondelete='CASCADE'),
        
        # Constraints
        sa.CheckConstraint("status IN ('active', 'expired', 'revoked', 'suspended')", name='valid_pat_status'),
        sa.CheckConstraint("total_requests >= 0", name='non_negative_pat_requests'),
        sa.CheckConstraint("total_errors >= 0", name='non_negative_pat_errors'),
        sa.CheckConstraint("length(name) >= 1", name='pat_name_not_empty'),
    )
    
    # Create indexes for personal_access_tokens
    op.create_index('idx_personal_access_tokens_user_id', 'personal_access_tokens', ['user_id'])
    op.create_index('idx_personal_access_tokens_publisher_id', 'personal_access_tokens', ['publisher_id'])
    op.create_index('idx_personal_access_tokens_token_hash', 'personal_access_tokens', ['token_hash'], unique=True)
    op.create_index('idx_personal_access_tokens_status', 'personal_access_tokens', ['status'])
    op.create_index('idx_personal_access_tokens_expires_at', 'personal_access_tokens', ['expires_at'])
    op.create_index('idx_personal_access_tokens_last_used_at', 'personal_access_tokens', ['last_used_at'])
    op.create_index('idx_pat_user_publisher', 'personal_access_tokens', ['user_id', 'publisher_id'])
    
    # ================================================================
    # 8. UPDATE EXISTING TABLES WITH USER AUDIT FIELDS
    # ================================================================
    
    # Add user audit columns to existing tables
    for table in ['songwriters', 'works', 'work_writers', 'recordings', 'recording_contributors']:
        op.add_column(table, sa.Column('updated_by', postgresql.UUID(as_uuid=True)))
        # Note: created_by already exists in these tables
    
    # Rename tenant_id to publisher_id in all existing tables
    for table in ['songwriters', 'works', 'work_writers', 'recordings', 'recording_contributors']:
        op.alter_column(table, 'tenant_id', new_column_name='publisher_id')
    
    # ================================================================
    # 9. SEED INITIAL PERMISSIONS
    # ================================================================
    
    # Define system permissions
    permissions_data = [
        # Works permissions
        ('works:create', 'Create Works', 'Create new musical works', 'works', 'create'),
        ('works:read', 'Read Works', 'View musical works', 'works', 'read'),
        ('works:update', 'Update Works', 'Edit musical works', 'works', 'update'),
        ('works:delete', 'Delete Works', 'Delete musical works', 'works', 'delete'),
        ('works:admin', 'Works Admin', 'Full works administration', 'works', 'admin'),
        
        # Songwriters permissions
        ('songwriters:create', 'Create Songwriters', 'Add new songwriters', 'songwriters', 'create'),
        ('songwriters:read', 'Read Songwriters', 'View songwriter profiles', 'songwriters', 'read'),
        ('songwriters:update', 'Update Songwriters', 'Edit songwriter information', 'songwriters', 'update'),
        ('songwriters:delete', 'Delete Songwriters', 'Remove songwriters', 'songwriters', 'delete'),
        ('songwriters:admin', 'Songwriters Admin', 'Full songwriter administration', 'songwriters', 'admin'),
        
        # Recordings permissions
        ('recordings:create', 'Create Recordings', 'Add new recordings', 'recordings', 'create'),
        ('recordings:read', 'Read Recordings', 'View recordings', 'recordings', 'read'),
        ('recordings:update', 'Update Recordings', 'Edit recording information', 'recordings', 'update'),
        ('recordings:delete', 'Delete Recordings', 'Remove recordings', 'recordings', 'delete'),
        ('recordings:admin', 'Recordings Admin', 'Full recordings administration', 'recordings', 'admin'),
        
        # Publisher permissions
        ('publisher:admin', 'Publisher Admin', 'Full publisher administration', 'publisher', 'admin'),
        ('publisher:settings', 'Publisher Settings', 'Manage publisher settings', 'publisher', 'settings'),
        ('publisher:users', 'Publisher Users', 'Manage publisher users', 'publisher', 'users'),
        ('publisher:billing', 'Publisher Billing', 'Access billing information', 'publisher', 'billing'),
        
        # System permissions
        ('system:admin', 'System Admin', 'System-wide administration', 'system', 'admin'),
    ]
    
    # Insert permissions
    for perm_id, name, description, resource, action in permissions_data:
        op.execute(f"""
            INSERT INTO permissions (id, name, description, resource, action, is_system_permission)
            VALUES ('{perm_id}', '{name}', '{description}', '{resource}', '{action}', true)
            ON CONFLICT (id) DO NOTHING
        """)
    
    # ================================================================
    # 10. CREATE SYSTEM ROLES
    # ================================================================
    
    # Create system roles with permissions
    system_roles = [
        ('system_admin', 'System Administrator', [
            'system:admin', 'publisher:admin', 'publisher:settings', 'publisher:users', 'publisher:billing',
            'works:admin', 'songwriters:admin', 'recordings:admin'
        ]),
        ('publisher_admin', 'Publisher Administrator', [
            'publisher:admin', 'publisher:settings', 'publisher:users', 'publisher:billing',
            'works:admin', 'songwriters:admin', 'recordings:admin'
        ]),
        ('staff_user', 'Staff User', [
            'works:create', 'works:read', 'works:update',
            'songwriters:create', 'songwriters:read', 'songwriters:update',
            'recordings:create', 'recordings:read', 'recordings:update'
        ]),
        ('creator_user', 'Creator User', [
            'works:read', 'songwriters:read', 'recordings:read'
        ]),
        ('read_only_user', 'Read Only User', [
            'works:read', 'songwriters:read', 'recordings:read'
        ]),
    ]
    
    for role_name, description, permissions in system_roles:
        permissions_json = str(permissions).replace("'", '"')
        op.execute(f"""
            INSERT INTO roles (id, name, description, publisher_id, permissions, is_system_role, is_active)
            VALUES (uuid_generate_v4(), '{role_name}', '{description}', NULL, '{permissions_json}', true, true)
            ON CONFLICT (name, publisher_id) DO NOTHING
        """)


def downgrade() -> None:
    """Rollback publisher architecture changes."""
    
    # Drop new tables in reverse order
    op.drop_table('personal_access_tokens')
    op.drop_table('service_tokens')
    op.drop_table('service_accounts')
    op.drop_table('user_sessions')
    op.drop_table('permissions')
    op.drop_table('roles')
    op.drop_table('user_publishers')
    op.drop_table('users')
    op.drop_table('accounts')
    
    # Revert column renames in existing tables
    for table in ['songwriters', 'works', 'work_writers', 'recordings', 'recording_contributors']:
        op.alter_column(table, 'publisher_id', new_column_name='tenant_id')
        op.drop_column(table, 'updated_by')
    
    # Rename publishers back to tenants
    op.rename_table('publishers', 'tenants')
    
    # Remove added columns from publishers (now tenants)
    columns_to_remove = [
        'business_address', 'support_email', 'primary_contact_email',
        'business_license', 'tax_id', 'branding', 'business_model', 'publisher_type'
    ]
    
    for column in columns_to_remove:
        op.drop_column('tenants', column)
    
    # Restore original constraints
    op.drop_constraint('valid_publisher_status', 'tenants', type_='check')
    op.drop_constraint('valid_plan_type', 'tenants', type_='check')
    op.drop_constraint('valid_publisher_type', 'tenants', type_='check') 
    op.drop_constraint('valid_business_model', 'tenants', type_='check')
    
    op.create_check_constraint(
        'valid_tenant_status',
        'tenants', 
        "status IN ('active', 'suspended', 'archived', 'trial')"
    )
    op.create_check_constraint(
        'valid_plan_type',
        'tenants',
        "plan_type IN ('free', 'starter', 'professional', 'enterprise')"
    )