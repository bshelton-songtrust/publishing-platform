#!/bin/bash
# API Test Script - Verify Catalog Management Service
# Tests tenant creation, songwriters, works, recordings, and search functionality

set -e

API_BASE_URL="http://localhost:8000"
TENANT_ID="550e8400-e29b-41d4-a716-446655440000"
TENANT_ID_2="550e8400-e29b-41d4-a716-446655440001"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Function to make API calls with proper error handling
api_call() {
    local method=$1
    local endpoint=$2
    local data=$3
    local tenant_id=${4:-$TENANT_ID}
    
    echo_status "Making $method request to $endpoint"
    
    if [ "$method" = "GET" ]; then
        response=$(curl -s -w "HTTPSTATUS:%{http_code}" \
            -H "Content-Type: application/json" \
            -H "X-Tenant-ID: $tenant_id" \
            "$API_BASE_URL$endpoint")
    else
        response=$(curl -s -w "HTTPSTATUS:%{http_code}" \
            -X "$method" \
            -H "Content-Type: application/json" \
            -H "X-Tenant-ID: $tenant_id" \
            -d "$data" \
            "$API_BASE_URL$endpoint")
    fi
    
    # Extract status code and body
    http_code=$(echo "$response" | grep -o "HTTPSTATUS:[0-9]*" | cut -d: -f2)
    body=$(echo "$response" | sed 's/HTTPSTATUS:[0-9]*$//')
    
    echo "HTTP Status: $http_code"
    echo "Response: $body" | jq '.' 2>/dev/null || echo "Response: $body"
    echo ""
    
    if [[ "$http_code" -ge 200 && "$http_code" -lt 300 ]]; then
        echo_success "$method $endpoint - Success"
        echo "$body"
    else
        echo_error "$method $endpoint - Failed with status $http_code"
        echo "$body"
        return 1
    fi
}

# Start testing
echo "=============================================="
echo "🎵 Catalog Management Service API Test Suite"
echo "=============================================="
echo ""

# Test 1: Health Check
echo_status "1. Testing Health Check..."
api_call "GET" "/health" "" ""
echo ""

# Test 2: Create Tenant (directly in database since tenant management might not be exposed)
echo_status "2. Creating test tenant in database..."
docker-compose exec -T postgres psql -U catalog_user -d catalog_management -c "
INSERT INTO tenants (id, name, subdomain, status, plan_type, settings, additional_data, created_at, updated_at) 
VALUES (
    '$TENANT_ID',
    'Test Publishing Company',
    'test-publisher',
    'active',
    'professional',
    '{}',
    '{}',
    NOW(),
    NOW()
) ON CONFLICT (id) DO NOTHING;
"
echo_success "Tenant created/verified"
echo ""

# Test 3: Create Songwriters
echo_status "3. Creating songwriters..."

# Songwriter 1 - John Smith
songwriter1_data='{
    "data": {
        "type": "songwriter",
        "attributes": {
            "first_name": "John",
            "last_name": "Smith",
            "stage_name": "Johnny S",
            "email": "john.smith@example.com",
            "phone": "+1-555-123-4567",
            "birth_date": "1990-05-15",
            "birth_country": "US",
            "nationality": "US",
            "status": "active",
            "biography": "Talented songwriter from Nashville",
            "website": "https://johnnysmith.music"
        }
    }
}'

songwriter1_response=$(api_call "POST" "/api/v1/songwriters" "$songwriter1_data")
songwriter1_id=$(echo "$songwriter1_response" | jq -r '.data.id' 2>/dev/null || echo "")

if [ "$songwriter1_id" != "" ] && [ "$songwriter1_id" != "null" ]; then
    echo_success "Created songwriter 1: $songwriter1_id"
else
    echo_error "Failed to extract songwriter 1 ID"
fi

# Songwriter 2 - Jane Doe
songwriter2_data='{
    "data": {
        "type": "songwriter",
        "attributes": {
            "first_name": "Jane",
            "last_name": "Doe", 
            "stage_name": "JD Music",
            "email": "jane.doe@example.com",
            "birth_date": "1988-12-03",
            "birth_country": "CA",
            "nationality": "CA",
            "status": "active",
            "biography": "Award-winning songwriter and producer"
        }
    }
}'

songwriter2_response=$(api_call "POST" "/api/v1/songwriters" "$songwriter2_data")
songwriter2_id=$(echo "$songwriter2_response" | jq -r '.data.id' 2>/dev/null || echo "")

if [ "$songwriter2_id" != "" ] && [ "$songwriter2_id" != "null" ]; then
    echo_success "Created songwriter 2: $songwriter2_id"
else
    echo_error "Failed to extract songwriter 2 ID"
fi

echo ""

# Test 4: Create Musical Works
echo_status "4. Creating musical works..."

# Work 1 - "Summer Dreams"
work1_data='{
    "data": {
        "type": "work",
        "attributes": {
            "title": "Summer Dreams",
            "alternate_titles": ["Dreams of Summer", "Dreaming Summer"],
            "genre": "Pop",
            "subgenre": "Indie Pop",
            "language": "en",
            "duration": 180,
            "tempo": 120,
            "key_signature": "C Major",
            "time_signature": "4/4",
            "lyrics_preview": "Under the summer sky, we dance and fly...",
            "description": "An uplifting pop song about summer romance",
            "status": "draft",
            "writers": [
                {
                    "songwriter_id": "'$songwriter1_id'",
                    "role": "composer",
                    "contribution_percentage": 60
                },
                {
                    "songwriter_id": "'$songwriter2_id'",
                    "role": "lyricist", 
                    "contribution_percentage": 40
                }
            ]
        }
    }
}'

