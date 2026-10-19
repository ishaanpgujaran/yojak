from uuid import UUID
import pytest

from app.database import lifespan_database
from app.repositories import (
    create_merchant_connection,
    create_tenant,
    get_merchant_connection,
    get_tenant,
)

@pytest.mark.anyio
async def test_tenant_and_merchant_connection_operations():
    async with lifespan_database() as pool:
        tenant_id: UUID | NOne = None

        try:
            # 1. Create Tenant
            tenant = await create_tenant(pool, "Yojak Test Merchant",)
            tenant_id = tenant["id"]
            
            assert tenant["name"] == "Yojak Test Merchant"
            assert isinstance(tenant_id, UUID)


            # 2. Retrieve the tenant
            retrieved_tenant = await get_tenant(pool, tenant_id,)

            assert retrieved_tenant is not None
            assert retrieved_tenant["id"] == tenant_id


            # Create a Zoho Inventory Connection
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

            # 4. Retrieve Connection using its tenant & connection IDs.
            retrieved_connection = await get_merchant_connection(pool, tenant_id,connection_id,)

            assert retrieved_connection is not None
            assert retrieved_connection["id"] == connection_id

            # 5. A different tenatn ID must not retrieve this connection
            other_tenat_id = UUID(
                "00000000-0000-0000-0000-000000000001"
            )

            unauthorized_lookup = await get_merchant_connection(pool, other_tenat_id, connection_id,)

            assert unauthorized_lookup is None
        
        finally:
            # Clean up test records
            if tenant_id is not None:
                async with pool.acquire() as connection:
                    await connection.execute(
                        """
                        DELETE FROM tenants
                        WHERE id = $1;
                        """,
                        tenant_id,
                    )
