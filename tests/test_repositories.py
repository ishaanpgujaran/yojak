from uuid import UUID
import asyncio

import pytest

from app.database import lifespan_database
from app.repositories import (
    create_merchant_connection,
    create_zoho_authorization,
    get_or_create_tenant,
    get_merchant_connection,
    get_tenant,
    list_merchant_connections,
    get_zoho_refresh_token_for_connection,
    update_zoho_authorization,
)

from zoho.crypto import encrypt_refresh_token


@pytest.mark.anyio
async def test_tenant_and_merchant_connection_operations():
    async with lifespan_database() as pool:
        tenant_id: UUID | None = None
        other_tenant_id: UUID | None = None

        try:
            # 1. Create a tenant
            workos_user_id = "test_workos_user_001"

            tenant = await get_or_create_tenant(pool, workos_user_id)
            tenant_id = tenant["id"]

            assert tenant["workos_user_id"] == workos_user_id
            assert tenant["name"].startswith("Tenant ")
            assert len(tenant["name"]) == len("Tenant ") + 8
            assert isinstance(tenant_id, UUID)

            # 2. Repeated calls must return the same tenant
            retrieved_tenant = await get_or_create_tenant(
                pool,
                workos_user_id,
            )

            assert retrieved_tenant["id"] == tenant_id
            assert retrieved_tenant["name"] == tenant["name"]

            # 3. Retrieve the tenant by UUID
            stored_tenant = await get_tenant(pool, tenant_id)

            assert stored_tenant is not None
            assert stored_tenant["id"] == tenant_id
            assert stored_tenant["active_organization_connection_id"] is None

            # 4. A different WorkOS user must receive a different tenant
            other_tenant = await get_or_create_tenant(
                pool,
                "test_workos_user_002",
            )
            other_tenant_id = other_tenant["id"]

            assert other_tenant_id != tenant_id
            assert other_tenant["workos_user_id"] == "test_workos_user_002"

            # 5. Create a shared Zoho authorization
            test_refresh_token = "test-refresh-token"
            encrypted_refresh_token = encrypt_refresh_token(
                test_refresh_token
            )

            authorization = await create_zoho_authorization(
                pool,
                tenant_id,
                encrypted_refresh_token,
                [
                    "ZohoInventory.items.READ",
                    "ZohoInventory.salesorders.READ",
                    "ZohoInventory.settings.READ",
                ],
            )

            authorization_id = authorization["id"]

            assert authorization["tenant_id"] == tenant_id
            assert authorization["status"] == "active"
            assert "refresh_token_encrypted" not in authorization

            # 6. Create a merchant connection using the authorization
            merchant_connection = await create_merchant_connection(
                pool,
                tenant_id,
                authorization_id,
                "test-org-001",
            )

            connection_id = merchant_connection["id"]

            assert merchant_connection["tenant_id"] == tenant_id
            assert merchant_connection["provider"] == "zoho_inventory"
            assert merchant_connection["zoho_organization_id"] == "test-org-001"
            assert merchant_connection["authorization_id"] == authorization_id
            assert merchant_connection["status"] == "active"
            assert "refresh_token_encrypted" not in merchant_connection
            assert "granted_scopes" not in merchant_connection

            # 7. Retrieve the merchant connection
            retrieved_connection = await get_merchant_connection(
                pool,
                tenant_id,
                connection_id,
            )

            assert retrieved_connection is not None
            assert retrieved_connection["id"] == connection_id
            assert retrieved_connection["authorization_id"] == authorization_id

            # 8. A different tenant must not retrieve this connection
            unauthorized_lookup = await get_merchant_connection(
                pool,
                other_tenant_id,
                connection_id,
            )

            assert unauthorized_lookup is None

            # 9. List the tenant's merchant connections
            connections = await list_merchant_connections(
                pool,
                tenant_id,
            )

            assert len(connections) == 1
            assert connections[0]["id"] == connection_id

            # 10. Another tenant must not see this connection in its list
            other_connections = await list_merchant_connections(
                pool,
                other_tenant_id,
            )

            assert other_connections == []

            # 11. Retrieve the encrypted refresh token through the connection
            retrieved_token = await get_zoho_refresh_token_for_connection(
                pool,
                tenant_id,
                connection_id,
            )

            assert retrieved_token == encrypted_refresh_token
            assert isinstance(retrieved_token, bytes)

            # 12. Another tenant must not retrieve the token
            unauthorized_token = await get_zoho_refresh_token_for_connection(
                pool,
                other_tenant_id,
                connection_id,
            )

            assert unauthorized_token is None

            # 13. An unknown connection must return None
            unknown_connection_token = (
                await get_zoho_refresh_token_for_connection(
                    pool,
                    tenant_id,
                    UUID("00000000-0000-0000-0000-000000000001"),
                )
            )

            assert unknown_connection_token is None

            # 14. Update the shared authorization
            updated_plaintext_token = "updated-test-refresh-token"
            updated_encrypted_token = encrypt_refresh_token(
                updated_plaintext_token
            )

            updated_authorization = await update_zoho_authorization(
                pool,
                tenant_id,
                authorization_id,
                updated_encrypted_token,
                [
                    "ZohoInventory.items.READ",
                    "ZohoInventory.salesorders.READ",
                ],
            )

            assert updated_authorization is not None
            assert updated_authorization["id"] == authorization_id
            assert updated_authorization["status"] == "active"
            assert updated_authorization["granted_scopes"] == [
                "ZohoInventory.items.READ",
                "ZohoInventory.salesorders.READ",
            ]

            # The connection must now resolve to the updated encrypted token
            token_after_update = await get_zoho_refresh_token_for_connection(
                pool,
                tenant_id,
                connection_id,
            )

            assert token_after_update == updated_encrypted_token

            # 15. Updating a nonexistent authorization must return None
            missing_authorization = await update_zoho_authorization(
                pool,
                tenant_id,
                UUID("00000000-0000-0000-0000-000000000002"),
                updated_encrypted_token,
                ["ZohoInventory.items.READ"],
            )

            assert missing_authorization is None

        finally:
            # Deleting tenants cascades to their authorizations and connections
            async with pool.acquire() as connection:
                if tenant_id is not None:
                    await connection.execute(
                        "DELETE FROM tenants WHERE id = $1;",
                        tenant_id,
                    )

                if other_tenant_id is not None:
                    await connection.execute(
                        "DELETE FROM tenants WHERE id = $1;",
                        other_tenant_id,
                    )


@pytest.mark.anyio
async def test_concurrent_tenant_creation():
    async with lifespan_database() as pool:
        workos_user_id = "test_concurrent_workos_user"
        tenant_id = None

        try:
            # Make multiple requests for the same WorkOS user concurrently
            tenants = await asyncio.gather(
                *[
                    get_or_create_tenant(pool, workos_user_id)
                    for _ in range(5)
                ]
            )

            # Every request must return the same tenant ID
            tenant_ids = [tenant["id"] for tenant in tenants]

            assert len(set(tenant_ids)) == 1

            tenant_id = tenant_ids[0]

            # Verify that only one tenant exists for this WorkOS user
            async with pool.acquire() as connection:
                count = await connection.fetchval(
                    """
                    SELECT COUNT(*)
                    FROM tenants
                    WHERE workos_user_id = $1;
                    """,
                    workos_user_id,
                )

            assert count == 1

        finally:
            # Clean up the test tenant
            if tenant_id is not None:
                async with pool.acquire() as connection:
                    await connection.execute(
                        "DELETE FROM tenants WHERE id = $1;",
                        tenant_id,
                    )