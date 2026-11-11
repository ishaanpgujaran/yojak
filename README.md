# Yojak — Zoho Inventory MCP Connector

**Yojak** is an MCP-powered connector designed to securely connect AI agents with merchant data stored in Zoho Inventory.

It acts as a bridge between MCP-compatible AI clients and the Zoho Inventory API, enabling AI agents to access business information through structured, well-defined tools.

The project focuses on secure authentication, tenant isolation, reliable API communication, and a modular architecture that can support additional Zoho Inventory capabilities.

> **Project Status:** Under active development.

## Overview

Businesses manage important operational data in inventory management systems such as Zoho Inventory. However, making this information accessible to AI agents requires a secure and standardized integration layer.

Yojak addresses this by providing an MCP server that handles authentication, organization access, and communication with Zoho Inventory.

The intended outcome is to allow AI agents to interact with merchant inventory data through MCP tools without requiring them to understand the underlying Zoho API implementation.

## Architecture

```text
                  AI Client
                      |
                      | MCP Protocol
                      |
                Yojak MCP Server
                      |
              Authentication Layer
                 (WorkOS)
                      |
                Tenant Resolution
                      |
              Zoho Connector Layer
             /        |         \
          OAuth    Token       API Client
                  Management
                      |
               Zoho Inventory API
                      |
                Merchant Data
```

### Core Components

- **MCP Server:** Exposes Zoho Inventory capabilities through structured MCP tools using FastMCP.
- **Authentication:** Uses WorkOS AuthKit to authenticate MCP clients.
- **Tenant Isolation:** Associates authenticated users with their respective Yojak tenants and ensures merchant data remains isolated.
- **Zoho OAuth:** Handles authorization and securely manages Zoho refresh tokens.
- **Token Management:** Handles access-token retrieval, caching, expiry, and refresh.
- **Database Layer:** Uses PostgreSQL to persist tenant information, Zoho authorizations, merchant connections, and OAuth states.

## Tech Stack

| Component | Technology |
|---|---|
| Language | Python 3.12 |
| Backend | FastAPI |
| MCP Framework | FastMCP |
| Authentication | WorkOS AuthKit |
| Database | Supabase PostgreSQL |
| Database Driver | asyncpg |
| Validation and Configuration | Pydantic, Pydantic Settings |
| External Integration | Zoho Inventory API |
| Token Encryption | Fernet |
| Testing | pytest, pytest-asyncio |

## Implemented Features

The following components have been implemented:

- [x] FastAPI application foundation.
- [x] MCP server using FastMCP.
- [x] WorkOS AuthKit integration.
- [x] Authenticated tenant identification.
- [x] PostgreSQL database integration.
- [x] Database schema and migrations.
- [x] Zoho OAuth authorization flow.
- [x] OAuth state generation, storage, and validation.
- [x] Secure refresh-token encryption.
- [x] Access-token refresh and caching.
- [x] Zoho organization discovery.
- [x] OAuth scope validation and reauthorization handling.
- [x] Repository-level tests for tenant and authorization operations.

## Planned Features

The following capabilities are part of the development roadmap:

- [ ] Complete end-to-end OAuth verification.
- [ ] Complete Zoho organization selection and connection management.
- [ ] Implement read-only inventory MCP tools.
- [ ] Support inventory item retrieval and search.
- [ ] Support sales order retrieval and search.
- [ ] Implement pagination and robust API error handling.
- [ ] Add comprehensive integration tests.
- [ ] Verify end-to-end functionality through MCP clients.
- [ ] Prepare deployment and documentation.

### Initial MCP Tools

The initial release is planned to expose read-only tools such as:

| Tool | Description |
|---|---|
| `list_items` | Retrieve inventory items from Zoho Inventory. |
| `get_item` | Retrieve details of a specific inventory item. |
| `list_sales_orders` | Retrieve sales orders from the selected organization. |
| `get_sales_order` | Retrieve details of a specific sales order. |

These tools are planned and are not yet implemented.

## Database Design

Yojak uses PostgreSQL to manage tenant information and merchant connections.

The primary database entities include:

- **tenants:** Stores Yojak tenant information and the active organization connection.
- **zoho_authorizations:** Stores encrypted Zoho refresh tokens, granted scopes, and authorization status.
- **merchant_connections:** Maintains the relationship between a tenant and its Zoho Inventory organizations.
- **oauth_states:** Stores hashed OAuth state values for secure authorization callback validation.

The database design supports multiple tenants while enforcing organization ownership and connection isolation.

## Security Considerations

Security is a core consideration in Yojak's architecture.

- Authenticated tenant identity is derived from verified WorkOS access tokens.
- OAuth state validation protects the authorization callback flow.
- Zoho refresh tokens are encrypted before database storage.
- Merchant connections are associated with their owning tenant.
- Active organization connections are constrained to belong to the same tenant.
- The initial inventory integration is designed around read-only access.

## Project Structure

```text
yojak/
├── app/
│   ├── config.py
│   ├── main.py
│   ├── database.py
│   ├── repositories.py
│   ├── runtime.py
│   └── dependencies.py
│
├── zoho/
│   ├── auth.py
│   ├── client.py
│   ├── crypto.py
│   ├── token_manager.py
│   └── organizations.py
│
├── yojak_mcp/
│   └── server.py
│
├── sql/
│   └── database migrations
│
├── tests/
│   └── automated tests
│
├── .env.example
├── requirements.txt
└── README.md
```

## Getting Started

### Prerequisites

- Python 3.12+
- A Zoho Inventory account and OAuth application.
- A WorkOS AuthKit application.
- A Supabase PostgreSQL database.

### Installation

Clone the repository:

```bash
git clone https://github.com/ishaanpgujaran/yojak.git
cd yojak
```

Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

### Environment Configuration

Create a `.env` file using `.env.example` as a reference.

Configure the required environment variables:

```env
ZOHO_CLIENT_ID=
ZOHO_CLIENT_SECRET=
ZOHO_REDIRECT_URI=
ZOHO_ACCOUNTS_URL=
ZOHO_API_BASE_URL=

DATABASE_URL=

WORKOS_AUTHKIT_DOMAIN=

ZOHO_TOKEN_ENCRYPTION_KEY=
```

Use the appropriate values for your Zoho OAuth application, WorkOS configuration, and PostgreSQL database.

**Important:** Never commit `.env` files, OAuth credentials, access tokens, refresh tokens, or encryption keys to version control.

## Testing

Run the test suite using:

```bash
pytest -v
```

Tests cover database operations, tenant isolation, OAuth state handling, token encryption, Zoho API communication, token management, and authorization-related repository operations.

## Current Scope

Yojak is currently focused on establishing a secure foundation for connecting AI agents with Zoho Inventory.

The initial implementation prioritizes authentication, authorization, organization management, and read-only inventory access.

Additional capabilities can be introduced incrementally as the connector evolves.

## Author

**Ishaan Gujaran**

GitHub: [@ishaanpgujaran](https://github.com/ishaanpgujaran)

---

*Yojak — Connecting AI agents with business inventory data.*