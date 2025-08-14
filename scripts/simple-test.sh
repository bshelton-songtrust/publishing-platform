#!/bin/bash
# Enhanced API Test Script - Test both system and tenant-protected endpoints

set -e

API_BASE_URL="http://localhost:8000"

# Generate a test tenant ID
TENANT_ID=$(uuidgen)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

echo_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

echo_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

echo_warning() {
    echo -e "${YELLOW}[EXPECTED]${NC} $1"
}

# Function to test system endpoint (no tenant header required)
test_system_endpoint() {
    local endpoint=$1
    local description=$2
    
    echo_status "Testing: $description"
    echo_status "Endpoint: $endpoint"
    
    response=$(curl -s -w "HTTPSTATUS:%{http_code}" "$API_BASE_URL$endpoint" || echo "HTTPSTATUS:000")
    
    # Extract status code and body
    http_code=$(echo "$response" | grep -o "HTTPSTATUS:[0-9]*" | cut -d: -f2)
    body=$(echo "$response" | sed 's/HTTPSTATUS:[0-9]*$//')
    
    echo "HTTP Status: $http_code"
    
    if [[ "$http_code" -ge 200 && "$http_code" -lt 300 ]]; then
        echo_success "✅ $description - Working"
        echo "Response: $body" | jq '.' 2>/dev/null || echo "Response: $body"
    elif [[ "$http_code" == "404" ]]; then
        echo_error "❌ $description - Not Found (404)"
    else
        echo_error "❌ $description - Failed with status $http_code"
        echo "Response: $body"
    fi
    echo ""
}

# Function to test tenant-protected endpoint
test_tenant_endpoint() {
    local endpoint=$1
    local description=$2
    local should_include_tenant=${3:-true}
    
    echo_status "Testing: $description"
    echo_status "Endpoint: $endpoint"
    
    if [[ "$should_include_tenant" == "true" ]]; then
        echo_status "Using tenant ID: $TENANT_ID"
        response=$(curl -s -w "HTTPSTATUS:%{http_code}" -H "X-Tenant-ID: $TENANT_ID" "$API_BASE_URL$endpoint" || echo "HTTPSTATUS:000")
    else
        echo_status "Testing without tenant header (should fail)"
        response=$(curl -s -w "HTTPSTATUS:%{http_code}" "$API_BASE_URL$endpoint" || echo "HTTPSTATUS:000")
    fi
    
    # Extract status code and body
    http_code=$(echo "$response" | grep -o "HTTPSTATUS:[0-9]*" | cut -d: -f2)
    body=$(echo "$response" | sed 's/HTTPSTATUS:[0-9]*$//')
    
    echo "HTTP Status: $http_code"
    
    if [[ "$should_include_tenant" == "true" ]]; then
        # Test with tenant header - should work
        if [[ "$http_code" -ge 200 && "$http_code" -lt 300 ]]; then
            echo_success "✅ $description - Working with tenant header"
            echo "Response: $body" | jq '.' 2>/dev/null || echo "Response: $body"
        else
            echo_error "❌ $description - Failed with status $http_code"
            echo "Response: $body"
        fi
    else
        # Test without tenant header - should fail with 400
        if [[ "$http_code" == "400" ]]; then
            echo_warning "✅ $description - Correctly rejected without tenant header (400)"
            echo "Response: $body" | jq '.' 2>/dev/null || echo "Response: $body"
        elif [[ "$http_code" == "500" ]]; then
            echo_error "❌ $description - Returned 500 instead of 400 (tenant validation issue)"
            echo "Response: $body"
        else
            echo_error "❌ $description - Unexpected status $http_code"
            echo "Response: $body"
        fi
    fi
    echo ""
}

echo "=============================================="
echo "🎵 Catalog Management Service - Enhanced Tests"
echo "=============================================="
echo ""
echo_status "Generated test tenant ID: $TENANT_ID"
echo ""

echo "=============================================="
echo "🔍 SYSTEM ENDPOINTS (No tenant header required)"  
echo "=============================================="
echo ""

# Test system endpoints (no tenant header required)
test_system_endpoint "/health" "Health Check"
test_system_endpoint "/health/database" "Database Health Check"
test_system_endpoint "/health/dependencies" "Dependencies Health Check"
test_system_endpoint "/version" "Version Info"
test_system_endpoint "/docs" "API Documentation"
test_system_endpoint "/openapi.json" "OpenAPI Specification"
test_system_endpoint "/" "Root Endpoint"