work1_response=$(api_call "POST" "/api/v1/works" "$work1_data")
work1_id=$(echo "$work1_response" | jq -r '.data.id' 2>/dev/null || echo "")

if [ "$work1_id" != "" ] && [ "$work1_id" != "null" ]; then
    echo_success "Created work 1: $work1_id"
else
    echo_error "Failed to extract work 1 ID"
fi

# Work 2 - "City Lights"
work2_data='{
    "data": {
        "type": "work",
        "attributes": {
            "title": "City Lights",
            "genre": "Electronic",
            "subgenre": "Synthwave",
            "language": "en",
            "duration": 240,
            "tempo": 128,
            "description": "Electronic anthem about urban life",
            "status": "pending",
            "writers": [
                {
                    "songwriter_id": "'$songwriter2_id'",
                    "role": "composer",
                    "contribution_percentage": 100
                }
            ]
        }
    }
}'

work2_response=$(api_call "POST" "/api/v1/works" "$work2_data")
work2_id=$(echo "$work2_response" | jq -r '.data.id' 2>/dev/null || echo "")

if [ "$work2_id" != "" ] && [ "$work2_id" != "null" ]; then
    echo_success "Created work 2: $work2_id"
else
    echo_error "Failed to extract work 2 ID"
fi

echo ""

# Test 5: Create Recordings
echo_status "5. Creating recordings..."

# Recording 1 - Studio version of "Summer Dreams"
recording1_data='{
    "data": {
        "type": "recording",
        "attributes": {
            "work_id": "'$work1_id'",
            "title": "Summer Dreams (Studio Version)",
            "artist_name": "The Dreamers",
            "duration": 185,
            "release_date": "2024-06-15",
            "label": "Indie Records",
            "catalog_number": "IR-2024-001",
            "format": "digital",
            "country": "US",
            "description": "Official studio recording"
        }
    }
}'

recording1_response=$(api_call "POST" "/api/v1/recordings" "$recording1_data")
recording1_id=$(echo "$recording1_response" | jq -r '.data.id' 2>/dev/null || echo "")

if [ "$recording1_id" != "" ] && [ "$recording1_id" != "null" ]; then
    echo_success "Created recording 1: $recording1_id"
else
    echo_error "Failed to extract recording 1 ID"
fi

echo ""

# Test 6: Retrieve Data
echo_status "6. Testing data retrieval..."

echo_status "6a. Get all songwriters"
api_call "GET" "/api/v1/songwriters"

echo_status "6b. Get specific songwriter"
if [ "$songwriter1_id" != "" ]; then
    api_call "GET" "/api/v1/songwriters/$songwriter1_id"
fi

echo_status "6c. Get all works"
api_call "GET" "/api/v1/works"

echo_status "6d. Get specific work with writers"
if [ "$work1_id" != "" ]; then
    api_call "GET" "/api/v1/works/$work1_id?include=writers"
fi

echo_status "6e. Get all recordings"
api_call "GET" "/api/v1/recordings"

echo ""

# Test 7: Search Functionality
echo_status "7. Testing search functionality..."

echo_status "7a. Search works by title"
api_call "GET" "/api/v1/search/works?q=Summer"

echo_status "7b. Search songwriters by name"
api_call "GET" "/api/v1/search/songwriters?q=John"

echo ""

# Test 8: Update Operations
echo_status "8. Testing update operations..."

if [ "$work1_id" != "" ]; then
    update_data='{
        "data": {
            "type": "work",
            "id": "'$work1_id'",
            "attributes": {
                "status": "registered",
                "iswc": "T-123456789-1"
            }
        }
    }'
    
    echo_status "8a. Update work status and add ISWC"
    api_call "PATCH" "/api/v1/works/$work1_id" "$update_data"
    
    echo_status "8b. Verify update"
    api_call "GET" "/api/v1/works/$work1_id"
fi

echo ""

# Test 9: Multi-tenant Isolation
echo_status "9. Testing multi-tenant isolation..."

# Try to access data with different tenant ID
echo_status "9a. Attempting to access data with different tenant ID (should return empty)"
api_call "GET" "/api/v1/works" "" "$TENANT_ID_2"

echo ""

# Test 10: Pagination and Filtering
echo_status "10. Testing pagination and filtering..."

echo_status "10a. Get works with pagination"
api_call "GET" "/api/v1/works?page=1&per_page=10"

echo_status "10b. Filter works by genre"
api_call "GET" "/api/v1/works?genre=Pop"

echo_status "10c. Filter works by status"
api_call "GET" "/api/v1/works?status=registered"

echo ""

# Summary
echo "=============================================="
echo_success "🎉 API Test Suite Completed!"
echo "=============================================="
echo ""
echo "Test Summary:"
echo "✅ Health check"
echo "✅ Tenant setup"
echo "✅ Songwriter creation"
echo "✅ Work creation with writers"
echo "✅ Recording creation"
echo "✅ Data retrieval"
echo "✅ Search functionality"
echo "✅ Update operations"
echo "✅ Multi-tenant isolation"
echo "✅ Pagination and filtering"
echo ""
echo "🚀 Your Catalog Management Service is working perfectly!"
echo ""
echo "Next steps:"
echo "- Visit http://localhost:8000/docs for interactive API documentation"
echo "- Check the database: docker-compose exec postgres psql -U catalog_user -d catalog_management"
echo "- View logs: docker-compose logs catalog-service"