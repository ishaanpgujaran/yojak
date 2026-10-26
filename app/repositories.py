#Repository module provides functions that handle database operations
from typing import Any
from uuid import UUID

import asyncpg

import hashlib
from datetime import datetime, timedelta, timezone


# H1. SHA-256 Hash of OAuth State Value
def hash_oauth_state(state: str) -> str:
    return hashlib.sha256(state.encode("utf-8")).hexdigest()


# 1. Creating Tenant 
async def get_or_create_tenant(pool: asyncpg.Pool, name: str,) -> dict[str, Any]:
    
    query = """
        INSERT INTO tenants (workos_user_id, name)
        VALUES ($1, 'tenant ' || LEFT(REPLACE(gen_random_uuid()::TEXT,'-',''),8))
        ON CONFLICT (workos_user_id)
        DO UPDATE SET workos_user_id = EXCLUDED.workos_user_id
        RETURNING id, workos_user_id, name, created_at;
    """

    async with pool.acquire() as connection:
        row = await connection.fetchrow(query, name)
    
    return dict(row)


#2. Retrieving Tenant
async def get_tenant(pool: asyncpg.Pool, tenant_id: UUID,) -> dict[str, Any] | None:
    
    query = """
        SELECT id, name, created_at
        FROM tenants
        WHERE id = $1;
    """

    async with pool.acquire() as connection:
        row = await connection.fetchrow(query, tenant_id)

    return dict(row) if row else None


# 3. Creating Merchant
async def create_merchant_connection(
    pool: asyncpg.Pool,
    tenant_id: UUID,
    zoho_organization_id: str, 
    granted_scopes: list[str],
    ) -> dict[str, Any]:
    
    query = """
        INSERT INTO merchant_connections(
            tenant_id,
            provider,
            zoho_organization_id,
            granted_scopes
        )
        Values ($1, 'zoho_inventory', $2, $3)
        RETURNING
            id,
            tenant_id,
            provider,
            zoho_organization_id,
            granted_scopes,
            status,
            created_at,
            updated_at;
    """

    async with pool.acquire() as connection:
        row = await connection.fetchrow(
            query,
            tenant_id,
            zoho_organization_id,
            granted_scopes,
        )
    
    return dict(row)


# 4. Retrieving Merchant
async def get_merchant_connection(
    pool: asyncpg.Pool,
    tenant_id: UUID,
    connection_id: UUID,
    ) -> dict[str, Any] | None:
    
    query = """
        SELECT
            id,
            tenant_id,
            provider,
            zoho_organization_id,
            granted_scopes,
            status, 
            created_at,
            updated_at
        FROM merchant_connections
        WHERE tenant_id = $1 AND id = $2;
    """

    async with pool.acquire() as connection:
        row = await connection.fetchrow(
            query,
            tenant_id,
            connection_id,
        )
    
    return dict(row) if row else None    


# 5. Store Hashed OAuth State with Limited Lifetime
async def create_oauth_state(
    pool: asyncpg.Pool,
    state: str,
    tenant_id: UUID,
    expires_in_minutes: int = 10,
    ) -> None:

    if expires_in_minutes <= 0:
        raise ValueError("expires_in_minutes must be positive")
    
    state_hash = hash_oauth_state(state)

    expires_at = datetime.now(timezone.utc) + timedelta(minutes = expires_in_minutes)

    query = """
        INSERT INTO oauth_states (
            state_hash,
            tenant_id,
            expires_at
        )
        VALUES ($1, $2, $3);
    """

    async with pool.acquire() as connection:
        await connection.execute(
            query,
            state_hash,
            tenant_id,
            expires_at,
        )



# 6. Validate & Consume an Unexpired OAuth State exactly Once
async def consume_oauth_state(
    pool: asyncpg.Pool,
    state: str,
    ) -> UUID | None:

    state_hash = hash_oauth_state(state)

    query = """
        DELETE FROM oauth_states
        WHERE state_hash = $1 AND expires_at > NOW()
        RETURNING tenant_id;
    """

    async with pool.acquire() as connection:
        row = await connection.fetchrow(query, state_hash)

    return row["tenant_id"] if row else None