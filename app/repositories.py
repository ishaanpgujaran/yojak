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
async def get_or_create_tenant(
        pool: asyncpg.Pool, 
        workos_user_id: str,
    ) -> dict[str, Any]:
    
    query = """
        INSERT INTO tenants (workos_user_id, name)
        VALUES ($1, 'Tenant ' || LEFT(REPLACE(gen_random_uuid()::TEXT,'-',''),8))
        ON CONFLICT (workos_user_id)
        DO UPDATE SET workos_user_id = EXCLUDED.workos_user_id
        RETURNING id, workos_user_id, name, created_at;
    """

    async with pool.acquire() as connection:
        row = await connection.fetchrow(query, workos_user_id)
    
    return dict(row)


#2. Retrieving Tenant
async def get_tenant(
        pool: asyncpg.Pool,
        tenant_id: UUID,
    ) -> dict[str, Any] | None:
    
    query = """
        SELECT 
            id,
            name, 
            created_at,
            active_organization_connection_id
        FROM tenants
        WHERE id = $1;
    """

    async with pool.acquire() as connection:
        row = await connection.fetchrow(query, tenant_id)

    return dict(row) if row else None


# 3. Creating Zoho Authorization 
async def create_zoho_authorization(
        pool: asyncpg.Pool,
        tenant_id: UUID,
        refresh_token_encrypted: bytes,
        granted_scopes: list[str],
        status: str = "active",
    ) -> dict[str, Any]:

    if not refresh_token_encrypted:
        raise ValueError("Encrypted refresh token cannot be empty.")
    
    query = """
        INSERT INTO zoho_authorizations (
            tenant_id,
            refresh_token_encrypted,
            granted_scopes,
            status
        )
        VALUES ($1, $2, $3, $4)

        ON CONFLICT (tenant_id)
        DO UPDATE SET 
            refresh_token_encrypted = EXCLUDED.refresh_token_encrypted,
            granted_scopes = EXCLUDED.granted_scopes,
            status = EXCLUDED.status,
            updated_at = NOW()

        RETURNING
            id,
            tenant_id,
            granted_scopes,
            status,
            created_at,
            updated_at;
    """

    async with pool.acquire() as connection:
        row = await connection.fetchrow(
            query,
            tenant_id,
            refresh_token_encrypted,
            granted_scopes,
            status,
        )
    
    return dict(row)


# 4. Updating Zoho Authorization
async def update_zoho_authorization(
        pool: asyncpg.Pool,
        tenant_id: UUID,
        authorization_id: UUID,
        refresh_token_encrypted: bytes,
        granted_scopes: list[str],
    ) -> dict[str, Any] | None:

    if not refresh_token_encrypted:
        raise ValueError("Encrypted refresh token cannot be empty.")
    
    query = """
        UPDATE zoho_authorizations
        SET
            refresh_token_encrypted = $3,
            granted_scopes = $4,
            status = 'active',
            updated_at = NOW()
        WHERE tenant_id = $1 AND id = $2
        RETURNING
            id,
            tenant_id,
            granted_scopes,
            status,
            created_at,
            updated_at;
    """

    async with pool.acquire() as connection:
        row = await connection.fetchrow(
            query,
            tenant_id,
            authorization_id,
            refresh_token_encrypted,
            granted_scopes,
        )
    
    return dict(row) if row else None


# 5. Retrieve the Active Zoho Authorization for a Tenant
async def get_active_zoho_authorization(
        pool: asyncpg.Pool,
        tenant_id: UUID,
    ) -> dict[str, Any] | None:

    query = """
        SELECT
            id,
            tenant_id,
            granted_scopes,
            status,
            created_at,
            updated_at
        FROM zoho_authorizations
        WHERE tenant_id = $1 AND status = 'active'
        ORDER BY updated_at DESC LIMIT 1;
    """

    async with pool.acquire() as connection:
        row = await connection.fetchrow(query, tenant_id)
    
    return dict(row) if row else None