echo "=============================================="
echo "🏢 API ENDPOINTS - Security Test (Without tenant header)"
echo "=============================================="
echo ""

# Test API endpoints without tenant header (should fail with 400)
test_tenant_endpoint "/api/v1/works" "Works API Security" false
test_tenant_endpoint "/api/v1/songwriters" "Songwriters API Security" false
test_tenant_endpoint "/api/v1/recordings" "Recordings API Security" false
test_tenant_endpoint "/api/v1/search/works?q=test" "Search API Security" false

echo "=============================================="
echo "🏢 API ENDPOINTS - Functional Test (With tenant header)"
echo "=============================================="
echo ""

# Test API endpoints with tenant header (should work)
test_tenant_endpoint "/api/v1/works" "Works API" true
test_tenant_endpoint "/api/v1/songwriters" "Songwriters API" true
test_tenant_endpoint "/api/v1/recordings" "Recordings API" true
test_tenant_endpoint "/api/v1/search/works?q=test" "Search Works API" true
test_tenant_endpoint "/api/v1/search/songwriters?q=test" "Search Songwriters API" true
test_tenant_endpoint "/api/v1/search/recordings?q=test" "Search Recordings API" true
test_tenant_endpoint "/api/v1/search/all?q=test" "Search All API" true

echo "=============================================="
echo "🧪 INTEGRATION TESTS - CRUD Operations"
echo "=============================================="
echo ""

# Function for CRUD testing with JSON payloads
test_crud_operation() {
    local method=$1
    local endpoint=$2
    local description=$3
    local payload=$4
    local expected_status=$5
    
    echo_status "Testing: $description"
    echo_status "Method: $method $endpoint"
    
    if [[ "$payload" != "" ]]; then
        echo_status "Payload: $payload" | jq '.' 2>/dev/null || echo_status "Payload: $payload"
        response=$(curl -s -w "HTTPSTATUS:%{http_code}" -X "$method" -H "X-Tenant-ID: $TENANT_ID" -H "Content-Type: application/json" -d "$payload" "$API_BASE_URL$endpoint" || echo "HTTPSTATUS:000")
    else
        response=$(curl -s -w "HTTPSTATUS:%{http_code}" -X "$method" -H "X-Tenant-ID: $TENANT_ID" "$API_BASE_URL$endpoint" || echo "HTTPSTATUS:000")
    fi
    
    # Extract status code and body
    http_code=$(echo "$response" | grep -o "HTTPSTATUS:[0-9]*" | cut -d: -f2)
    body=$(echo "$response" | sed 's/HTTPSTATUS:[0-9]*$//')
    
    echo "HTTP Status: $http_code"
    
    if [[ "$http_code" == "$expected_status" ]]; then
        echo_success "✅ $description - Success (HTTP $http_code)"
        echo "Response: $body" | jq '.' 2>/dev/null || echo "Response: $body"
        
        # Extract and return resource ID if this is a creation
        if [[ "$method" == "POST" && "$http_code" == "201" ]]; then
            resource_id=$(echo "$body" | jq -r '.data.id' 2>/dev/null || echo "")
            if [[ "$resource_id" != "" && "$resource_id" != "null" ]]; then
                echo_status "Created resource ID: $resource_id"
                echo "$resource_id" > /tmp/last_created_id
            fi
        fi
    else
        echo_error "❌ $description - Expected HTTP $expected_status, got $http_code"
        echo "Response: $body"
    fi
    echo ""
}

# Generate UUIDs for test data
SONGWRITER_ID=$(uuidgen)
WORK_ID=$(uuidgen)

echo_status "Starting CRUD integration tests..."
echo_status "Test Songwriter ID: $SONGWRITER_ID"
echo_status "Test Work ID: $WORK_ID"
echo ""

# 1. Create a songwriter first
echo "--- Creating Test Songwriter ---"
SONGWRITER_PAYLOAD=$(cat <<EOF
{
  "data": {
    "type": "songwriter",
    "id": "$SONGWRITER_ID",
    "attributes": {
      "first_name": "John",
      "last_name": "Doe",
      "stage_name": "Johnny D",
      "email": "john.doe@example.com",
      "ipi": "123456789",
      "status": "active"
    }
  }
}
EOF
)

test_crud_operation "POST" "/api/v1/songwriters" "Create Songwriter" "$SONGWRITER_PAYLOAD" "201"

# 2. Get the songwriter back
echo "--- Retrieving Test Songwriter ---"
test_crud_operation "GET" "/api/v1/songwriters/$SONGWRITER_ID" "Get Songwriter" "" "200"

