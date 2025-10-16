"""
Web server security middleware for authentication and rate limiting.

This module provides:
- API key authentication
- Rate limiting per client IP
- Request validation
"""

import asyncio
import logging
import time
from collections import defaultdict
from typing import Dict, Optional, Tuple

from fastapi import Header, HTTPException, Request, status
from fastapi.security import APIKeyHeader

logger = logging.getLogger(__name__)

# API Key scheme
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


class RateLimiter:
    """
    Simple in-memory rate limiter using sliding window.

    Thread-safe for async operations. In production, consider using
    Redis for distributed rate limiting.
    """

    def __init__(self, requests_per_minute: int = 60):
        """
        Initialize rate limiter.

        Args:
            requests_per_minute: Maximum requests allowed per client per minute
        """
        self.requests_per_minute = requests_per_minute
        self.window_size = 60  # seconds
        # Store: {client_id: [(timestamp1, timestamp2, ...)]}
        self.request_history: Dict[str, list] = defaultdict(list)
        self._lock = asyncio.Lock()  # Protect request_history from race conditions

    async def is_allowed(self, client_id: str) -> Tuple[bool, Optional[int]]:
        """
        Check if request is allowed under rate limit (thread-safe).

        Args:
            client_id: Unique identifier for client (IP address)

        Returns:
            Tuple of (is_allowed, retry_after_seconds)
        """
        async with self._lock:
            now = time.time()
            cutoff = now - self.window_size

            # Clean old requests outside the window
            self.request_history[client_id] = [
                ts for ts in self.request_history[client_id] if ts > cutoff
            ]

            # Check if under limit
            if len(self.request_history[client_id]) >= self.requests_per_minute:
                # Calculate retry_after from oldest request in window
                oldest = min(self.request_history[client_id])
                retry_after = int(oldest + self.window_size - now) + 1
                return False, retry_after

            # Allow request and record timestamp
            self.request_history[client_id].append(now)
            return True, None

    async def cleanup_old_entries(self, max_age_seconds: int = 300):
        """
        Cleanup old client histories to prevent memory bloat (thread-safe).

        Args:
            max_age_seconds: Remove clients with no requests in this many seconds
        """
        async with self._lock:
            now = time.time()
            cutoff = now - max_age_seconds

            clients_to_remove = [
                client_id
                for client_id, timestamps in self.request_history.items()
                if not timestamps or max(timestamps) < cutoff
            ]

            for client_id in clients_to_remove:
                del self.request_history[client_id]


class SecurityManager:
    """Centralized security manager for authentication and rate limiting."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        rate_limit_per_minute: int = 60,
        enable_auth: bool = True,
        enable_rate_limit: bool = True,
    ):
        """
        Initialize security manager.

        Args:
            api_key: Valid API key for authentication (None = auth disabled)
            rate_limit_per_minute: Max requests per client per minute
            enable_auth: Whether to enforce authentication
            enable_rate_limit: Whether to enforce rate limiting
        """
        self.api_key = api_key
        self.enable_auth = enable_auth and api_key is not None
        self.enable_rate_limit = enable_rate_limit
        self.rate_limiter = RateLimiter(requests_per_minute=rate_limit_per_minute)

        if self.enable_auth:
            logger.info("API authentication enabled")
        else:
            logger.warning(
                "API authentication DISABLED - all endpoints are unprotected!"
            )

        if self.enable_rate_limit:
            logger.info(f"Rate limiting enabled: {rate_limit_per_minute} req/min")

    async def verify_api_key(self, x_api_key: Optional[str] = Header(None)):
        """
        FastAPI dependency for API key verification.

        Args:
            x_api_key: API key from X-API-Key header

        Raises:
            HTTPException: If authentication fails
        """
        if not self.enable_auth:
            return  # Auth disabled, allow request

        if not x_api_key:
            logger.warning("Request missing API key")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing API key. Include X-API-Key header.",
                headers={"WWW-Authenticate": "ApiKey"},
            )

        if x_api_key != self.api_key:
            logger.warning(f"Invalid API key attempt: {x_api_key[:8]}...")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid API key",
            )

    async def check_rate_limit(self, request: Request):
        """
        FastAPI dependency for rate limit checking.

        Args:
            request: FastAPI Request object

        Raises:
            HTTPException: If rate limit exceeded
        """
        if not self.enable_rate_limit:
            return  # Rate limiting disabled

        # Use client IP as identifier
        client_ip = request.client.host if request.client else "unknown"

        allowed, retry_after = await self.rate_limiter.is_allowed(client_ip)

        if not allowed:
            logger.warning(f"Rate limit exceeded for {client_ip}")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Retry after {retry_after} seconds.",
                headers={"Retry-After": str(retry_after)},
            )
