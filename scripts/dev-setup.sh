#!/bin/bash
# Development setup script

set -e

echo "Setting up Catalog Management Service for development..."

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "Error: Docker is not running. Please start Docker and try again."
    exit 1
fi

# Copy environment file if it doesn't exist
if [ ! -f .env ]; then
    echo "Creating .env file from template..."
    cp .env.example .env
    echo "Please review and update .env file with your settings."
fi

# Build and start services
echo "Building and starting services..."
echo "Cleaning up old images and building fresh (this may take a few minutes)..."
docker-compose down --rmi all --volumes --remove-orphans 2>/dev/null || true
docker system prune -f 2>/dev/null || true
docker-compose build --no-cache --pull
docker-compose up -d postgres redis

# Wait for database to be ready
echo "Waiting for database to be ready..."
sleep 10

# Clean Python cache files first
echo "Cleaning Python cache files..."
find . -type f -name "*.pyc" -delete 2>/dev/null || true
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# Run database migrations
echo "Running database migrations..."
docker-compose build --no-cache migrate
docker-compose --profile tools run --rm migrate

# Start the application
echo "Starting catalog service..."
docker-compose up -d catalog-service

# Show service status
echo "Service status:"
docker-compose ps

echo ""
echo "Setup complete! Services are running:"
echo "- Catalog Management API: http://localhost:8000"
echo "- API Documentation: http://localhost:8000/docs"
echo "- Health Check: http://localhost:8000/health"
echo "- PostgreSQL: localhost:5432"
echo "- Redis: localhost:6379"
echo ""
echo "To view logs: docker-compose logs -f catalog-service"
echo "To stop services: docker-compose down"