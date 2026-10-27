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


# Configure database pool lifecycle
@asynccontextmanager
async def mcp_lifespan(server: FastMCP) -> AsyncIterator[dict[str, Any]]:
    async with lifespan_database() as pool:
        yield {"pool": pool}


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


# Helper fnction to get WorkOS user id of authenticated user
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