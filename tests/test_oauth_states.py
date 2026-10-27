from uuid import UUID
import pytest

from app.database import lifespan_database
from app.repositories import (
    consume_oauth_state,
    create_oauth_state,
    get_or_create_tenant,
)

@pytest.mark.anyio
async def test_oauth_state_can_be_consumed_only_once():
    async with lifespan_database() as pool:
        tenant_id: UUID | None = None

        try:
            # Create a tenant with a vaid WorkOS user ID
            tenant = await get_or_create_tenant(pool, "test-workos-user-oauth-state-001")

            tenant_id = tenant["id"]

            # Create an OAuth state
            state = "test-oauth-state-unique-001"

            await create_oauth_state(
                    pool,
                    state,
                    tenant_id,
                )

            # First Consumption should succeed
            consumed_tenant_id = await consume_oauth_state(
                    pool,
                    state,
                )

            assert consumed_tenant_id == tenant_id

            # Second Consumption should fail
            second_attempt = await consume_oauth_state(
                    pool,
                    state,
                )

            assert second_attempt is None
        
        finally:
            if tenant_id is not None:
                async with pool.acquire() as connection:
                    await connection.execute(
                        """
                            DELETE FROM tenants
                            WHERE id = $1;
                        """,
                        tenant_id
                    )