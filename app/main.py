from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.database import lifespan_database

from fastmcp.utilities.lifespan import combine_lifespans
from yojak_mcp.server import mcp


# Integration of Database Pool in FastAPI
@asynccontextmanager
async def lifespan(app: FastAPI):
    async with lifespan_database() as pool:
        app.state.db_pool = pool

        yield


# MCP Server HTTP Application
mcp_app = mcp.http_app(path="/")


app = FastAPI(
    title = "Yojak",
    description = "An MCP powered connector for Zoho Inventory",
    version = "0.1.0",
    lifespan = combine_lifespans(lifespan, mcp_app.lifespan),
)

app.mount("/mcp", mcp_app)

@app.get("/")
def health_check():
    return {
        "status" : "OK",
        "application" : "Yojak",
    }