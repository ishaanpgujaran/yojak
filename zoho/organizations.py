import asyncpg

from uuid import UUID

from typing import Any

from zoho.token_manager import get_access_token
from zoho.client import list_organizations


# Discover Zoho Organizations through Authorization
async def discover_organizations(
        pool: asyncpg.Pool,
        tenant_id: UUID,
        authorization_id: UUID,
    ) -> list[dict[str, Any]]:

    """Discover Zoho organizations accessible through an authorization."""

    # 1. Obtain a valid access token through the Token Manager
    access_token = await get_access_token(
        pool, 
        tenant_id,
        authorization_id,
    )

    # 2. Retrieve organizations from Zoho
    response_data = await list_organizations(access_token)

    # 3. Extract the organizations
    organizations = response_data["organizations"]

    return organizations
