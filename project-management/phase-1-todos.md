# Phase 1: Core Models & Database Schema (Weeks 1-6)

## Overview
Establish the foundational data model and services for multi-tenant publisher management.

---

## Week 1-2: Database Schema & Migration

### Database Migration Tasks
- [ ] **Create migration script** - `003_publisher_architecture.py`
  - [ ] Rename `tenants` table to `publishers`
  - [ ] Add publisher-specific columns (publisher_type, business_model, etc.)
  - [ ] Create `accounts` table with billing information
  - [ ] Create `users` table with identity and authentication
  - [ ] Create `user_publishers` table for many-to-many relationships
  - [ ] Create `roles` table for role templates
  - [ ] Create `permissions` table for granular permissions
  - [ ] Create `user_sessions` table for session management
  - [ ] Add user audit columns to existing tables (`created_by`, `updated_by`)
  - [ ] Update foreign key references from `tenant_id` to `publisher_id`
  
### Enhanced RLS Policies
- [ ] **Update existing RLS policies** for new publisher model
- [ ] **Create user-based RLS policies** for granular access control
- [ ] **Test RLS policies** with different user roles and scenarios
- [ ] **Document RLS strategy** for future reference

---

## Week 3-4: Core Models

### Publisher Model (`src/models/publisher.py`)
- [ ] **Create Publisher model** (enhanced from Tenant)
  - [ ] Publisher types: enterprise, professional, platform, boutique  
  - [ ] Business models: traditional, platform, hybrid
  - [ ] Publisher-specific settings and branding
  - [ ] Contact information and business details
  - [ ] Status management (active, suspended, trial, archived)

### User Models
- [ ] **Create User model** (`src/models/user.py`)
  - [ ] Identity fields (email, names, username)
  - [ ] Authentication (password_hash, external_auth support)
  - [ ] Profile (avatar, phone, timezone, language)
  - [ ] Status and verification fields
  - [ ] Security (MFA, failed attempts, lockout)
  - [ ] Preferences and metadata

- [ ] **Create UserPublisher model** (`src/models/user_publisher.py`)
  - [ ] Many-to-many relationship between users and publishers
  - [ ] Role assignment per publisher
  - [ ] Permissions and restrictions per relationship
  - [ ] Status and audit fields

### Account Model (`src/models/account.py`)
- [ ] **Create Account model** for billing/subscriptions
  - [ ] Subscription details (plan_type, billing_cycle)
  - [ ] Seat licensing and usage
  - [ ] Billing information and payment methods
  - [ ] Status and trial management
  - [ ] Usage tracking (API calls, storage)

### Permission Models
- [ ] **Create Permission model** (`src/models/permission.py`)
  - [ ] Permission ID (e.g., 'works:create', 'songwriters:read')
  - [ ] Resource and action breakdown
  - [ ] System vs custom permissions

- [ ] **Create Role model** (`src/models/role.py`)
  - [ ] Role templates with permission arrays
  - [ ] System vs publisher-specific roles
  - [ ] Role hierarchy and inheritance

- [ ] **Create UserSession model** (`src/models/user_session.py`)
  - [ ] Session token management
  - [ ] IP address and user agent tracking
  - [ ] Expiration and activity tracking

### Model Updates
- [ ] **Update BaseModel** (`src/models/base.py`)
  - [ ] Rename `tenant_id` to `publisher_id`
  - [ ] Add proper user audit fields
  - [ ] Update relationships and foreign keys

- [ ] **Update existing models** (Work, Songwriter, Recording)
  - [ ] Update foreign key references
  - [ ] Add user audit fields
  - [ ] Update table constraints

---

## Week 3-4: Publisher Service Layer

### Publisher Service (`src/services/publisher_service.py`)
- [ ] **Publisher CRUD operations**
  - [ ] Create new publishers with proper validation
  - [ ] Get publisher details and settings
  - [ ] Update publisher information and branding
  - [ ] Archive/suspend publishers
  - [ ] Publisher status management

- [ ] **Publisher settings management**
  - [ ] Manage publisher-specific configuration
  - [ ] Handle branding customization
  - [ ] Business model validation
  - [ ] Contact information management

- [ ] **Publisher user management**
  - [ ] List users for a publisher
  - [ ] Manage user-publisher relationships
  - [ ] Role assignment and permissions
  - [ ] User invitation workflow

### Publisher API (`src/api/routes/publishers.py`)
- [ ] **Core publisher endpoints**
  - [ ] `POST /api/v1/publishers` - Create publisher
  - [ ] `GET /api/v1/publishers/{id}` - Get publisher details
  - [ ] `PUT /api/v1/publishers/{id}` - Update publisher
  - [ ] `DELETE /api/v1/publishers/{id}` - Archive publisher
  - [ ] `GET /api/v1/publishers` - List publishers (admin only)

