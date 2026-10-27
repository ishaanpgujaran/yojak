from uuid import UUID
import pytest

from app.database import lifespan_database
from app.repositories import (
    create_merchant_connection,
    get_or_create_tenant,
    get_merchant_connection,
    get_tenant,
)

import asyncio


@pytest.mark.anyio
async def test_tenant_and_merchant_connection_operations():
    async with lifespan_database() as pool:
        tenant_id: UUID | None = None
        other_tenant_id: UUID | None = None

        try:
            # 1. Create or Retrieve Tenant
            workos_user_id = "test_workos_user_001"

            tenant = await get_or_create_tenant(pool, workos_user_id)
            tenant_id = tenant["id"]
            
            assert tenant["workos_user_id"] == workos_user_id
            assert tenant["name"].startswith("Tenant ")
            assert len(tenant["name"]) == len("Tenant ") + 8
            assert isinstance(tenant_id, UUID)


            # 2. Repeated get or create calls must return same tenant
            retrieved_tenant = await get_or_create_tenant(pool, workos_user_id)

            assert retrieved_tenant["id"] == tenant_id
            assert retrieved_tenant["name"] == tenant["name"] 
            

            # 3. Retrieve the tenant using internal tenant_id UUID
            stored_tenant = await get_tenant(pool, tenant_id,)

            assert stored_tenant is not None
            assert stored_tenant["id"] == tenant_id


            # 4. Different WorkOS user must recieve different tenant
            other_tenant = await get_or_create_tenant(pool, "test_workos_user_002",)
            other_tenant_id = other_tenant["id"]

            assert other_tenant_id != tenant_id
            assert other_tenant["workos_user_id"] == "test_workos_user_002"
    

            # 5. Create a Zoho Inventory Connection
            merchant_connection = await create_merchant_connection(
                pool,
                tenant_id,
                "test-org-001",
                [
                    "ZohoInventory.items.READ",
                    "ZohoInventory.salesorders.READ",
                ],
            )

            connection_id = merchant_connection["id"]

            assert merchant_connection["tenant_id"] == tenant_id
            assert merchant_connection["provider"] == "zoho_inventory"
            assert merchant_connection["status"] == "pending"


            # 6. Retrieve Connection using its tenant & connection IDs.
            retrieved_connection = await get_merchant_connection(pool, tenant_id,connection_id,)

            assert retrieved_connection is not None
            assert retrieved_connection["id"] == connection_id


            # 7. A different tenatn ID must not retrieve this connection
            unauthorized_lookup = await get_merchant_connection(pool, other_tenant_id, connection_id,)

            assert unauthorized_lookup is None
        
        finally:
            # Clean up test records
            async with pool.acquire() as connection:
                if tenant_id is not None:
                    await connection.execute(
                        """
                        DELETE FROM tenants
                        WHERE id = $1;
                        """,
                        tenant_id,
                    )
                if other_tenant_id is not None:
                    await connection.execute(
                        """
                        DELETE FROM tenants 
                        WHERE id = $1;
                        """,
                        other_tenant_id,
                    )


@pytest.mark.anyio 
async def test_concurrent_tenant_creation():
    async with lifespan_database() as pool:
        workos_user_id = "test_concurrent_workos_user"
        tenant_id = None
    
        try:
            # Make multiple requests for the smae WorkOS user concurrently
            tenants = await asyncio.gather(
                *[
                    get_or_create_tenant(pool, workos_user_id)
                    for _ in range(5)
                ]
            )

            # Every request must return same tenant ID
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
                        """
                        DELETE FROM tenants
                        WHERE id = $1;
                        """,
                        tenant_id,
                    )    