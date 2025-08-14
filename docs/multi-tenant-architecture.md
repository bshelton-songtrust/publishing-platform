# Multi-Tenant Publisher Architecture Design

## Executive Summary

This document outlines the comprehensive architecture design for the Downtown Music Publishing unified platform, focusing on multi-tenant publisher management, user access control, and account administration. The system supports multiple publishing organizations (Downtown Music Publishing, Sheer, Songtrust, Spirit) with complete data isolation and flexible access patterns.

## Table of Contents

1. [Current State Analysis](#current-state-analysis)
2. [Proposed Architecture](#proposed-architecture)
3. [Database Schema Design](#database-schema-design)
4. [Service Architecture](#service-architecture)
5. [Security Framework](#security-framework)
6. [Access Control Patterns](#access-control-patterns)
7. [Active Directory Integration](#active-directory-integration)
8. [Implementation Roadmap](#implementation-roadmap)
9. [API Design](#api-design)
10. [Monitoring and Operations](#monitoring-and-operations)

---

## Current State Analysis

### Existing Implementation

The current system provides a solid foundation with:

**✅ Strengths:**
- Row-Level Security (RLS) implemented at database level
- Tenant-based data isolation via `X-Tenant-ID` headers
- JWT-based authentication framework
- Comprehensive catalog management (works, songwriters, recordings)
- Event-driven architecture with SQS integration

**❌ Gaps Identified:**
- No user management system (users are referenced but not modeled)
- Missing account/billing management
- Limited role-based access control
- No integration with Active Directory
- Tenant management is basic (missing publisher-specific features)

### Current Database Schema

```sql
-- Existing tenant model
CREATE TABLE tenants (
    id UUID PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    subdomain VARCHAR(100) UNIQUE NOT NULL,
    status VARCHAR(20) DEFAULT 'active',
    plan_type VARCHAR(50) DEFAULT 'free',
    settings JSONB DEFAULT '{}',
    additional_data JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

---

## Proposed Architecture

### 1. Publisher-Centric Model

**Rename "Tenant" → "Publisher"** to better reflect the music industry context:
- Downtown Music Publishing (Enterprise)
- Sheer (Professional) 
- Songtrust (Platform - individual creators)
- Spirit (Boutique)

### 2. Multi-Level Access Control

```
Publisher (Organization Level)
├── Accounts (Billing/Subscription)
├── Users (People with Access)
│   ├── Publisher Admins (Full publisher access)
│   ├── Staff Users (Department-specific access)
│   └── Creator Users (Own content only - Songtrust model)
└── Catalogs (Isolated data per publisher)
```

### 3. User Types & Access Patterns

| User Type | Scope | Example Use Case |
|-----------|-------|------------------|
| **System Admin** | Cross-publisher | Internal DMP admin managing all publishers |
| **Publisher Admin** | Single publisher | Sheer admin managing all Sheer catalogs |
| **Department User** | Publisher department | A&R team member accessing specific works |
| **Creator User** | Own content only | Songtrust songwriter managing their works |
| **Read-Only User** | View access | Accounting team viewing royalty data |

---

## Database Schema Design

### 1. Core Identity Tables

```sql
-- Publishers (renamed from tenants)
CREATE TABLE publishers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    subdomain VARCHAR(100) UNIQUE NOT NULL,
    publisher_type VARCHAR(50) NOT NULL, -- 'enterprise', 'professional', 'platform', 'boutique'
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    business_model VARCHAR(50) NOT NULL DEFAULT 'traditional', -- 'traditional', 'platform', 'hybrid'
    
    -- Publisher-specific settings
    settings JSONB DEFAULT '{}',
    branding JSONB DEFAULT '{}', -- logos, colors, etc.
    
    -- Compliance and legal
    tax_id VARCHAR(50),
    business_license VARCHAR(100),
    
    -- Contact information
    primary_contact_email VARCHAR(255),
    support_email VARCHAR(255),
    business_address JSONB,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    CONSTRAINT valid_publisher_type CHECK (publisher_type IN ('enterprise', 'professional', 'platform', 'boutique')),
    CONSTRAINT valid_status CHECK (status IN ('active', 'suspended', 'archived', 'trial')),
    CONSTRAINT valid_business_model CHECK (business_model IN ('traditional', 'platform', 'hybrid'))
);

-- Accounts (billing and subscription management)
CREATE TABLE accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    publisher_id UUID NOT NULL REFERENCES publishers(id) ON DELETE CASCADE,
    account_type VARCHAR(50) NOT NULL DEFAULT 'standard',
    
    -- Subscription details
    plan_type VARCHAR(50) NOT NULL DEFAULT 'free',
    billing_cycle VARCHAR(20) DEFAULT 'monthly', -- 'monthly', 'annual', 'enterprise'
    seats_licensed INTEGER DEFAULT 1,
    seats_used INTEGER DEFAULT 0,
    
    -- Billing information
    billing_email VARCHAR(255),
    billing_address JSONB,
    payment_method JSONB,
    
    -- Account status
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    trial_ends_at TIMESTAMP WITH TIME ZONE,
    next_billing_date TIMESTAMP WITH TIME ZONE,
    
    -- Usage tracking
    monthly_api_calls INTEGER DEFAULT 0,
    storage_used_mb INTEGER DEFAULT 0,
    
    -- Metadata
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    CONSTRAINT valid_account_type CHECK (account_type IN ('standard', 'enterprise', 'platform')),
    CONSTRAINT valid_plan_type CHECK (plan_type IN ('free', 'starter', 'professional', 'enterprise', 'platform')),
    CONSTRAINT valid_billing_cycle CHECK (billing_cycle IN ('monthly', 'annual', 'enterprise')),
    CONSTRAINT valid_account_status CHECK (status IN ('active', 'suspended', 'cancelled', 'trial'))
);

-- Users (people who access the system)
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Identity
    email VARCHAR(255) UNIQUE NOT NULL,
    username VARCHAR(100),
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    full_name VARCHAR(255) GENERATED ALWAYS AS (first_name || ' ' || last_name) STORED,
    
    -- Authentication
    password_hash VARCHAR(255), -- NULL if using external auth (AD)
    is_external_auth BOOLEAN DEFAULT FALSE,
    external_auth_provider VARCHAR(50), -- 'active_directory', 'google', 'azure'
    external_auth_id VARCHAR(255),
    
    -- Profile
    avatar_url VARCHAR(500),
    phone_number VARCHAR(50),
    timezone VARCHAR(50) DEFAULT 'UTC',
    language VARCHAR(10) DEFAULT 'en',
    
    -- Status
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    is_verified BOOLEAN DEFAULT FALSE,
    email_verified_at TIMESTAMP WITH TIME ZONE,
    last_login_at TIMESTAMP WITH TIME ZONE,
    
    -- Security
    failed_login_attempts INTEGER DEFAULT 0,
    locked_until TIMESTAMP WITH TIME ZONE,
    password_changed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    mfa_enabled BOOLEAN DEFAULT FALSE,
    mfa_secret VARCHAR(255),
    
    -- Metadata
    preferences JSONB DEFAULT '{}',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    CONSTRAINT valid_user_status CHECK (status IN ('active', 'inactive', 'suspended', 'archived')),
    CONSTRAINT valid_external_provider CHECK (
        external_auth_provider IS NULL OR 
        external_auth_provider IN ('active_directory', 'google', 'azure', 'okta')
    )
);

-- User-Publisher relationships (many-to-many)
CREATE TABLE user_publishers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    publisher_id UUID NOT NULL REFERENCES publishers(id) ON DELETE CASCADE,
    
    -- Access details
    role VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    
    -- Permissions
    permissions JSONB DEFAULT '[]', -- Array of permission strings
    restrictions JSONB DEFAULT '{}', -- Department, catalog restrictions
    
    -- Metadata
    invited_by UUID REFERENCES users(id),
    invited_at TIMESTAMP WITH TIME ZONE,
    joined_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_accessed_at TIMESTAMP WITH TIME ZONE,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    UNIQUE(user_id, publisher_id),
    
    CONSTRAINT valid_role CHECK (role IN (
        'system_admin', 'publisher_admin', 'department_admin', 
        'staff_user', 'creator_user', 'read_only_user'
    )),
    CONSTRAINT valid_user_publisher_status CHECK (status IN ('active', 'inactive', 'suspended'))
);
```

### 2. Permission System

```sql
-- Roles (predefined role templates)
CREATE TABLE roles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    description TEXT,
    publisher_id UUID REFERENCES publishers(id), -- NULL for system-wide roles
    
    -- Role configuration
    permissions JSONB NOT NULL DEFAULT '[]',
    is_system_role BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    UNIQUE(name, publisher_id)
);

-- Permissions (granular permissions)
CREATE TABLE permissions (
    id VARCHAR(100) PRIMARY KEY, -- e.g., 'works:create', 'songwriters:read'
    name VARCHAR(255) NOT NULL,
    description TEXT,
    resource VARCHAR(100) NOT NULL, -- 'works', 'songwriters', 'recordings'
    action VARCHAR(50) NOT NULL, -- 'create', 'read', 'update', 'delete', 'admin'
    is_system_permission BOOLEAN DEFAULT TRUE,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- User sessions (for tracking active sessions)
CREATE TABLE user_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    publisher_id UUID REFERENCES publishers(id) ON DELETE CASCADE,
    
    -- Session details
    session_token_hash VARCHAR(255) NOT NULL,
    refresh_token_hash VARCHAR(255),
    
    -- Context
    ip_address INET,
    user_agent TEXT,
    
    -- Timing
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    last_activity_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### 3. Update Existing Tables

```sql
-- Add user tracking to existing tables
ALTER TABLE songwriters 
ADD COLUMN created_by UUID REFERENCES users(id),
ADD COLUMN updated_by UUID REFERENCES users(id);

ALTER TABLE works 
ADD COLUMN created_by UUID REFERENCES users(id),
ADD COLUMN updated_by UUID REFERENCES users(id);

ALTER TABLE recordings 
ADD COLUMN created_by UUID REFERENCES users(id),
ADD COLUMN updated_by UUID REFERENCES users(id);

-- Rename tenant_id to publisher_id in all tables
ALTER TABLE songwriters RENAME COLUMN tenant_id TO publisher_id;
ALTER TABLE works RENAME COLUMN tenant_id TO publisher_id;
ALTER TABLE work_writers RENAME COLUMN tenant_id TO publisher_id;
ALTER TABLE recordings RENAME COLUMN tenant_id TO publisher_id;
ALTER TABLE recording_contributors RENAME COLUMN tenant_id TO publisher_id;
```

---

## Service Architecture

### 1. Publisher Management Service

**Responsibilities:**
- Publisher lifecycle management (create, update, archive)
- Publisher settings and configuration
- Subdomain management
- Publisher-specific business rules

**Key Endpoints:**
```python
POST /api/v1/publishers                    # Create new publisher
GET /api/v1/publishers/{id}               # Get publisher details
PUT /api/v1/publishers/{id}               # Update publisher
DELETE /api/v1/publishers/{id}            # Archive publisher
GET /api/v1/publishers/{id}/settings      # Get publisher settings
PUT /api/v1/publishers/{id}/settings      # Update publisher settings
```

### 2. User Management Service

**Responsibilities:**
- User lifecycle management
- Authentication and authorization
- User-publisher relationships
- Profile management

**Key Endpoints:**
```python
POST /api/v1/users                        # Create user
GET /api/v1/users/me                      # Get current user profile
PUT /api/v1/users/{id}                    # Update user
POST /api/v1/users/{id}/publishers        # Add user to publisher
DELETE /api/v1/users/{id}/publishers/{pub_id}  # Remove user from publisher
GET /api/v1/publishers/{id}/users         # List publisher users
```

### 3. Account Management Service

**Responsibilities:**
- Billing and subscription management
- Plan upgrades/downgrades
- Usage tracking and limits
- Payment processing integration

**Key Endpoints:**
```python
GET /api/v1/publishers/{id}/account       # Get account details
PUT /api/v1/publishers/{id}/account/plan  # Change subscription plan
GET /api/v1/publishers/{id}/account/usage # Get usage statistics
POST /api/v1/publishers/{id}/account/payment-methods  # Add payment method
```

### 4. Enhanced Catalog Service

**Updated to support new user model:**
- User-level audit trails
- Permission-based access control
- Enhanced RLS policies

---

## Security Framework

### 1. Enhanced Row-Level Security

```sql
-- Publisher isolation (updated from tenant)
CREATE POLICY publisher_isolation_policy ON publishers
FOR ALL TO catalog_service_role
USING (id::text = current_setting('app.current_publisher_id', true))
WITH CHECK (id::text = current_setting('app.current_publisher_id', true));

-- User-based access policies
CREATE POLICY user_access_policy ON works
FOR ALL TO catalog_service_role
USING (
    publisher_id::text = current_setting('app.current_publisher_id', true)
    AND (
        -- Publisher admin can access all
        current_setting('app.current_user_role', true) = 'publisher_admin'
        OR
        -- Creator can only access their own works
        (current_setting('app.current_user_role', true) = 'creator_user'
         AND created_by::text = current_setting('app.current_user_id', true))
        OR
        -- Staff can access based on permissions
        current_setting('app.user_has_permission', true) = 'works:read'
    )
);

-- Similar policies for songwriters and recordings...
```

### 2. Permission-Based Access Control

```python
# Example permission definitions
PERMISSIONS = {
    # Works management
    'works:create': 'Create new musical works',
    'works:read': 'View musical works',
    'works:update': 'Edit musical works',
    'works:delete': 'Delete musical works',
    'works:admin': 'Full works administration',
    
    # Songwriter management
    'songwriters:create': 'Add new songwriters',
    'songwriters:read': 'View songwriter profiles',
    'songwriters:update': 'Edit songwriter information',
    'songwriters:delete': 'Remove songwriters',
    
    # Publisher management
    'publisher:admin': 'Full publisher administration',
    'publisher:settings': 'Manage publisher settings',
    'publisher:users': 'Manage publisher users',
    'publisher:billing': 'Access billing information',
    
    # System administration
    'system:admin': 'System-wide administration',
}

# Role templates
ROLE_TEMPLATES = {
    'publisher_admin': [
        'works:admin', 'songwriters:admin', 'recordings:admin',
        'publisher:admin', 'publisher:settings', 'publisher:users'
    ],
    'staff_user': [
        'works:create', 'works:read', 'works:update',
        'songwriters:create', 'songwriters:read', 'songwriters:update',
        'recordings:create', 'recordings:read', 'recordings:update'
    ],
    'creator_user': [
        'works:read', 'songwriters:read', 'recordings:read'
    ],
    'read_only_user': [
        'works:read', 'songwriters:read', 'recordings:read'
    ]
}
```

### 3. Multi-Context Authentication

```python
# Enhanced JWT token payload
{
    "sub": "user-uuid",
    "email": "user@publisher.com",
    "role": "publisher_admin",
    "publisher_id": "publisher-uuid",
    "permissions": ["works:admin", "songwriters:admin"],
    "restrictions": {
        "departments": ["A&R", "Publishing"],
        "catalogs": ["catalog-1", "catalog-2"]
    },
    "exp": 1234567890
}
```

---

## Access Control Patterns

### 1. Publisher Types & Access Models

**Enterprise (Downtown Music Publishing, Sheer)**
```
Publisher Admin → Full Access to All Publisher Data
Department Admin → Access to Department-Specific Data
Staff User → Role-Based Access Within Department
```

**Platform (Songtrust)**
```
Platform Admin → Administrative Access
Creator User → Access Only to Own Created Content
Support User → Read-Only Access for Support
```

### 2. Data Isolation Strategies

| Publisher Type | Isolation Level | Access Pattern |
|----------------|-----------------|----------------|
| Enterprise | Publisher-Level | Hierarchical roles with departments |
| Platform | User-Level | Creator owns their content |
| Boutique | Publisher-Level | Small team, shared access |

### 3. Permission Inheritance

```
System Admin (Cross-Publisher)
├── Publisher Admin (All Publisher Data)
│   ├── Department Admin (Department Data)
│   │   └── Staff User (Role-Based Access)
│   └── Creator User (Own Content Only)
└── Read-Only User (View Access Only)
```

---

## Active Directory Integration

### 1. Authentication Flow

```python
# Active Directory authentication middleware
class ActiveDirectoryAuthMiddleware:
    async def authenticate_user(self, token: str) -> User:
        # 1. Validate AD token
        ad_user = await self.validate_ad_token(token)
        
        # 2. Find or create user
        user = await self.find_or_create_user(ad_user)
        
        # 3. Sync user attributes
        await self.sync_user_attributes(user, ad_user)
        
        # 4. Determine publisher access
        publisher_access = await self.get_publisher_access(user, ad_user)
        
        return user, publisher_access
```

### 2. User Provisioning

```python
# AD user mapping
AD_USER_MAPPING = {
    'email': 'userPrincipalName',
    'first_name': 'givenName',
    'last_name': 'sn',
    'department': 'department',
    'title': 'title',
    'manager': 'manager',
}

# Publisher assignment rules
PUBLISHER_ASSIGNMENT_RULES = {
    'downtownmusic.com': 'downtown-music-publishing',
    'sheermusic.com': 'sheer',
    'songtrust.com': 'songtrust',
    'spiritmusic.com': 'spirit',
}

# Role assignment based on AD groups
AD_ROLE_MAPPING = {
    'DMP-Admin': 'system_admin',
    'Publisher-Admin-{publisher}': 'publisher_admin',
    'A&R-{publisher}': 'staff_user',
    'Finance-{publisher}': 'read_only_user',
}
```

### 3. Hybrid Authentication

```python
# Support both internal and AD users
class HybridAuthService:
    async def authenticate(self, credentials) -> UserContext:
        if credentials.provider == 'active_directory':
            return await self.authenticate_ad_user(credentials.token)
        elif credentials.provider == 'internal':
            return await self.authenticate_internal_user(
                credentials.email, 
                credentials.password
            )
        else:
            raise UnsupportedAuthProvider()
```

---

## Implementation Roadmap

### Phase 1: Core User & Account Models (4-6 weeks)

**Week 1-2: Database Schema**
- [ ] Create new tables: `publishers`, `accounts`, `users`, `user_publishers`
- [ ] Migration scripts to rename `tenants` → `publishers`
- [ ] Update existing tables with user references
- [ ] Enhanced RLS policies

**Week 3-4: User Management Service**
- [ ] User CRUD operations
- [ ] User-publisher relationship management
- [ ] Basic authentication updates
- [ ] Password management

**Week 5-6: Account Management**
- [ ] Account lifecycle management
- [ ] Subscription plan management
- [ ] Usage tracking framework
- [ ] Basic billing integration

### Phase 2: Enhanced Permissions (3-4 weeks)

**Week 1-2: Permission Framework**
- [ ] Permission and role tables
- [ ] Permission checking middleware
- [ ] Role-based access control
- [ ] Enhanced JWT tokens with permissions

**Week 3-4: Access Control Implementation**
- [ ] Update all API endpoints with permission checks
- [ ] Implement user-level data filtering
- [ ] Enhanced RLS policies for user isolation
- [ ] API documentation updates

### Phase 3: Active Directory Integration (3-4 weeks)

**Week 1-2: AD Authentication**
- [ ] AD authentication middleware
- [ ] User provisioning from AD
- [ ] Hybrid authentication support
- [ ] AD user attribute synchronization

**Week 3-4: Advanced AD Features**
- [ ] Group-based role assignment
- [ ] Automated publisher assignment
- [ ] AD group synchronization
- [ ] Single sign-on (SSO) implementation

### Phase 4: Advanced Features (4-6 weeks)

**Week 1-2: Advanced User Management**
- [ ] User invitation system
- [ ] Multi-factor authentication
- [ ] Session management
- [ ] User activity tracking

**Week 3-4: Publisher Enhancement**
- [ ] Publisher-specific settings
- [ ] Custom branding support
- [ ] Department management
- [ ] Usage analytics

**Week 5-6: Monitoring & Operations**
- [ ] Enhanced audit logging
- [ ] User access reporting
- [ ] Security monitoring
- [ ] Performance optimization

---

## API Design

### 1. Authentication Endpoints

```python
# User authentication
POST /api/v1/auth/login
POST /api/v1/auth/logout
POST /api/v1/auth/refresh
POST /api/v1/auth/forgot-password
POST /api/v1/auth/reset-password

# Active Directory
POST /api/v1/auth/ad/login
GET /api/v1/auth/ad/callback
```

### 2. User Management

```python
# User operations
GET /api/v1/users/me
PUT /api/v1/users/me
POST /api/v1/users
GET /api/v1/users/{id}
PUT /api/v1/users/{id}
DELETE /api/v1/users/{id}

# User-Publisher relationships
GET /api/v1/users/{id}/publishers
POST /api/v1/users/{id}/publishers
PUT /api/v1/users/{id}/publishers/{publisher_id}
DELETE /api/v1/users/{id}/publishers/{publisher_id}
```

### 3. Publisher Management

```python
# Publisher operations
GET /api/v1/publishers
POST /api/v1/publishers
GET /api/v1/publishers/{id}
PUT /api/v1/publishers/{id}
DELETE /api/v1/publishers/{id}

# Publisher users
GET /api/v1/publishers/{id}/users
POST /api/v1/publishers/{id}/users/invite
PUT /api/v1/publishers/{id}/users/{user_id}/role
DELETE /api/v1/publishers/{id}/users/{user_id}

# Publisher settings
GET /api/v1/publishers/{id}/settings
PUT /api/v1/publishers/{id}/settings
```

### 4. Enhanced Headers

```python
# Required headers for all requests
Authorization: Bearer <jwt-token>
X-Publisher-ID: <publisher-uuid>

# Optional context headers
X-User-Role: <current-role>
X-Department: <department-name>
X-Request-ID: <unique-request-id>
```

---

## Monitoring and Operations

### 1. Audit Logging

```python
# Enhanced audit log structure
{
    "timestamp": "2024-01-15T10:30:00Z",
    "event_type": "work_created",
    "user_id": "user-uuid",
    "publisher_id": "publisher-uuid",
    "resource_id": "work-uuid",
    "resource_type": "work",
    "action": "create",
    "changes": {
        "title": {"old": null, "new": "Yesterday"},
        "genre": {"old": null, "new": "Pop"}
    },
    "ip_address": "192.168.1.100",
    "user_agent": "Mozilla/5.0...",
    "session_id": "session-uuid"
}
```

### 2. Security Monitoring

```python
# Security events to monitor
SECURITY_EVENTS = [
    'failed_login_attempt',
    'account_locked',
    'permission_denied',
    'suspicious_activity',
    'privilege_escalation',
    'cross_publisher_access_attempt',
    'bulk_data_access',
    'after_hours_access'
]
```

### 3. Usage Analytics

```python
# Publisher usage metrics
{
    "publisher_id": "publisher-uuid",
    "period": "2024-01",
    "metrics": {
        "active_users": 15,
        "api_calls": 25000,
        "storage_used_mb": 1024,
        "works_created": 50,
        "works_updated": 125,
        "songwriters_added": 5
    }
}
```

---

## Conclusion

This architecture provides a comprehensive foundation for multi-tenant publisher management with:

1. **Flexible Publisher Models**: Support for different business models (enterprise, platform, boutique)
2. **Granular Access Control**: Role-based permissions with user-level isolation
3. **Active Directory Integration**: Seamless enterprise authentication
4. **Scalable User Management**: Support for thousands of users across multiple publishers
5. **Audit and Compliance**: Complete audit trails and security monitoring
6. **Future-Proof Design**: Extensible architecture for additional publishers and features

The system maintains complete data isolation while enabling flexible access patterns suitable for different types of music publishing organizations, from large enterprises like Downtown Music Publishing to creator platforms like Songtrust.

---

## Next Steps

1. **Review and Approve**: Stakeholder review of the proposed architecture
2. **Technical Planning**: Detailed implementation planning with engineering team
3. **Pilot Implementation**: Start with Phase 1 implementation on a test publisher
4. **Migration Planning**: Strategy for migrating existing data to new schema
5. **Active Directory Planning**: Coordination with IT team for AD integration requirements

---

*Document Version: 1.0*  
*Last Updated: 2024-01-15*  
*Author: Downtown Music Publishing Engineering Team*