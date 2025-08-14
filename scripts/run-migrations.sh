#!/bin/bash
# Database migration script

set -e

echo "Running database migrations..."

# Check if DATABASE_URL is set
if [ -z "$DATABASE_URL" ]; then
    echo "DATABASE_URL environment variable is not set."
    echo "Using default: postgresql://catalog_user:catalog_password@localhost:5432/catalog_management"
    export DATABASE_URL="postgresql://catalog_user:catalog_password@localhost:5432/catalog_management"
fi

# Run migrations using Alembic
python -m alembic upgrade head

echo "Database migrations completed successfully!"