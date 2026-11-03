from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse, JSONResponse

from fastmcp.utilities.lifespan import combine_lifespans

from pydantic import BaseModel, Field

from yojak_mcp.server import mcp, workos_auth

from app import runtime
from app.repositories import (
    get_or_create_tenant, 
    create_oauth_state,
    consume_oauth_state,
    create_zoho_authorization,
    get_active_zoho_authorization,
    create_merchant_connection,
    set_active_organization_connection,
)

from zoho.auth import generate_oauth_state, build_authorization_url
from zoho.client import exchange_authorization_code
from zoho.crypto import encrypt_refresh_token
from zoho.organizations import discover_organizations




# MCP Server HTTP Application
mcp_app = mcp.http_app(path="/")

# FastAPI Application
app = FastAPI(
    title = "Yojak",
    description = "An MCP powered connector for Zoho Inventory",
    version = "0.1.0",
    lifespan = combine_lifespans(mcp_app.lifespan),
)

# Mounting MCP app
app.mount("/mcp", mcp_app)


# Pydantic Model definition for validating incoming request body automatically
class ZohoOrganizationSelection(BaseModel):
    organization_id: str = Field(min_length = 1)


# Health Check Endpoint
@app.get("/")
def health_check():
    return {
        "status" : "OK",
        "application" : "Yojak",
    }


# Zoho OAuth Initiation Endpoint
@app.get("/oauth/zoho/connect")
async def connect_zoho(request: Request):
    
    # 1. Extract the bearer token
    authorization = request.headers.get("Authorization", "")
    scheme, _, credentials = authorization.partition(" ")

    if scheme.lower() != "bearer" or not credentials.strip():
        raise HTTPException(
            status_code = 401,
            detail = "A valid bearer token is required.",
            headers = {"WWW-Authenticate": "Bearer"},
        )
    

    # 2. Verify WorkOS access token
    try:
        token = await workos_auth.token_verifier.verify_token(credentials.strip())
    except Exception:
        raise HTTPException(
            status_code = 401,
            detail = "Invalid or Expired access token.",
            headers = {"WWW-Authenticate": "Bearer"},
        )
    

    # 3. Obtain the verified WorkOS user ID
    workos_user_id = token.subject

    if not isinstance(workos_user_id, str) or not workos_user_id.strip():
        raise HTTPException(
            status_code = 401,
            detail = "Authenticated user identity is missing.",
            headers = {"WWW-Authenticate": "Bearer"},
        )
    

    # 4. Get the existing database pool
    pool = runtime.database_pool

    if pool is None:
        raise HTTPException(
            status_code = 503,
            detail = "Database connection is unavailable.",
        )
    

    # 5. Resolve the tenant and persist OAuth state
    try:
        tenant = await get_or_create_tenant(pool, workos_user_id)

        state = generate_oauth_state()

        await create_oauth_state(
            pool,
            state,
            tenant["id"],
        )

        authorization_url = build_authorization_url(state)
    except Exception:
        raise HTTPException(
            status_code = 500,
            detail = "Unable to initiate Zoho authorization."
        )
    

    # 6. Redirect the user to Zoho
    return RedirectResponse(
        url = authorization_url,
        status_code = 302,
    )


