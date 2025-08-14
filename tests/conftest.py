"""Pytest configuration and fixtures."""

import asyncio
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from src.main import app
from src.core.database import get_db_session, Base
from src.core.settings import get_settings

# Test database URL (using SQLite for tests)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

# Create test engine
test_engine = create_async_engine(
    TEST_DATABASE_URL,
    poolclass=StaticPool,
    connect_args={"check_same_thread": False},
    echo=True,
)

TestSessionLocal = async_sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@pytest_asyncio.fixture
async def db_session():
    """Create a test database session."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async with TestSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_session):
    """Create a test client with database dependency override."""
    
    async def get_test_db():
        yield db_session
    
    app.dependency_overrides[get_db_session] = get_test_db
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client
    
    app.dependency_overrides.clear()


@pytest.fixture
def sample_work_data():
    """Sample work data for testing."""
    return {
        "data": {
            "type": "work",
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "attributes": {
                "title": "Test Song",
                "genre": "Pop",
                "language": "en",
                "duration": 180,
                "is_instrumental": False,
                "has_lyrics": True,
                "registration_status": "draft",
                "writers": [
                    {
                        "songwriter_id": "550e8400-e29b-41d4-a716-446655440001",
                        "role": "composer_lyricist",
                        "contribution_percentage": 100.0
                    }
                ]
            }
        }
    }


@pytest.fixture
def sample_songwriter_data():
    """Sample songwriter data for testing."""
    return {
        "data": {
            "type": "songwriter",
            "id": "550e8400-e29b-41d4-a716-446655440001",
            "attributes": {
                "first_name": "John",
                "last_name": "Doe",
                "stage_name": "Johnny D",
                "email": "john.doe@example.com",
                "status": "active"
            }
        }
    }


@pytest.fixture
def tenant_id():
    """Test tenant ID."""
    return "550e8400-e29b-41d4-a716-446655440099"


@pytest.fixture
def user_id():
    """Test user ID."""
    return "550e8400-e29b-41d4-a716-446655440098"


@pytest.fixture
def auth_headers(tenant_id, user_id):
    """Authentication headers for testing."""
    # In a real implementation, you'd generate a proper JWT token
    # For testing, we can mock the authentication
    return {
        "Authorization": "Bearer test-token",
        "X-Tenant-ID": tenant_id,
        "Content-Type": "application/json"
    }