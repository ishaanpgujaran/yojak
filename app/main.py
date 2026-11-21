import logging

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import RedirectResponse, JSONResponse

from fastmcp.utilities.lifespan import combine_lifespans

from pydantic import BaseModel, Field

from yojak_mcp.server import mcp, workos_auth

from app import runtime
from app.dependencies import get_authenticated_tenant_context
from app.database_errors import DATABASE_AVAILABILITY_ERRORS
from app.repositories import (
    get_or_create_tenant, 
    get_active_zoho_authorization,
    create_merchant_connection,
    set_active_organization_connection,
)
from app.services.zoho_oauth import (
    connect_zoho_service,
    handle_zoho_callback_service,
    ZohoAuthorizationLookupError,
    ZohoAuthorizationValidationError,
    ZohoOAuthInitiationError,
    ZohoOAuthStateValidationError,
    ZohoOAuthStateInvalidError,
    ZohoAuthorizationDeniedError,
    ZohoAuthorizationCodeMissingError,
    ZohoAuthorizationCodeExchangeError,
    ZohoRefreshTokenEncryptionError,
    ZohoInvalidScopeFormatError,
    ZohoAuthorizationPersistenceError,
)
from zoho.organizations import discover_organizations


logger = logging.getLogger(__name__)


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


# Registering Exception Handler
async def database_availability_exception_handler(
        request: Request,
        exc: Exception,
    ):

    logger.error(
        "Database availability failure during request: %s",
        request.url.path,
        exc_info = (type(exc), exc, exc.__traceback__),
    )

    return JSONResponse(
        status_code = 503,
        content = {
            "status": "service_unavailable",
            "message": "Database service is temporarily unavailable. Please try again later.",
        },
    )

# FastAPI exception-handler registration expects an exception class, so using loop to register individual classes
for exception_class in DATABASE_AVAILABILITY_ERRORS:
    app.add_exception_handler(
        exception_class,
        database_availability_exception_handler,
    )


# Health Check Endpoint
@app.get("/")
def health_check():
    return {
        "status" : "OK",
        "application" : "Yojak",
    }


# Database Readiness Endpoint
@app.get("/health/ready")
async def readiness_check():

    pool = runtime.database_pool

    if pool is None:
        return JSONResponse(
            status_code = 503,
            content = {
                "status": "not_ready",
                "database": "unavailable",
            },
        )
    
    try:
        async with pool.acquire() as connection:
            await connection.fetchval("SELECT 1")
    except Exception:
        logger.exception("Database readiness check failed.")

        return JSONResponse(
            status_code = 503,
            content = {
                "status": "not_ready",
                "database": "unavailable",
            },
        )

    return {
        "status": "ready",
        "database": "connected", 
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
    

    # 5. Resolve the tenant 
    try:
        tenant = await get_or_create_tenant(pool, workos_user_id)

        tenant_id = tenant["id"]

    # Re-raise known database availability exceptions before the generic exception handler.
    except DATABASE_AVAILABILITY_ERRORS:
        raise

    except Exception:
        raise HTTPException(
            status_code = 500,
            detail = "Unable to retrieve the existing Zoho authorization.",
        )
    

    # 6. Delegate Zoho connection logic to the shared service.
    try:
        result = await connect_zoho_service(pool, tenant_id)

    except DATABASE_AVAILABILITY_ERRORS:
        raise

    except ZohoAuthorizationLookupError:
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve the existing Zoho authorization.",
        )

    except ZohoAuthorizationValidationError:
        raise HTTPException(
            status_code=502,
            detail="Unable to validate the existing Zoho authorization.",
        )

    except ZohoOAuthInitiationError:
        raise HTTPException(
            status_code=500,
            detail="Unable to initiate Zoho authorization.",
        )

    # 7. Translate the service result into an HTTP response.
    if result["status"] == "authorization_reused":
        return JSONResponse(
            status_code=200,
            content={
                "status": "authorization_reused",
                "provider": "zoho_inventory",
                "message": (
                    "An existing Zoho authorization was found. "
                    "You can now discover your organizations."
                ),
                "authorization_id": result["authorization_id"],
            },
        )

    return RedirectResponse(
        url=result["authorization_url"],
        status_code=302,
    )