# Zoho OAuth Callback Endpoint
@app.get("/oauth/zoho/callback")
async def zoho_callback(
        code: str | None = None,
        state: str | None = None,
        error: str | None = None,
    ):
    

    # 1. Validate the OAuth state parameter
    if not state or not state.strip():
        raise HTTPException(
            status_code = 400,
            detail = "OAuth state is missing.",
        )
    

    # 2. Obtain the existing database pool
    pool = runtime.database_pool

    if pool is None:
        raise HTTPException(
            status_code = 503,
            detail = "Database connection is unavailable.",
        )
    

    # 3. Validate and Consume OAuth state
    try:
        tenant_id = await consume_oauth_state(pool, state)
    except Exception:
        raise HTTPException(
            status_code = 500,
            detail = "Unable to validate OAuth state.",
        )
    
    if tenant_id is None:
        raise HTTPException(
            status_code = 400,
            detail = "OAuth state is invalid, expired, or already used.",
        )
    
    
    # 4. Handle authorization denial or other OAuth errors
    if error:
        raise HTTPException(
            status_code = 400,
            detail = "Zoho authorization was denied or failed.",
        )


    # 5. Validate the authorization code
    if not code or not code.strip():
        raise HTTPException(
            status_code = 400,
            detail = "Authorization code is missing.",
        )


    # 6. Exchange authorization code for tokens
    try: 
        token_data = await exchange_authorization_code(code)
    except Exception:
        raise HTTPException(
            status_code = 502,
            detail = "Unable to exchange the Zoho authorization code.",
        )
    

    # 7. Encrypt the refresh token
    try:
        encrypted_refresh_token = encrypt_refresh_token(token_data["refresh_token"])
    except Exception:
        raise HTTPException(
            status_code = 500,
            detail = "Unable to securely store the Zoho authorization",
        )
    

    # 8. Parse granted scopes
    scopes_value = token_data.get("scope", "")

    if isinstance(scopes_value, str):
        granted_scopes = [
            scope.strip() for scope in scopes_value.split(",") if scope.strip()
        ]
    elif isinstance(scopes_value, list):
        granted_scopes = scopes_value
    else:
        raise HTTPException(
            status_code = 502,
            detail = "Zoho returned an invalid scope format.",
        )
    

    # 9. Persist the authorization
    try:
        authorization = await create_zoho_authorization(
            pool = pool,
            tenant_id = tenant_id,
            refresh_token_encrypted = encrypted_refresh_token,
            granted_scopes = granted_scopes,
        )
    except Exception:
        raise HTTPException(
            status_code = 500,
            detail = "Unable to save the Zoho Authorization.",
        )
    

    # 10. Return a safe success response
    return JSONResponse(
        status_code = 200,
        content = {
            "status": "connected",
            "provider": "zoho_inventory",
            "message": (
                "Zoho authorization completed successfully."
                "You can now discover your organizations."
            ),
            "authorization_id": str(authorization["id"]),
        },
    )


# Zoho OAuth Organization Discovery Endpoint
@app.get("/oauth/zoho/organizations")
async def get_zoho_organizations(request: Request):

    # 1. Extract the WorkOS access token
    authorization_header = request.headers.get("Authorization")

    if not authorization_header or not authorization_header.startswith("Bearer "):
        raise HTTPException(
            status_code = 401,
            detail = "Missing or invalid Authorization header.",
        )
    
    credentials = authorization_header.removeprefix("Bearer ").strip()


    # 2. Verify the WorkOS access token
    try:
        token = workos_auth.token_verifier.verify_token(credentials)
    except Exception:
        raise HTTPException(
            status_code = 401,
            detail = "Invalid or expired WorkOS access token.",
        )
    

    # 3. Identify the authenticated WorkOS user
    workos_user_id = token.subject

    if not isinstance(workos_user_id, str) or not workos_user_id.strip():
        raise HTTPException(
            status_code = 401,
            detail = "Authenticated user identity is missing.",
        )
    

    # 4. Retrieve te database connection pool
    pool = runtime.database_pool

    if pool is None:
        raise HTTPException(
            status_code = 503,
            detail = "Database connection pool is unavailable.",
        )
    

    # 5. Resolve the tenant 
    tenant = await get_or_create_tenant(pool, workos_user_id)
    tenant_id = tenant["id"]


    # 6. Retrieve the tenant's active Zoho Authorization
    zoho_authorization = await get_active_zoho_authorization(
        pool,
        tenant_id,
    )

    if zoho_authorization is None:
        raise HTTPException(
            status_code = 404,
            detail = "No active Zoho authorization found. Connect Zoho first.",
        )
    

    # 7. Discover Zoho Organizations
    organizations = await discover_organizations(
        pool,
        tenant_id,
        zoho_authorization["id"],
    )


    # 8. Handle Zero Organizations
    if len(organizations) == 0:
        return {
            "status": "no_organizations_found",
            "selection_required": False,
            "message": "No Zoho organizations were found for this account.",
        }
    

    # 9. Handle a Single Organization
    if len(organizations) == 1:
        organization = organizations[0]

        connection  = await create_merchant_connection(
            pool,
            tenant_id,
            zoho_authorization["id"],
            organization["organization_id"],
        )

        # Set the organization connection as the tenant's active organization
        is_active = await set_active_organization_connection(
            pool,
            tenant_id,
            connection["id"],
        )

        if not is_active:
            raise HTTPException(
                status_code = 500,
                detail = "Unable to set the active Zoho organization.",
            )

        return {
            "status": "connected",
            "selection_required": False,
            "connection": {
                "id": str(connection["id"]),
                "organization_id": connection["zoho_organization_id"],
                "organization_name": organization.get("name"),
            },
        }


    # 10. Handle Multiple Organizations
    return {
        "status": "selection_required",
        "selection_required": True,
        "message": "Multiple Zoho organizations were found. Please select one.",
        "organizations": [
            {
                "organization_id":organization["organization_id"],
                "name": organization.get("name"),
            }
            for organization in organizations
        ],
    }


