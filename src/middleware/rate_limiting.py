"""Rate limiting middleware using Redis."""

import asyncio
import logging
import time
from typing import Optional

import redis.asyncio as redis
from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware

from src.core.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware using Redis for distributed rate limiting.
    Implements sliding window rate limiting with different limits for read/write operations.
    """

    def __init__(self, app):
        super().__init__(app)
        self.redis_client: Optional[redis.Redis] = None
        self._initialize_redis()

    def _initialize_redis(self):
        """Initialize Redis connection."""
        try:
            self.redis_client = redis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
                max_connections=settings.redis_pool_size,
            )
            logger.info("Redis client initialized for rate limiting")
        except Exception as e:
            logger.error(f"Failed to initialize Redis client: {e}")
            self.redis_client = None

    async def dispatch(self, request: Request, call_next):
        """Apply rate limiting to requests."""
        # Skip rate limiting for exempt paths
        if self._is_exempt_path(request.url.path):
            return await call_next(request)

        # Skip rate limiting if Redis is not available (fallback mode)
        if not self.redis_client:
            logger.warning("Rate limiting disabled - Redis not available")
            return await call_next(request)

        # Get tenant and user context
        tenant_id = getattr(request.state, "tenant_id", None)
        user_id = getattr(request.state, "user_id", None)

        if not tenant_id:
            # Rate limiting requires tenant context
            return await call_next(request)

        # Determine rate limit based on operation type
        is_write_operation = request.method in {"POST", "PUT", "PATCH", "DELETE"}
        limit = (
            settings.rate_limit_write_per_minute
            if is_write_operation
            else settings.rate_limit_read_per_minute
        )

        # Apply rate limiting
        try:
            allowed = await self._check_rate_limit(
                tenant_id=tenant_id,
                user_id=user_id,
                operation_type="write" if is_write_operation else "read",
                limit=limit,
            )

            if not allowed:
                # Rate limit exceeded
                logger.warning(
                    f"Rate limit exceeded for tenant {tenant_id}, "
                    f"user {user_id}, operation: {'write' if is_write_operation else 'read'}"
                )
                
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "error": "rate_limit_exceeded",
                        "message": f"Rate limit of {limit} requests per minute exceeded",
                        "code": "RATE_LIMIT_EXCEEDED",
                        "retry_after": 60,
                    },
                    headers={
                        "Retry-After": "60",
                        "X-RateLimit-Limit": str(limit),
                        "X-RateLimit-Remaining": "0",
                    },
                )

        except redis.RedisError as e:
            logger.error(f"Redis error during rate limiting: {e}")
            # Continue without rate limiting if Redis fails
            pass

        # Process the request
        response = await call_next(request)

        # Add rate limit headers to response
        try:
            remaining = await self._get_remaining_requests(
                tenant_id=tenant_id,
                user_id=user_id,
                operation_type="write" if is_write_operation else "read",
                limit=limit,
            )
            
            response.headers["X-RateLimit-Limit"] = str(limit)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
            response.headers["X-RateLimit-Reset"] = str(int(time.time()) + 60)
            
        except redis.RedisError:
            # Ignore Redis errors for response headers
            pass

        return response

    async def _check_rate_limit(
        self,
        tenant_id: str,
        user_id: Optional[str],
        operation_type: str,
        limit: int,
    ) -> bool:
        """Check if request should be rate limited using sliding window."""
        current_time = int(time.time())
        window_start = current_time - 60  # 1 minute window

        # Create rate limiting keys
        tenant_key = f"rate_limit:tenant:{tenant_id}:{operation_type}:{current_time // 60}"
        user_key = None
        if user_id:
            user_key = f"rate_limit:user:{user_id}:{operation_type}:{current_time // 60}"

        # Use Redis pipeline for atomic operations
        async with self.redis_client.pipeline() as pipe:
            # Check and increment tenant counter
            pipe.incr(tenant_key)
            pipe.expire(tenant_key, 60)

            if user_key:
                # Check and increment user counter (optional)
                pipe.incr(user_key)
                pipe.expire(user_key, 60)

            results = await pipe.execute()

        tenant_count = results[0]
        
        # Check if tenant limit exceeded
        if tenant_count > limit:
            return False

        # For now, we only enforce tenant-level limits
        # User-level limits could be added here if needed
        return True

    async def _get_remaining_requests(
        self,
        tenant_id: str,
        user_id: Optional[str],
        operation_type: str,
        limit: int,
    ) -> int:
        """Get remaining requests in current window."""
        current_time = int(time.time())
        tenant_key = f"rate_limit:tenant:{tenant_id}:{operation_type}:{current_time // 60}"

        try:
            current_count = await self.redis_client.get(tenant_key)
            current_count = int(current_count) if current_count else 0
            return max(0, limit - current_count)
        except redis.RedisError:
            return limit

    def _is_exempt_path(self, path: str) -> bool:
        """Check if path is exempt from rate limiting."""
        exempt_paths = {
            "/health",
            "/openapi.json",
            "/docs",
            "/redoc",
            "/favicon.ico",
        }
        return path in exempt_paths

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.redis_client:
            await self.redis_client.close()


class InMemoryRateLimiter:
    """
    Fallback in-memory rate limiter when Redis is not available.
    Note: This is not suitable for production with multiple instances.
    """

    def __init__(self):
        self.requests: dict = {}
        self.cleanup_interval = 60
        self.last_cleanup = time.time()

    async def check_rate_limit(
        self,
        key: str,
        limit: int,
        window: int = 60,
    ) -> bool:
        """Check rate limit using in-memory storage."""
        current_time = time.time()
        window_start = current_time - window

        # Cleanup old entries periodically
        if current_time - self.last_cleanup > self.cleanup_interval:
            await self._cleanup_old_entries(window_start)
            self.last_cleanup = current_time

        # Get or create request list for this key
        if key not in self.requests:
            self.requests[key] = []

        # Remove requests outside the window
        self.requests[key] = [
            timestamp for timestamp in self.requests[key] 
            if timestamp > window_start
        ]

        # Check if limit exceeded
        if len(self.requests[key]) >= limit:
            return False

        # Add current request
        self.requests[key].append(current_time)
        return True

    async def _cleanup_old_entries(self, cutoff_time: float):
        """Remove old entries to prevent memory leaks."""
        keys_to_remove = []
        for key, timestamps in self.requests.items():
            # Remove old timestamps
            self.requests[key] = [
                timestamp for timestamp in timestamps 
                if timestamp > cutoff_time
            ]
            
            # Mark empty keys for removal
            if not self.requests[key]:
                keys_to_remove.append(key)

        # Remove empty keys
        for key in keys_to_remove:
            del self.requests[key]