# Zoho OAuth Callback Endpoint
@app.get("/oauth/zoho/callback")
async def zoho_callback(
        code: str | None = None,
        state: str | None = None,
        error: str | None = None,
    ):

    # 1. Validate the OAuth state parameter.
    if not state or not state.strip():
        raise HTTPException(
            status_code=400,
            detail="OAuth state is missing.",
        )

    # 2. Obtain the existing database pool.
    pool = runtime.database_pool

    if pool is None:
        raise HTTPException(
            status_code=503,
            detail="Database connection is unavailable.",
        )

    # 3. Delegate callback processing to the shared service.
    try:
        result = await handle_zoho_callback_service(
            pool,
            code,
            state,
            error,
        )

    except DATABASE_AVAILABILITY_ERRORS:
        raise

    except ZohoOAuthStateValidationError:
        raise HTTPException(
            status_code=500,
            detail="Unable to validate OAuth state.",
        )

    except ZohoOAuthStateInvalidError:
        raise HTTPException(
            status_code=400,
            detail="OAuth state is invalid, expired, or already used.",
        )

    except ZohoAuthorizationDeniedError:
        raise HTTPException(
            status_code=400,
            detail="Zoho authorization was denied or failed.",
        )

    except ZohoAuthorizationCodeMissingError:
        raise HTTPException(
            status_code=400,
            detail="Authorization code is missing.",
        )

    except ZohoAuthorizationCodeExchangeError:
        raise HTTPException(
            status_code=502,
            detail="Unable to exchange the Zoho authorization code.",
        )

    except ZohoRefreshTokenEncryptionError:
        raise HTTPException(
            status_code=500,
            detail="Unable to securely store the Zoho authorization",
        )

    except ZohoInvalidScopeFormatError:
        raise HTTPException(
            status_code=502,
            detail="Zoho returned an invalid scope format.",
        )

    except ZohoAuthorizationPersistenceError:
        raise HTTPException(
            status_code=500,
            detail="Unable to save the Zoho Authorization.",
        )

    # 4. Translate the service result into an HTTP response.
    return JSONResponse(
        status_code=200,
        content={
            "status": "connected",
            "provider": "zoho_inventory",
            "message": (
                "Zoho authorization completed successfully."
                "You can now discover your organizations."
            ),
            "authorization_id": result["authorization_id"],
        },
    )


# Zoho OAuth Organization Discovery Endpoint
@app.get("/oauth/zoho/organizations")
async def get_zoho_organizations(
        context: dict = Depends(get_authenticated_tenant_context),
    ):

    # 1. Retrieve authenticated tenant context using Dependencies
    pool = context["pool"]
    tenant_id = context["tenant_id"]
    

    # 2. Retrieve the tenant's active Zoho Authorization
    zoho_authorization = await get_active_zoho_authorization(
        pool,
        tenant_id,
    )

    if zoho_authorization is None:
        raise HTTPException(
            status_code = 404,
            detail = "No active Zoho authorization found. Connect Zoho first.",
        )
    

    # 3. Discover Zoho Organizations
    organizations = await discover_organizations(
        pool,
        tenant_id,
        zoho_authorization["id"],
    )


    # 4. Handle Zero Organizations
    if len(organizations) == 0:
        return {
            "status": "no_organizations_found",
            "selection_required": False,
            "message": "No Zoho organizations were found for this account.",
        }
    

    # 5. Handle a Single Organization
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


    # 6. Handle Multiple Organizations
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
        context: dict = Depends(get_authenticated_tenant_context),
    ):

    # 1. Retrieve authenticated tenant context using Dependencies
    pool = context["pool"]
    tenant_id = context["tenant_id"]
    

    # 2. Retrieve the active Zoho authorization
    zoho_authorization = await get_active_zoho_authorization(
        pool,
        tenant_id,
    )

    if zoho_authorization is None:
        raise HTTPException(
            status_code = 404,
            detail = "No active Zoho authorization found. Connection Zoho first.",
        )
    

    # 3. Discover organizations accessible through this authorization
    organizations = await discover_organizations(
        pool,
        tenant_id,
        zoho_authorization["id"],
    )


    # 4. Verify that the selected organization is accessible
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
    

    # 5. Create or retrieve the merchant connection
    connection = await create_merchant_connection(
        pool,
        tenant_id,
        zoho_authorization["id"],
        selection.organization_id,
    )


    # 6. Set the selected organization as active
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
    

    # 7. Return the connected organization
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