# Zoho OAuth Organization Selection Endpoint
@app.post("/oauth/zoho/organizations/select")
async def select_zoho_organization(
        selection: ZohoOrganizationSelection,
        request: Request,
    ):

    # 1. Extract the WorkOS access token
    authorization_header = request.headers.get("Authorization")

    if not authorization_header or not authorization_header.startswith("Bearer "):
        raise HTTPException(
            status_code = 401,
            detail = " Missing or invalid Authorization header.",
        )
    
    credentials = authorization_header.removeprefix("Bearer ").strip()


    # 2. Verify the WorkOS access token
    try:
        token = workos_auth.token_verifier.verify_token(credentials)
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
    pool = runtime.database_pool

    if pool is None:
        raise HTTPException(
            status_code = 503,
            detail = "Database connection pool is unavailable.",
        )
    

    # 5. Resolve the tenant
    tenant = await get_or_create_tenant(pool, workos_user_id)
    tenant_id = tenant["id"]


    # 6. Retrieve the active Zoho authorization
    zoho_authorization = await get_active_zoho_authorization(
        pool,
        tenant_id,
    )

    if zoho_authorization is None:
        raise HTTPException(
            status_code = 404,
            detail = "No active Zoho authorization found. Connection Zoho first.",
        )
    

    # 7. Discover organizations accessible through this authorization
    organizations = await discover_organizations(
        pool,
        tenant_id,
        zoho_authorization["id"],
    )


    # 8. Verify that the selected organization is accessible
    selected_organization = next(
        (
            organization for organization in organizations 
            if organization["organization_id"] == selection.organization_id
        ),
        None,
    )

    if selected_organization is None:
        raise HTTPException(
            status_code = 404,
            detail = "The selected organization is not accessible through this Zoho authorization.",
        )
    

    # 9. Create or retrieve the merchant connection
    connection = await create_merchant_connection(
        pool,
        tenant_id,
        zoho_authorization["id"],
        selection.organization_id,
    )


    # 10. Set the selected organization as active
    is_active = await set_active_organization_connection(
        pool,
        tenant_id,
        connection["id"],
    )

    if not is_active:
        raise HTTPException(
            status_code = 500,
            detail = "Unable to set the active Zoho organization.",
        )
    

    # 11. Return the connected organization
    return {
        "status": "connected",
        "connection": {
            "id": str(connection["id"]),
            "organization_id": connection["zoho_organization_id"],
            "organization_name": selected_organization.get("name"),
        },
    }


# Exposing Resource Metadata URL in Outer Application using add_route()
metadata_route = next(
    route for route in mcp_app.routes
    if getattr(route, "path", None) == "/.well-known/oauth-protected-resource/mcp/"
)

app.add_route(
    metadata_route.path,
    metadata_route.endpoint,
    methods = sorted(metadata_route.methods),
    name = metadata_route.name,
)