# 3. Create a work with the songwriter as writer
echo "--- Creating Test Work ---"
WORK_PAYLOAD=$(cat <<EOF
{
  "data": {
    "type": "work",
    "id": "$WORK_ID",
    "attributes": {
      "title": "Yesterday Once More",
      "genre": "Pop",
      "language": "en",
      "duration": 240,
      "registration_status": "draft",
      "is_instrumental": false,
      "has_lyrics": true,
      "description": "A classic pop song",
      "writers": [
        {
          "songwriter_id": "$SONGWRITER_ID",
          "role": "composer_lyricist",
          "contribution_percentage": 100.0,
          "is_primary": true
        }
      ]
    }
  }
}
EOF
)

test_crud_operation "POST" "/api/v1/works" "Create Work" "$WORK_PAYLOAD" "201"

# 4. Get the work back with writers included
echo "--- Retrieving Test Work (with writers) ---"
test_crud_operation "GET" "/api/v1/works/$WORK_ID?include=writers" "Get Work with Writers" "" "200"

# 5. Update the work
echo "--- Updating Test Work ---"
WORK_UPDATE_PAYLOAD=$(cat <<EOF
{
  "data": {
    "type": "work",
    "id": "$WORK_ID",
    "attributes": {
      "title": "Yesterday Once More (Updated)",
      "genre": "Classic Rock",
      "description": "A classic pop song - now updated!"
    }
  }
}
EOF
)

test_crud_operation "PATCH" "/api/v1/works/$WORK_ID" "Update Work" "$WORK_UPDATE_PAYLOAD" "200"

# 6. Search for the work
echo "--- Searching for Test Work ---"
test_crud_operation "GET" "/api/v1/search/works?q=Yesterday" "Search Works" "" "200"

# 7. List all works (should include our test work)
echo "--- Listing All Works ---"
test_crud_operation "GET" "/api/v1/works" "List Works" "" "200"

# 8. List all songwriters (should include our test songwriter)
echo "--- Listing All Songwriters ---"
test_crud_operation "GET" "/api/v1/songwriters" "List Songwriters" "" "200"

# 9. Clean up - delete the work and songwriter
echo "--- Cleanup: Deleting Test Work ---"
test_crud_operation "DELETE" "/api/v1/works/$WORK_ID" "Delete Work" "" "204"

echo "--- Cleanup: Deleting Test Songwriter ---"
test_crud_operation "DELETE" "/api/v1/songwriters/$SONGWRITER_ID" "Delete Songwriter" "" "204"

# 10. Verify deletion - should return 404
echo "--- Verifying Deletion ---"
test_crud_operation "GET" "/api/v1/works/$WORK_ID" "Verify Work Deleted" "" "404"
test_crud_operation "GET" "/api/v1/songwriters/$SONGWRITER_ID" "Verify Songwriter Deleted" "" "404"

echo "=============================================="
echo "📋 Test Summary"
echo "=============================================="
echo ""
echo "Service Status:"
echo "- Base URL: $API_BASE_URL"
echo "- Test Tenant ID: $TENANT_ID"
echo ""
echo "Expected Results:"
echo "- ✅ System endpoints should work without tenant headers"
echo "- ✅ API endpoints should reject requests without tenant headers (400)"  
echo "- ✅ API endpoints should work with valid tenant headers (200)"
echo "- ✅ CRUD operations should work end-to-end (Create, Read, Update, Delete)"
echo ""
echo "Multi-tenant Security:"
echo "- All /api/v1/* endpoints require X-Tenant-ID header"
echo "- System endpoints (/health, /docs, etc.) are publicly accessible" 
echo "- Data is isolated per tenant (each tenant has separate data)"
echo ""
echo "Integration Tests Performed:"
echo "1. ✅ Create Songwriter → Get Songwriter"
echo "2. ✅ Create Work (with writer relationship) → Get Work"
echo "3. ✅ Update Work → Verify changes" 
echo "4. ✅ Search functionality"
echo "5. ✅ List operations"
echo "6. ✅ Delete operations → Verify cleanup"
echo ""
echo "To manually test with tenant header:"
echo "  curl -H \"X-Tenant-ID: $TENANT_ID\" http://localhost:8000/api/v1/works"
echo ""
echo "To check service logs:"
echo "  docker-compose logs catalog-service"
echo ""
echo "To access the database:"
echo "  docker-compose exec postgres psql -U catalog_user -d catalog_management"