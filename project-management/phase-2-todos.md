# Phase 2: Permissions & Account Management (Weeks 7-10)

## Overview
Implement granular permission system and comprehensive account/billing management.

---

## Week 7-8: Permission Framework

### Permission Service (`src/services/permission_service.py`)
- [ ] **Core permission operations**
  - [ ] Check user permissions for resources
  - [ ] Validate role-based access
  - [ ] Handle permission inheritance
  - [ ] Support context-based restrictions (departments, catalogs)

- [ ] **Permission resolution**
  - [ ] Resolve effective permissions for user-publisher combination
  - [ ] Handle role hierarchy and permission aggregation
  - [ ] Cache permission resolution for performance
  - [ ] Support dynamic permission checking

- [ ] **Role management**
  - [ ] Create and manage role templates
  - [ ] Assign roles to users per publisher
  - [ ] Validate role compatibility
  - [ ] Handle system vs custom roles

### Permission Middleware (`src/middleware/permission.py`)
- [ ] **Permission enforcement middleware**
  - [ ] Extract user context from JWT
  - [ ] Validate required permissions for endpoints
  - [ ] Handle permission-based filtering
  - [ ] Support permission decorators

- [ ] **Context management**
  - [ ] Set user context in database session
  - [ ] Handle publisher context switching
  - [ ] Manage RLS context variables
  - [ ] Support multi-publisher user scenarios

### Enhanced JWT & Authentication
- [ ] **Update JWT token structure**
  - [ ] Include user ID and publisher context
  - [ ] Add role and permission arrays
  - [ ] Support context restrictions
  - [ ] Handle token refresh with new permissions

- [ ] **Update AuthenticationMiddleware**
  - [ ] Extract enhanced user context
  - [ ] Set permission context for RLS
  - [ ] Handle multi-publisher scenarios
  - [ ] Support permission-based routing

### Permission Models Enhancement
- [ ] **Seed default permissions**
  - [ ] Works permissions (create, read, update, delete, admin)
  - [ ] Songwriter permissions
  - [ ] Recording permissions  
  - [ ] Publisher management permissions
  - [ ] System administration permissions

- [ ] **Create role templates**
  - [ ] System Admin role (cross-publisher)
  - [ ] Publisher Admin role
  - [ ] Department Admin role
  - [ ] Staff User role
  - [ ] Creator User role (Songtrust model)
  - [ ] Read-Only User role

---

## Week 8-9: Account Management Service

### Account Service (`src/services/account_service.py`)
- [ ] **Account lifecycle management**
  - [ ] Create accounts for new publishers
  - [ ] Update subscription plans and billing cycles
  - [ ] Handle plan upgrades/downgrades
  - [ ] Manage account suspension and reactivation

- [ ] **Subscription management**
  - [ ] Plan type validation and enforcement
  - [ ] Seat licensing and usage tracking
  - [ ] Trial period management
  - [ ] Billing cycle handling

- [ ] **Usage tracking**
  - [ ] API call counting and limits
  - [ ] Storage usage monitoring
  - [ ] Feature usage analytics
  - [ ] Export usage reports

- [ ] **Payment integration foundation**
  - [ ] Payment method management (structure only)
  - [ ] Billing address handling
  - [ ] Invoice generation preparation
  - [ ] Payment status tracking

### Account API (`src/api/routes/accounts.py`)
- [ ] **Account management endpoints**
  - [ ] `GET /api/v1/publishers/{id}/account` - Get account details
  - [ ] `PUT /api/v1/publishers/{id}/account/plan` - Change subscription
  - [ ] `GET /api/v1/publishers/{id}/account/usage` - Usage statistics
  - [ ] `PUT /api/v1/publishers/{id}/account/billing` - Update billing info

- [ ] **Usage and analytics endpoints**
  - [ ] `GET /api/v1/publishers/{id}/account/usage/history` - Usage history
  - [ ] `GET /api/v1/publishers/{id}/account/analytics` - Account analytics
  - [ ] `POST /api/v1/publishers/{id}/account/payment-methods` - Add payment method
  - [ ] `DELETE /api/v1/publishers/{id}/account/payment-methods/{id}` - Remove payment method

