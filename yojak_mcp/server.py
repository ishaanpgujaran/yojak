from fastmcp import FastMCP
from fastmcp.server.auth.providers.workos import AuthKitProvider

from app.config import settings

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
)

# Tool 1 - Diagnostic Tool
@mcp.tool
def yojak_status() -> dict:
    # Dcstring describes the tool to the client
    """Return the current status of the Yojak Application """ 

    return {
        "application" : "Yojak",
        "status" : "OK",
    }