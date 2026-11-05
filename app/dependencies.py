from typing import Any
import asyncpg
from fastapi import HTTPException, Request

from app.repositories import get_or_create_tenant
from app import runtime

from yojak_mcp.server import workos_auth


# Get tenant by WorkOS authentication
async def get_authenticated_tenant_context(
        request: Request,
    ) -> dict[str, Any]:

    # 1. Extract the WorkOS access token
    authorization_header = request.headers.get("Authorization")

    if not authorization_header or not authorization_header.startswith("Bearer "):
        raise HTTPException(
            status_code = 401,
            detail = "Missing or invalid Authorization header.",
        )
    
    credentials = authorization_header.removeprefix("Bearer ").strip()

    if not credentials:
        raise HTTPException(
            status_code = 401,
            detail = "Missing or invalid Authorization header.",
        )
    

    # 2. Verify the WorkOS access token
    try:
        token = await workos_auth.token_verifier.verify_token(credentials.strip())
    except Exception:
        raise HTTPException(
            status_code = 401,
            detail = "Invalid or expired WorkOS access token.",
        )
    

    # 3. Identify the authenticated user
    workos_user_id = token.subject

    if not isinstance(workos_user_id, str) or not workos_user_id.strip():
        raise HTTPException(
            status_code = 401,
            detail = "Authenticated user identity is missing.",
        )
    

    # 4. Retrieve the database connection pool
    pool: asyncpg.Pool | None = runtime.database_pool

    if pool is None:
        raise HTTPException(
            status_code = 503,
            detail = "Database connection pool is unavailable."
        )
    

    # 5. Resolve the tenant
    tenant = await get_or_create_tenant(
        pool,
        workos_user_id,
    )


    return {
        "pool": pool,
        "tenant_id": tenant["id"],
    }