### Account Schemas (`src/schemas/account.py`)
- [ ] **Request/Response schemas**
  - [ ] AccountResponse
  - [ ] AccountUpdateRequest
  - [ ] PlanChangeRequest
  - [ ] UsageResponse
  - [ ] UsageHistoryResponse
  - [ ] PaymentMethodRequest/Response
  - [ ] BillingAddressRequest/Response

---

## Week 9-10: API Integration & Permission Enforcement

### Update Existing API Endpoints
- [ ] **Works API enhancement** (`src/api/routes/works.py`)
  - [ ] Add permission decorators (@require_permission('works:read'))
  - [ ] Implement user-based filtering for Creator users
  - [ ] Add user context to audit trails
  - [ ] Support department-based restrictions

- [ ] **Songwriters API enhancement** (`src/api/routes/songwriters.py`)
  - [ ] Permission-based access control
  - [ ] User audit trail integration
  - [ ] Creator user content isolation
  - [ ] Department filtering support

- [ ] **Recordings API enhancement** (`src/api/routes/recordings.py`)
  - [ ] Permission enforcement
  - [ ] User context integration
  - [ ] Content ownership validation
  - [ ] Access restriction implementation

### Enhanced RLS Policies
- [ ] **Update existing RLS policies**
  - [ ] Add user-based access rules
  - [ ] Implement role-based filtering
  - [ ] Support creator content isolation
  - [ ] Handle department restrictions

- [ ] **Create new RLS policies**
  - [ ] User-publisher relationship validation
  - [ ] Permission-based resource access
  - [ ] Context-aware data filtering
  - [ ] Cross-publisher access prevention

### Middleware Integration
- [ ] **Update request pipeline**
  - [ ] PublisherContextMiddleware integration
  - [ ] PermissionMiddleware implementation  
  - [ ] Enhanced AuthenticationMiddleware
  - [ ] Audit logging middleware

- [ ] **Database session enhancement**
  - [ ] Set RLS context variables
  - [ ] User and publisher context
  - [ ] Permission context setting
  - [ ] Session-level caching

---

## Week 10: Testing & Validation

### Permission System Testing
- [ ] **Unit tests for permission service**
  - [ ] Permission resolution logic
  - [ ] Role hierarchy validation
  - [ ] Context-based restrictions
  - [ ] Cache performance testing

- [ ] **Integration tests for permission enforcement**
  - [ ] API endpoint permission validation
  - [ ] RLS policy testing with different users
  - [ ] Multi-publisher scenario testing
  - [ ] Permission inheritance testing

### Account Management Testing
- [ ] **Account service testing**
  - [ ] Subscription management workflows
  - [ ] Usage tracking accuracy
  - [ ] Plan upgrade/downgrade scenarios
  - [ ] Billing cycle handling

- [ ] **API endpoint testing**
  - [ ] Account CRUD operations
  - [ ] Usage reporting accuracy
  - [ ] Payment method management
  - [ ] Error handling validation

### Security Testing
- [ ] **Access control validation**
  - [ ] User isolation testing
  - [ ] Permission bypass prevention
  - [ ] Cross-publisher access prevention
  - [ ] Privilege escalation testing

- [ ] **Performance testing**
  - [ ] Permission checking performance
  - [ ] RLS policy performance impact
  - [ ] Cache effectiveness measurement
  - [ ] Multi-user concurrent access

---

## Acceptance Criteria

### Permission System
✅ Granular permissions implemented for all resources
✅ Role-based access control functional
✅ User isolation validated through testing
✅ Permission inheritance working correctly
✅ Performance impact within acceptable limits

### Account Management
✅ Complete subscription lifecycle management
✅ Usage tracking accurate and reliable
✅ Billing information securely managed
✅ Plan changes handled seamlessly
✅ Usage analytics providing valuable insights

### API Integration
✅ All existing endpoints enhanced with permissions
✅ User context properly integrated
✅ Audit trails capturing user actions
✅ Error handling comprehensive and user-friendly
✅ Backward compatibility maintained where possible

### Security & Performance
✅ Security testing passes all scenarios
✅ Performance benchmarks met
✅ Concurrent user access handled properly
✅ Data isolation verified
✅ Permission caching effective

---

## Dependencies & Blockers
- Phase 1 completion (models and basic services)
- JWT token structure changes require client updates
- RLS policy changes need thorough testing
- Performance optimization may require database tuning

---

*Phase 2 Status: Pending Phase 1 Completion*
*Estimated Duration: 4 weeks*
*Priority: High - Core security and billing functionality*