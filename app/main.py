from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse

from fastmcp.utilities.lifespan import combine_lifespans
from yojak_mcp.server import mcp, workos_auth

from app import runtime
from app.repositories import get_or_create_tenant, create_oauth_state
from zoho.auth import generate_oauth_state, build_authorization_url


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