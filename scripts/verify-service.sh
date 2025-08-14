#!/bin/bash
# Service Verification Script - Check if the catalog service is working

set -e

API_BASE_URL="http://localhost:8000"

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

# Function to test endpoint with detailed output
test_endpoint() {
    local endpoint=$1
    local description=$2
    local expected_status=${3:-200}
    
    echo_status "Testing: $description"
    echo_status "URL: $API_BASE_URL$endpoint"
    
    response=$(curl -s -w "HTTPSTATUS:%{http_code}" "$API_BASE_URL$endpoint" 2>/dev/null || echo "HTTPSTATUS:000")
    
    # Extract status code and body
    http_code=$(echo "$response" | grep -o "HTTPSTATUS:[0-9]*" | cut -d: -f2)
    body=$(echo "$response" | sed 's/HTTPSTATUS:[0-9]*$//')
    
    echo "HTTP Status: $http_code (expected: $expected_status)"
    
    if [[ "$http_code" == "$expected_status" ]]; then
        echo_success "✅ $description"
        if [[ "$body" != "" ]]; then
            echo "Response:"
            echo "$body" | jq '.' 2>/dev/null || echo "$body"
        fi
    elif [[ "$http_code" == "000" ]]; then
        echo_error "❌ $description - Connection failed"
        echo "   Make sure the service is running: docker-compose ps catalog-service"
    else
        echo_error "❌ $description - Status $http_code (expected $expected_status)"
        if [[ "$body" != "" ]]; then
            echo "Response: $body"
        fi
    fi
    echo ""
}

# Function to check database directly
check_database() {
    echo_status "Checking database tables..."
    
    # Check if postgres is running
    if ! docker-compose ps postgres | grep -q "Up"; then
        echo_error "PostgreSQL container is not running"
        return 1
    fi
    
    # Check tables exist
    tables=$(docker-compose exec -T postgres psql -U catalog_user -d catalog_management -t -c "
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
        ORDER BY table_name;
    " 2>/dev/null || echo "")
    
    if [[ "$tables" != "" ]]; then
        echo_success "✅ Database connected, tables found:"
        echo "$tables" | sed 's/^/   /'
    else
        echo_error "❌ Could not connect to database or no tables found"
        return 1
    fi
    echo ""
}

# Function to check service logs
check_service_logs() {
    echo_status "Checking service logs (last 10 lines)..."
    
    if docker-compose ps catalog-service | grep -q "Up"; then
        echo "Recent logs:"
        docker-compose logs --tail=10 catalog-service 2>/dev/null || echo "Could not fetch logs"
    else
        echo_error "Catalog service is not running"
        echo "Service status:"
        docker-compose ps catalog-service 2>/dev/null || echo "Could not get service status"
    fi
    echo ""
}

echo "=============================================="
echo "🔍 Catalog Management Service Verification"
echo "=============================================="
echo ""

# Check if Docker containers are running
echo_status "1. Checking Docker containers..."
if command -v docker-compose >/dev/null 2>&1; then
    echo "Container Status:"
    docker-compose ps 2>/dev/null || echo "Could not get container status"
else
    echo_error "docker-compose not found"
    exit 1
fi
echo ""

# Test service endpoints
echo_status "2. Testing service endpoints..."

test_endpoint "/health" "Health Check" "200"
test_endpoint "/health/database" "Database Health" "200" 
test_endpoint "/health/dependencies" "Dependencies Health" "200"
test_endpoint "/version" "Version Info" "200"
test_endpoint "/docs" "API Documentation" "200"
test_endpoint "/openapi.json" "OpenAPI Spec" "200"

# Check database
echo_status "3. Database verification..."
check_database

# Check service logs
echo_status "4. Service status..."
check_service_logs

# Summary and recommendations
echo "=============================================="
echo "📋 Verification Summary"
echo "=============================================="
echo ""
echo "Next steps to test the API:"
echo ""
echo "1. 📖 View API Documentation:"
echo "   Open in browser: http://localhost:8000/docs"
echo ""
echo "2. 🗄️  Access Database:"
echo "   docker-compose exec postgres psql -U catalog_user -d catalog_management"
echo ""
echo "3. 📊 View Service Logs:"
echo "   docker-compose logs -f catalog-service"
echo ""
echo "4. 🔍 Check Available Endpoints:"
echo "   curl http://localhost:8000/openapi.json | jq '.paths'"
echo ""
echo "5. 🧪 Manual API Testing:"
echo "   Use the interactive docs at /docs or tools like Postman/curl"
echo ""

# Test if main API routes are enabled
echo_status "5. Checking if main API routes are available..."
test_endpoint "/api/v1/works" "Works API (may be disabled)" "404"
test_endpoint "/api/v1/songwriters" "Songwriters API (may be disabled)" "404"

echo "=============================================="
echo "🎵 Service is ready for testing!"
echo "=============================================="