from fastmcp import FastMCP
from fastmcp.server.auth.providers.workos import AuthKitProvider

from app.config import settings

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from typing import Any
from app.database import lifespan_database


from fastmcp.server.context import Context
from fastmcp.server.dependencies import get_access_token
from app.repositories import get_or_create_tenant

from  app import runtime

from app.database_errors import DATABASE_AVAILABILITY_ERRORS
from app.services.zoho_oauth import (
    connect_zoho_service,
    ZohoAuthorizationLookupError,
    ZohoAuthorizationValidationError,
    ZohoOAuthInitiationError,
)

# Configure database pool lifecycle
@asynccontextmanager
async def mcp_lifespan(server: FastMCP) -> AsyncIterator[dict[str, Any]]:
    async with lifespan_database() as pool:
        runtime.database_pool = pool

        try:
            yield {"pool": pool}
        finally:
            runtime.database_pool = None


# Configure WorkOS AuthKit Authentication
workos_auth = AuthKitProvider (
    authkit_domain = settings.workos_authkit_domain,
    base_url = "http://localhost:8000",
    resource_base_url = "http://localhost:8000/mcp",
)

# Create MCP Server
mcp = FastMCP (
    name = "Yojak",
    auth = workos_auth,
    lifespan = mcp_lifespan,
)


# Helper function to get WorkOS user id of authenticated user
async def get_authenticated_tenant(ctx: Context) -> dict:
    """Resolve the tenant belnging to the authenticated WorkOS user"""

    token = get_access_token()

    if token is None:
        raise PermissionError("Authentication is Required!")
    
    workos_user_id = token.subject

    if not isinstance(workos_user_id, str) or not workos_user_id.strip():
        raise PermissionError("Authenticated user identity is missing.")
    
    pool = ctx.lifespan_context.get("pool")

    if pool is None:
        raise RuntimeError("Database connection pool is unavailable")
    
    return await get_or_create_tenant(pool, workos_user_id,)


# Tool 1 - Diagnostic Tool
@mcp.tool
def yojak_status() -> dict:
    # Docstring describes the tool to the client
    """Return the current status of the Yojak Application """ 

    return {
        "application" : "Yojak",
        "status" : "OK",
    }


# Tool 2 - Initiate or Reuse Zoho Authorization
@mcp.tool
async def yojak_connect_zoho(ctx: Context) -> dict:
    """
    Connect Yojak with the authenticated user's Zoho Inventory account.

    Reuses an existing valid Zoho authorization when possible.
    Otherwise, initiates a new Zoho OAuth consent flow.
    """

    # 1. Resolve the authenticated WorkOS user to a Yojak tenant.
    try:
        tenant = await get_authenticated_tenant(ctx)
    
    except DATABASE_AVAILABILITY_ERRORS as error:
        raise RuntimeError(
            "Yojak's database is temporarily unavailable. Please try again later."
        ) from error


    # 2. Retrieve the shared database pool from the MCP lifespan.
    pool = ctx.lifespan_context.get("pool")

    if pool is None:
        raise RuntimeError("Database connection pool is unavailable.")


    # 3. Delegate Zoho authorization logic to the shared service.
    try:
        result = await connect_zoho_service(
            pool,
            tenant["id"],
        )
    
    except DATABASE_AVAILABILITY_ERRORS as error:
        raise RuntimeError(
            "Yojak's database is temporarily unavailable. Please try again later."
        ) from error
    
    except ZohoAuthorizationLookupError as error:
        raise RuntimeError(
            "Unable to retrieve the existing Zoho authorization."
        ) from error

    except ZohoAuthorizationValidationError as error:
        raise RuntimeError(
            "Unable to validate the existing Zoho authorization."
        ) from error

    except ZohoOAuthInitiationError as error:
        raise RuntimeError(
            "Unable to initiate Zoho authorization."
        ) from error


    # 4. Translate the service result into an MCP-friendly response.
    if result["status"] == "authorization_reused":
        return {
            "status": "authorization_reused",
            "provider": "zoho_inventory",
            "message": (
                "An existing valid Zoho authorization was found."
            ),
            "next_step": (
                "Discover the Zoho organizations available to this account."
            ),
        }

    return {
        "status": "authorization_required",
        "provider": "zoho_inventory",
        "message": (
            "Zoho authorization is required. Open the authorization URL "
            "in a browser and complete the consent process."
        ),
        "authorization_url": result["authorization_url"],
        "next_step": (
            "Complete Zoho authorization in the browser. "
            "After the callback confirms success, discover your organizations."
        ),
    }

