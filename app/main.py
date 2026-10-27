from fastapi import FastAPI

from fastmcp.utilities.lifespan import combine_lifespans
from yojak_mcp.server import mcp


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