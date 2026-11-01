import asyncio
import time
from uuid import UUID
from typing import Any

import asyncpg

from app.repositories import get_zoho_refresh_token_for_connection
from zoho.crypto import decrypt_refresh_token
from zoho.client import refresh_access_token


# 1. In-memory Cache for Zoho Access Tokens
_token_cache: dict[tuple[UUID, UUID], dict[str, Any]] = {}


# 2. Lock Manager - Locks to prevent concurrent token refreshes
_token_locks: dict[tuple[UUID, UUID], asyncio.Lock] = {}


# 3. Lock Helper - Get or Create a Lock
def get_token_lock(cache_key: tuple[UUID, UUID]) -> asyncio.Lock:
    
    """Get or Create a lock for a specific organization connection."""

    if cache_key not in _token_locks:
        _token_locks[cache_key] = asyncio.Lock()
    
    return _token_locks[cache_key]


# 4. Cache Validation Mechanism
def get_cached_access_token(cache_key: tuple[UUID, UUID]) -> str | None:
    
    """Return a cached access token if it is still valid."""

    cached_token = _token_cache.get(cache_key)

    if cached_token is None:
        return None
    
    # Refresh 60 seconds before actual expiry - We are expiring 60s befor for safety
    if cached_token["expires_at"] <= time.monotonic() + 60:
        _token_cache.pop(cache_key, None)
        return None
    
    return cached_token["access_token"]


# 5. Cache Access Token 
def cache_access_token(
        cache_key: tuple[UUID, UUID],
        token_data: dict[str, Any],
    ) -> None:

    """Store an access token and its expiry timestamp in the cache."""

    access_token = token_data.get("access_token")
    expires_in = token_data.get("expires_in")

    if not isinstance(access_token, str) or not access_token.strip():
        raise ValueError("Invalid access token expiry received from Zoho.")
    
    if not isinstance(expires_in, (int, float)) or isinstance(expires_in, bool) or expires_in <= 0:
        raise ValueError("Invalid access token expiry received from Zoho.")
    
    expires_at = time.monotonic() + expires_in

    _token_cache[cache_key] = {
        "access_token": access_token,
        "expires_at": expires_at,
    }


# 6. Main Function that coordinates the entire token management lifecycle
async def get_access_token(
        pool: asyncpg.Pool,
        tenant_id: UUID,
        connection_id: UUID,
    ) -> str:

    """Get a valid Zoho access token, using the cache whenever possible."""

    cache_key = (tenant_id, connection_id)

    # 1. Check the cache before acquiring lock
    cached_token = get_cached_access_token(cache_key)

    if cached_token:
        return cached_token
    

    #2. Acquire the lock for this organization connection
    async with get_token_lock(cache_key):

        # 3. Check the cache again after acquiring the lock
        cached_token = get_cached_access_token(cache_key)

        if cached_token:
            return cached_token
        

        # 4. Retrieve the encrypted refresh token from the database
        encrypted_refresh_token = await get_zoho_refresh_token_for_connection(
            pool,
            tenant_id,
            connection_id,
        )

        if encrypted_refresh_token is None:
            raise ValueError("No active Zoho authorization found for this connection.")
        

        # 5. Decrypt the refresh token 
        refresh_token = decrypt_refresh_token(encrypted_refresh_token)
        

        # 6. Request a new access token from Zoho
        token_data = await refresh_access_token(refresh_token)


        # 7. Store the new access token in cache
        cache_access_token(cache_key, token_data)
        

        # 8. Return the access token 
        return token_data["access_token"]

