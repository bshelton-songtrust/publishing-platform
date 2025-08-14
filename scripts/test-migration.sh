#!/bin/bash
# Test migration script to isolate the computed_column issue

set -e

echo "Testing migration in isolation..."

# Stop everything first
docker-compose down --rmi all --volumes --remove-orphans 2>/dev/null || true

# Clean Python cache
echo "Cleaning Python cache files..."
find . -type f -name "*.pyc" -delete 2>/dev/null || true
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# Start just postgres
echo "Starting PostgreSQL..."
docker-compose up -d postgres

# Wait for postgres to be ready
echo "Waiting for PostgreSQL to be ready..."
sleep 15

# Check what's in the actual source files being copied
echo "Checking source files for computed_column..."
grep -r "computed_column" src/ || echo "No computed_column found in src/"

# Build just the migrate service with verbose output
echo "Building migration container..."
docker-compose build --no-cache --progress=plain migrate

# Try to run a simple Python import test inside container
echo "Testing Python imports in container..."
docker-compose --profile tools run --rm migrate python -c "from src.models.songwriter import Songwriter; print('Import successful')"