- [ ] **Publisher settings endpoints**
  - [ ] `GET /api/v1/publishers/{id}/settings` - Get settings
  - [ ] `PUT /api/v1/publishers/{id}/settings` - Update settings
  - [ ] `GET /api/v1/publishers/{id}/users` - List users
  - [ ] `POST /api/v1/publishers/{id}/users/invite` - Invite user

### Publisher Schemas (`src/schemas/publisher.py`)
- [ ] **Request/Response schemas**
  - [ ] PublisherCreateRequest
  - [ ] PublisherUpdateRequest  
  - [ ] PublisherResponse
  - [ ] PublisherCollectionResponse
  - [ ] PublisherSettingsRequest/Response
  - [ ] PublisherUserInviteRequest

---

## Week 5-6: User Management Service

### User Service (`src/services/user_service.py`) 
- [ ] **User CRUD operations**
  - [ ] Create users with validation
  - [ ] Get user profile and details
  - [ ] Update user information
  - [ ] Soft delete/archive users
  - [ ] User status management

- [ ] **Authentication operations**
  - [ ] Password management (hash, verify, reset)
  - [ ] Email verification workflow
  - [ ] MFA setup and validation
  - [ ] Account lockout management

- [ ] **User-Publisher relationship management**
  - [ ] Add user to publisher with role
  - [ ] Remove user from publisher
  - [ ] Update user role and permissions
  - [ ] List user's publishers and roles

### User API (`src/api/routes/users.py`)
- [ ] **User profile endpoints**
  - [ ] `GET /api/v1/users/me` - Get current user profile
  - [ ] `PUT /api/v1/users/me` - Update current user
  - [ ] `GET /api/v1/users/{id}` - Get user details (admin)
  - [ ] `POST /api/v1/users` - Create user (admin)

- [ ] **User-Publisher relationship endpoints**  
  - [ ] `GET /api/v1/users/{id}/publishers` - List user publishers
  - [ ] `POST /api/v1/users/{id}/publishers` - Add to publisher
  - [ ] `PUT /api/v1/users/{id}/publishers/{pub_id}` - Update role
  - [ ] `DELETE /api/v1/users/{id}/publishers/{pub_id}` - Remove from publisher

### User Schemas (`src/schemas/user.py`)
- [ ] **Request/Response schemas**
  - [ ] UserCreateRequest
  - [ ] UserUpdateRequest
  - [ ] UserResponse
  - [ ] UserCollectionResponse
  - [ ] UserPublisherRequest
  - [ ] UserPublisherResponse
  - [ ] PasswordChangeRequest
  - [ ] EmailVerificationRequest

---

## Week 6: Integration & Testing

### Service Integration
- [ ] **Update existing services** to use new models
  - [ ] Update work service to use publisher_id
  - [ ] Update songwriter service for new relationships
  - [ ] Update recording service for user audit

### Middleware Updates  
- [ ] **Update TenantContextMiddleware** → PublisherContextMiddleware
  - [ ] Change header from X-Tenant-ID to X-Publisher-ID
  - [ ] Maintain backward compatibility
  - [ ] Enhanced context with user information

- [ ] **Update AuthenticationMiddleware**
  - [ ] Enhanced user context in request state
  - [ ] Support for user-publisher relationships
  - [ ] Role and permission extraction from JWT

### Testing
- [ ] **Unit tests for all new models**
- [ ] **Integration tests for new services**
- [ ] **API endpoint tests**
- [ ] **Migration testing with sample data**
- [ ] **RLS policy validation**

---

## Acceptance Criteria

### Database & Models
✅ All new tables created with proper constraints and indexes
✅ Existing data migrated from tenants to publishers  
✅ RLS policies updated and tested
✅ Models follow established patterns and conventions

### Services & APIs
✅ Publisher service handles all publisher lifecycle operations
✅ User service manages users and publisher relationships  
✅ APIs follow established REST conventions
✅ Proper error handling and validation

### Integration  
✅ Existing catalog services work with new models
✅ Backward compatibility maintained where possible
✅ Comprehensive test coverage (>90%)
✅ Documentation updated

---

## Dependencies & Blockers
- Database migration must be tested thoroughly
- RLS policy changes require careful validation
- User authentication integration needs coordination
- Existing API client compatibility considerations

---

*Phase 1 Status: Ready to Begin*
*Estimated Duration: 6 weeks*
*Priority: High - Foundation for all subsequent phases*