# 6. Creating Merchant Connection
async def create_merchant_connection(
    pool: asyncpg.Pool,
    tenant_id: UUID,
    authorization_id: UUID,
    zoho_organization_id: str, 
    ) -> dict[str, Any]:
    
    insert_query = """
        INSERT INTO merchant_connections(
            tenant_id,
            provider,
            zoho_organization_id,
            authorization_id,
            status
        )
        SELECT 
            $1,
            'zoho_inventory',
            $3,
            $2, 
            'pending'
        WHERE EXISTS (
            SELECT 1 
            FROM zoho_authorizations
            WHERE id = $2 AND tenant_id = $1 AND status = 'active'
        )
        ON CONFLICT (tenant_id, zoho_organization_id)
        DO NOTHING
        RETURNING
            id,
            tenant_id,
            provider,
            zoho_organization_id,
            authorization_id,
            status,
            created_at,
            updated_at;
    """

    existing_query = """
        SELECT
            id,
            tenant_id,
            provider,
            zoho_organization_id,
            authorization_id,
            status,
            created_at,
            updated_at
        FROM merchant_connections
        WHERE tenant_id = $1 AND zoho_organization_id = $2;
        """


    async with pool.acquire() as connection:
        # Attempt to create a New merchant connection
        row = await connection.fetchrow(
            insert_query,
            tenant_id,
            authorization_id,
            zoho_organization_id,
        )

        # If insertion did not happen, check whether it already exists
        if row is None:
            row = await connection.fetchrow(
                existing_query,
                tenant_id,
                zoho_organization_id,                
            )

    if row is None:
        raise ValueError(
            "Connection was not createed. The authorization may be invalid,"
            "inactive, or the organization may already be connected."
            )

    return dict(row)


# 7. Retrieving Merchant Connection
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
            authorization_id,
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


# 8. Listing all multiple Merchant Connections
async def list_merchant_connections(
        pool: asyncpg.Pool,
        tenant_id: UUID,
    ) -> list[dict[str, Any]]:

    query = """
        SELECT
            id,
            tenant_id,
            provider,
            zoho_organization_id,
            authorization_id,
            status,
            created_at,
            updated_at
        FROM merchant_connections
        WHERE tenant_id = $1
        ORDER BY created_at DESC;
    """

    async with pool.acquire() as connection:
        rows = await connection.fetch(query, tenant_id)
    
    return [dict(row) for row in rows]


# 9. Retrieving Encrypted Refresh token for a Zoho Authorization
async def get_zoho_refresh_token_for_authorization(
        pool: asyncpg.Pool,
        tenant_id: UUID,
        authorization_id: UUID,
    ) -> bytes | None:
    
    query = """
        SELECT refresh_token_encrypted
        FROM zoho_authorizations
        WHERE tenant_id = $1
            AND id = $2
            AND status = 'active';
    """

    async with pool.acquire() as connection:
        row = await connection.fetchrow(
            query,
            tenant_id,
            authorization_id,
        )

    return row["refresh_token_encrypted"] if row else None


# 10. Store Hashed OAuth State with Limited Lifetime
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


# 11. Validate & Consume an Unexpired OAuth State exactly Once
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


# 12. Set the Active Zoho Organization Connection for a tenant & Deactivate any previous active connection
async def set_active_organization_connection(
        pool: asyncpg.Pool,
        tenant_id: UUID,
        connection_id: UUID,
    ) -> bool:

    async with pool.acquire() as connection:
        async with connection.transaction():

            # Lock the tenant row to serialize organization switches.
            tenant = await connection.fetchrow(
                """
                SELECT id
                FROM tenants
                WHERE id = $1
                FOR UPDATE;
                """,
                tenant_id,
            )

            if tenant is None:
                return False
            

            # Verify that the selected connection belongs to this tenant
            # And it is linked to an active Zoho authorization
            selected_connection = await connection.fetchrow(
                """
                SELECT mc.id 
                FROM merchant_connections AS mc
                JOIN zoho_authorizations AS za
                    ON za.id = mc.authorization_id
                    AND za.tenant_id = mc.tenant_id
                WHERE mc.id = $1 
                    AND mc.tenant_id = $2
                    AND mc.status IN ('pending', 'active', 'inactive')
                    AND za.status = 'active';
                """,
                connection_id,
                tenant_id
            )

            if selected_connection is None:
                return False
            

            # Deactivate the previously selected & active connection
            await connection.execute(
                """
                UPDATE merchant_connections
                SET status = 'inactive',
                    updated_at = NOW()
                WHERE tenant_id = $1
                    AND status = 'active'
                    AND id != $2;
                """,
                tenant_id,
                connection_id,
            )


            # Activate the newly selected or created connection
            await connection.execute(
                """
                UPDATE merchant_connections
                SET status = 'active',
                    updated_at = NOW()
                WHERE id = $1
                    AND tenant_id = $2;
                """,
                connection_id,
                tenant_id,
            )


            # Update the tenant's active connection pointer
            await connection.execute(
                """
                UPDATE tenants
                SET active_organization_connection_id = $2
                WHERE id = $1;
                """,
                tenant_id,
                connection_id,
            )
    
    return True

