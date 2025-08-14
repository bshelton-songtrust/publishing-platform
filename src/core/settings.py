"""Application settings and configuration."""

from functools import lru_cache
from typing import List, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="forbid",
    )

    # Environment
    environment: str = "development"
    debug: bool = False
    log_level: str = "INFO"

    # Database
    database_url: str = (
        "postgresql://catalog_user:catalog_password@localhost:5432/catalog_management"
    )
    database_pool_size: int = 20
    database_max_overflow: int = 0
    database_pool_timeout: int = 30
    database_pool_recycle: int = 3600

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    redis_pool_size: int = 10

    # JWT Authentication
    jwt_secret_key: str = "your-super-secret-jwt-key-change-this-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7

    # API Configuration
    api_v1_prefix: str = "/api/v1"
    cors_origins: List[str] = ["http://localhost:3000", "http://localhost:8080"]
    allowed_hosts: List[str] = ["localhost", "127.0.0.1", "0.0.0.0"]

    # Rate Limiting
    rate_limit_read_per_minute: int = 1000
    rate_limit_write_per_minute: int = 500

    # AWS Configuration
    aws_region: str = "us-east-1"
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None

    # Event Publishing
    event_bus_type: str = "mock"  # Options: sqs, mock
    sqs_event_queue_url: Optional[str] = None

    # Search Configuration
    search_index_name: str = "catalog_search"
    search_min_score: float = 0.5

    # File Upload Configuration
    max_file_size_mb: int = 10
    allowed_file_types: List[str] = [
        "audio/mpeg",
        "audio/wav", 
        "audio/mp4",
        "audio/flac"
    ]

    # External Service URLs
    rmp_api_base_url: Optional[str] = None
    songwriter_service_url: Optional[str] = None

    # Monitoring
    datadog_api_key: Optional[str] = None
    sentry_dsn: Optional[str] = None

    # Development/Testing
    mock_external_services: bool = True
    disable_auth: bool = False
    skip_migrations: bool = False

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Validate environment value."""
        valid_environments = ["development", "staging", "production", "test"]
        if v not in valid_environments:
            raise ValueError(f"Environment must be one of: {valid_environments}")
        return v

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"Log level must be one of: {valid_levels}")
        return v.upper()

    @field_validator("event_bus_type")
    @classmethod
    def validate_event_bus_type(cls, v: str) -> str:
        """Validate event bus type."""
        valid_types = ["sqs", "mock"]
        if v not in valid_types:
            raise ValueError(f"Event bus type must be one of: {valid_types}")
        return v

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.environment == "development"

    @property
    def is_testing(self) -> bool:
        """Check if running in test environment."""
        return self.environment == "test"


@lru_cache()
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings()