from uuid import UUID
import asyncio

import pytest

import asyncpg

from app.database import lifespan_database
from app.repositories import (
    create_merchant_connection,
    create_zoho_authorization,
    get_or_create_tenant,
    get_merchant_connection,
    get_tenant,
    list_merchant_connections,
    get_zoho_refresh_token_for_authorization,
    update_zoho_authorization,
    get_active_zoho_authorization,
    set_active_organization_connection,
)

from zoho.crypto import encrypt_refresh_token


@pytest.mark.anyio
async def test_tenant_and_merchant_connection_operations():
    async with lifespan_database() as pool:
        tenant_id: UUID | None = None
        other_tenant_id: UUID | None = None
        third_tenant_id: UUID | None = None

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

            # 6. Retrieve the tenant's active Zoho authorization
            active_authorization = await get_active_zoho_authorization(
                pool,
                tenant_id,
            )

            assert active_authorization is not None
            assert active_authorization["id"] == authorization_id
            assert active_authorization["tenant_id"] == tenant_id
            assert active_authorization["status"] == "active"
            assert "refresh_token_encrypted" not in active_authorization

            # 7. Another tenant must not retrieve this authorization
            other_active_authorization = await get_active_zoho_authorization(
                pool,
                other_tenant_id,
            )

            assert other_active_authorization is None

            #8. A tenant without an authorization must recieve None
            third_tenant = await get_or_create_tenant(
                pool,
                "tets_workos_user_003",
            )

            third_tenant_id = third_tenant["id"]

            missing_authorization = await get_active_zoho_authorization(
                pool,
                third_tenant_id,
            )

            assert missing_authorization is None

            # 9. Create a merchant connection using the authorization
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
            assert merchant_connection["status"] == "pending"
            assert "refresh_token_encrypted" not in merchant_connection
            assert "granted_scopes" not in merchant_connection

            # 10. Creating the same merchant connection again must return the existing connection
            duplicate_connection = await create_merchant_connection(
                pool,
                tenant_id,
                authorization_id,
                "test-org-001",
            )

            assert duplicate_connection["id"] == connection_id
            assert duplicate_connection["tenant_id"] == tenant_id
            assert duplicate_connection["zoho_organization_id"] == "test-org-001"

            # Verify that only one connection exists for this tenant & organization
            async with pool.acquire() as connection:
                connection_count = await connection.fetchval(
                    """
                    SELECT COUNT(*)
                    FROM merchant_connections
                    WHERE tenant_id = $1 AND zoho_organization_id = $2;
                    """,
                    tenant_id,
                    "test-org-001",
                )
            
            assert connection_count == 1

            # 11. Activate the merchant connection & Retrieve the merchant connection
            activation_result = await set_active_organization_connection(
                pool,
                tenant_id,
                connection_id,
            )

            assert activation_result is True

            # Verify that the connection is now active
            retrieved_active_connection = await get_merchant_connection(
                pool,
                tenant_id,
                connection_id,
            )

            assert retrieved_active_connection is not None
            assert retrieved_active_connection["id"] == connection_id
            assert retrieved_active_connection["authorization_id"] == authorization_id
            assert retrieved_active_connection["status"] == "active"

            # Verify that the tenant points to this active connection
            updated_tenant = await get_tenant(pool, tenant_id,)

            assert updated_tenant is not None
            assert updated_tenant["active_organization_connection_id"] == connection_id

            # 12. A different tenant must not retrieve this connection
            unauthorized_lookup = await get_merchant_connection(
                pool,
                other_tenant_id,
                connection_id,
            )

            assert unauthorized_lookup is None

            # 13. List the tenant's merchant connections
            connections = await list_merchant_connections(
                pool,
                tenant_id,
            )

            assert len(connections) == 1
            assert connections[0]["id"] == connection_id

            # 14. Another tenant must not see this connection in its list
            other_connections = await list_merchant_connections(
                pool,
                other_tenant_id,
            )

            assert other_connections == []

            # 15. Retrieve the encrypted refresh token through the authorization
            retrieved_token = await get_zoho_refresh_token_for_authorization(
                pool,
                tenant_id,
                authorization_id,
            )

            assert retrieved_token == encrypted_refresh_token
            assert isinstance(retrieved_token, bytes)

            # 16. Another tenant must not retrieve the token
            unauthorized_token = await get_zoho_refresh_token_for_authorization(
                pool,
                other_tenant_id,
                authorization_id,
            )

            assert unauthorized_token is None

            # 17. An unknown authorization must return None
            unknown_authorization_token = (
                await get_zoho_refresh_token_for_authorization(
                    pool,
                    tenant_id,
                    UUID("00000000-0000-0000-0000-000000000001"),
                )
            )

            assert unknown_authorization_token is None

            # 18. Update the shared authorization
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

            # The authorization must now resolve to the updated encrypted token
            token_after_update = await get_zoho_refresh_token_for_authorization(
                pool,
                tenant_id,
                authorization_id,
            )

            assert token_after_update == updated_encrypted_token

            # 19. Updating a nonexistent authorization must return None
            missing_authorization = await update_zoho_authorization(
                pool,
                tenant_id,
                UUID("00000000-0000-0000-0000-000000000002"),
                updated_encrypted_token,
                ["ZohoInventory.items.READ"],
            )

            assert missing_authorization is None

            # 20. Create a second organization connection
            # The new connection should initially have pending status
            second_merchant_connection = await create_merchant_connection(
                pool,
                tenant_id,
                authorization_id,
                "test-org-002",
            )

            second_connection_id = second_merchant_connection["id"]

            assert second_merchant_connection["tenant_id"] == tenant_id
            assert second_merchant_connection["zoho_organization_id"] == "test-org-002"
            assert second_merchant_connection["status"] == "pending"
            assert second_connection_id != connection_id

            # 21. Switc from the first organization to the second organization
            # The first connection should become inactive 
            # The second connection should become active
            second_activation_result = await set_active_organization_connection(
                pool,
                tenant_id,
                second_connection_id,
            )

            assert second_activation_result is True

            # 22. Verify the connection statuses after switching
            first_connection_after_switch = await get_merchant_connection(
                pool,
                tenant_id,
                connection_id,
            )

            second_connection_after_switch = await get_merchant_connection(
                pool,
                tenant_id,
                second_connection_id,
            )

            assert first_connection_after_switch is not None
            assert second_connection_after_switch is not None
            assert first_connection_after_switch["status"] == "inactive"
            assert second_connection_after_switch["status"] == "active"

            # 23. Verify that the tenant points to the second organization
            updated_tenant_after_switch = await get_tenant(pool, tenant_id,)

            assert updated_tenant_after_switch is not None
            assert (
                updated_tenant_after_switch["active_organization_connection_id"] == second_connection_id
            )

            # 24. Switch back to the first organization 
            # The existing connection should be reused and reactivated
            switch_back_result = await set_active_organization_connection(
                pool,
                tenant_id,
                connection_id,
            )

            assert switch_back_result is True

            # 25. Verify the connection statuses after switching back
            first_connection_after_switch_back = await get_merchant_connection(
                pool,
                tenant_id,
                connection_id,
            )

            second_connection_after_switch_back = await get_merchant_connection(
                pool,
                tenant_id,
                second_connection_id,
            )

            assert first_connection_after_switch_back is not None
            assert second_connection_after_switch_back is not None
            assert first_connection_after_switch_back["status"] == "active"
            assert second_connection_after_switch_back["status"] == "inactive"

            # 26. Verify that the tenant now points back to the first organization 
            updated_tenant_after_switch_back = await get_tenant(pool, tenant_id,)

            assert updated_tenant_after_switch_back is not None
            assert(
                updated_tenant_after_switch_back["active_organization_connection_id"] == connection_id
            ) 

            # 27. Verify that only one active connection exists for this tenant
            async with pool.acquire() as connection:
                active_connection_count = await connection.fetchval(
                    """
                    SELECT COUNT(*)
                    FROM merchant_connections
                    WHERE tenant_id = $1
                    AND status = 'active';
                    """,
                    tenant_id,
                )

            assert active_connection_count == 1

            # 28. An inactive Zoho authorization must prevent organization activation
            # Mark the tenant's Zoho authorization as inactive.
            async with pool.acquire() as connection:
                await connection.execute(
                    """
                    UPDATE zoho_authorizations
                    SET status = 'revoked'
                    WHERE id = $1 AND tenant_id = $2;
                    """,
                    authorization_id,
                    tenant_id,
                )

            # Attempt to activate the second organization.
            # Its authorization is no longer active, so this must fail.
            inactive_authorization_result = (
                await set_active_organization_connection(
                    pool,
                    tenant_id,
                    second_connection_id,
                )
            )

            assert inactive_authorization_result is False

            # Verify that the existing active connection remains unchanged.
            first_connection_after_failed_activation = (
                await get_merchant_connection(
                    pool,
                    tenant_id,
                    connection_id,
                )
            )

            second_connection_after_failed_activation = (
                await get_merchant_connection(
                    pool,
                    tenant_id,
                    second_connection_id,
                )
            )

            assert first_connection_after_failed_activation["status"] == "active"
            assert second_connection_after_failed_activation["status"] == "inactive"

            # The tenant's active pointer must also remain unchanged.
            tenant_after_failed_activation = await get_tenant(
                pool,
                tenant_id,
            )

            assert (
                tenant_after_failed_activation["active_organization_connection_id"]
                == connection_id
            )

            # 29. Restore the Zoho authorization for the rollback test
            # The previous test marked it as revoked.
            async with pool.acquire() as connection:
                await connection.execute(
                    """
                    UPDATE zoho_authorizations
                    SET status = 'active'
                    WHERE id = $1 AND tenant_id = $2;
                    """,
                    authorization_id,
                    tenant_id,
                )

            # 30. Create a temporary PostgreSQL trigger to simulate a failure
            # when updating the tenant's active organization connection.
            async with pool.acquire() as connection:

                # Remove any leftover trigger/function from a previous
                # interrupted test run.
                await connection.execute(
                    """
                    DROP TRIGGER IF EXISTS test_active_pointer_failure
                    ON tenants;
                    """
                )

                await connection.execute(
                    """
                    DROP FUNCTION IF EXISTS test_fail_active_pointer_update();
                    """
                )

                # Create a function that deliberately raises an exception.
                await connection.execute(
                    """
                    CREATE FUNCTION test_fail_active_pointer_update()
                    RETURNS TRIGGER AS $$
                    BEGIN
                        RAISE EXCEPTION
                            'Simulated tenant pointer update failure';
                    END;
                    $$ LANGUAGE plpgsql;
                    """
                )

                # Execute the function whenever the active connection pointer
                # on a tenant is updated.
                await connection.execute(
                    """
                    CREATE TRIGGER test_active_pointer_failure
                    BEFORE UPDATE OF active_organization_connection_id
                    ON tenants
                    FOR EACH ROW
                    EXECUTE FUNCTION test_fail_active_pointer_update();
                    """
                )

            # 31. Attempt to switch to the second organization.
            # The connection-status updates will execute first, but the
            # tenant-pointer update will fail because of our trigger.
            # The entire transaction should therefore be rolled back.
            with pytest.raises(asyncpg.PostgresError):
                await set_active_organization_connection(
                    pool,
                    tenant_id,
                    second_connection_id,
                )

            # 32. Verify that the connection statuses were rolled back.
            first_connection_after_rollback = await get_merchant_connection(
                pool,
                tenant_id,
                connection_id,
            )

            second_connection_after_rollback = await get_merchant_connection(
                pool,
                tenant_id,
                second_connection_id,
            )

            assert first_connection_after_rollback is not None
            assert second_connection_after_rollback is not None

            assert first_connection_after_rollback["status"] == "active"
            assert second_connection_after_rollback["status"] == "inactive"

            # 33. Verify that the tenant's active connection pointer
            # still references the first organization.
            tenant_after_rollback = await get_tenant(
                pool,
                tenant_id,
            )

            assert tenant_after_rollback is not None
            assert (
                tenant_after_rollback["active_organization_connection_id"]
                == connection_id
            )


        finally:
            # Deleting tenants cascades to their authorizations and connections
            async with pool.acquire() as connection:
                # Remove the temporary triggers & function used by rollback test
                await connection.execute(
                    """
                    DROP TRIGGER IF EXISTS test_active_pointer_failure
                    ON tenants;
                    """
                )

                await connection.execute(
                    """
                    DROP FUNCTION IF EXISTS test_fail_active_pointer_update();
                    """
                )

                # Deleting tenants cascades to their authorizations and connections
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

                if third_tenant_id is not None:
                    await connection.execute(
                        "DELETE FROM tenants WHERE id = $1;",
                        third_tenant_id,
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


@pytest.mark.asyncio
async def test_create_zoho_authorization_updates_existing_record():
    async with lifespan_database() as pool:

        try:
            tenant = await get_or_create_tenant(
                pool,
                "workos_user_zoho_reconnect_test",
            )
            tenant_id = tenant["id"]

            first_token = b"encrypted_refresh_token_1"
            first_scopes = [
                "ZohoInventory.items.READ",
                "ZohoInventory.salesorders.READ",
            ]

            first_authorization = await create_zoho_authorization(
                pool,
                tenant_id,
                first_token,
                first_scopes,
            )

            assert first_authorization is not None
            assert first_authorization["tenant_id"] == tenant_id
            assert first_authorization["status"] == "active"

            second_token = b"encrypted_refresh_token_2"
            second_scopes = [
                "ZohoInventory.items.READ",
                "ZohoInventory.salesorders.READ",
                "ZohoInventory.settings.READ",
            ]

            second_authorization = await create_zoho_authorization(
                pool,
                tenant_id,
                second_token,
                second_scopes,
            )

            assert second_authorization is not None

            # The existing authorization record must be reused.
            assert second_authorization["id"] == first_authorization["id"]

            # The original creation timestamp must remain unchanged.
            assert second_authorization["created_at"] == first_authorization["created_at"]

            # The authorization details must be updated.
            assert second_authorization["granted_scopes"] == second_scopes
            assert second_authorization["status"] == "active"

            # Verify the encrypted refresh token was actually replaced.
            stored_token = await get_zoho_refresh_token_for_authorization(
                pool,
                tenant_id,
                second_authorization["id"],
            )

            assert stored_token == second_token
        finally:
            # Clean up the test tenant
            if tenant_id is not None:
                async with pool.acquire() as connection:
                    await connection.execute(
                        "DELETE FROM tenants WHERE id = $1;",
                        tenant_id,
                    )


@pytest.mark.asyncio
async def test_create_zoho_authorization_without_refresh_token():
    async with lifespan_database() as pool:
        tenant_id = None

        try:
            tenant = await get_or_create_tenant(
                pool,
                "workos_user_missing_refresh_token",
            )
            tenant_id = tenant["id"]

            result = await create_zoho_authorization(
                pool,
                tenant_id,
                None,
                ["ZohoInventory.items.READ"],
            )

            assert result is None

        finally:
            if tenant_id is not None:
                async with pool.acquire() as connection:
                    await connection.execute(
                        "DELETE FROM tenants WHERE id = $1;",
                        tenant_id,
                    )


@pytest.mark.asyncio
async def test_create_zoho_authorization_preserves_existing_token_when_none_received():
    async with lifespan_database() as pool:
        tenant_id = None

        try:
            tenant = await get_or_create_tenant(
                pool,
                "workos_user_preserve_refresh_token",
            )
            tenant_id = tenant["id"]

            original_token = b"original_encrypted_refresh_token"

            original_authorization = await create_zoho_authorization(
                pool,
                tenant_id,
                original_token,
                ["ZohoInventory.items.READ"],
            )

            updated_scopes = [
                "ZohoInventory.items.READ",
                "ZohoInventory.salesorders.READ",
                "ZohoInventory.settings.READ",
            ]

            updated_authorization = await create_zoho_authorization(
                pool,
                tenant_id,
                None,
                updated_scopes,
            )

            assert updated_authorization is not None

            # The existing authorization record must be reused.
            assert updated_authorization["id"] == original_authorization["id"]

            # The authorization must remain active.
            assert updated_authorization["status"] == "active"

            # The scopes must be updated.
            assert updated_authorization["granted_scopes"] == updated_scopes

            # The original encrypted refresh token must be preserved.
            stored_token = await get_zoho_refresh_token_for_authorization(
                pool,
                tenant_id,
                updated_authorization["id"],
            )

            assert stored_token == original_token

        finally:
            if tenant_id is not None:
                async with pool.acquire() as connection:
                    await connection.execute(
                        "DELETE FROM tenants WHERE id = $1;",
                        tenant_id,
                    )



@pytest.mark.asyncio
async def test_create_zoho_authorization_does_not_reactivate_revoked_authorization_without_new_token():
    async with lifespan_database() as pool:
        tenant_id = None

        try:
            tenant = await get_or_create_tenant(
                pool,
                "workos_user_revoked_authorization",
            )
            tenant_id = tenant["id"]

            original_token = b"revoked_encrypted_refresh_token"

            original_authorization = await create_zoho_authorization(
                pool,
                tenant_id,
                original_token,
                ["ZohoInventory.items.READ"],
            )

            authorization_id = original_authorization["id"]

            # Simulate a revoked authorization.
            async with pool.acquire() as connection:
                await connection.execute(
                    """
                    UPDATE zoho_authorizations
                    SET status = 'revoked'
                    WHERE id = $1 AND tenant_id = $2;
                    """,
                    authorization_id,
                    tenant_id,
                )

            result = await create_zoho_authorization(
                pool,
                tenant_id,
                None,
                ["ZohoInventory.items.READ"],
            )

            # The update must be rejected.
            assert result is None

            # The authorization must remain revoked.
            async with pool.acquire() as connection:
                stored_authorization = await connection.fetchrow(
                    """
                    SELECT id, status, refresh_token_encrypted
                    FROM zoho_authorizations
                    WHERE id = $1 AND tenant_id = $2;
                    """,
                    authorization_id,
                    tenant_id,
                )

            assert stored_authorization is not None
            assert stored_authorization["status"] == "revoked"
            assert stored_authorization["refresh_token_encrypted"] == original_token

        finally:
            if tenant_id is not None:
                async with pool.acquire() as connection:
                    await connection.execute(
                        "DELETE FROM tenants WHERE id = $1;",
                        tenant_id,
                    )
