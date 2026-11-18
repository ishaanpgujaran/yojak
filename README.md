# Yojak — Zoho Inventory MCP Connector

**Yojak** is an MCP-powered connector that enables AI agents to securely access merchant data stored in Zoho Inventory.

It acts as a bridge between MCP-compatible AI clients and the Zoho Inventory API, providing a standardized interface for authentication, organization access, and inventory operations.

The project focuses on secure authentication, tenant isolation, reliable API communication, and a modular connector architecture.

> **Project Status:** Core authentication and organization-connection implementation completed. Live end-to-end verification is in progress. Read-only inventory MCP tools are the next development milestone.

---

## Overview

Businesses manage important operational data in inventory management systems such as Zoho Inventory. Making this information accessible to AI agents requires a secure integration layer that handles authentication, authorization, and communication with the underlying platform.

Yojak provides this integration through the Model Context Protocol (MCP).

The intended outcome is to allow AI agents to access merchant inventory information through structured tools without needing to understand the underlying Zoho API implementation.

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
                  /          |          \
               OAuth       Token       API Client
                          Management
                           |
                    Zoho Inventory API
                           |
                     Merchant Data
```

### Core Components

- **MCP Server:** Exposes Zoho Inventory capabilities through structured MCP tools using FastMCP.
- **Authentication:** Uses WorkOS AuthKit to authenticate MCP clients.
- **Tenant Isolation:** Associates authenticated users with their respective Yojak tenants.
- **Zoho OAuth:** Handles authorization, callback validation, and secure refresh-token storage.
- **Token Management:** Handles access-token retrieval, caching, expiry, and refresh.
- **Organization Management:** Discovers Zoho organizations and manages the tenant's active organization connection.
- **Database Layer:** Uses PostgreSQL to persist tenants, Zoho authorizations, merchant connections, and OAuth states.

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
- [x] PostgreSQL database integration and migrations.
- [x] Tenant-isolated Zoho authorization records.
- [x] Zoho OAuth authorization initiation and callback handling.
- [x] Cryptographically secure OAuth state generation, storage, and validation.
- [x] Secure refresh-token encryption.
- [x] Access-token refresh, caching, and concurrency control.
- [x] Handling of invalid and revoked refresh tokens.
- [x] OAuth scope validation and reauthorization handling.
- [x] Reuse and preservation of existing Zoho authorizations.
- [x] Zoho organization discovery.
- [x] Merchant organization connection creation and reuse.
- [x] Organization selection and active-connection switching.
- [x] Database constraints enforcing tenant ownership and a single active organization connection.
- [x] Automated tests for authentication, database operations, OAuth, token management, and organization endpoints.
- [x] Database availability error handling and readiness checks.

## Organization Connection Management

A Yojak tenant can authorize one Zoho account and access the organizations available through that authorization.

Yojak maintains a separate merchant connection for each accessible Zoho organization.

The organization management implementation supports:

- Discovering organizations accessible through the authorized Zoho account.
- Automatically activating an organization when only one is available.
- Returning the available organizations when multiple organizations are found.
- Validating a selected organization against Zoho's actual organization list.
- Creating or reusing the corresponding merchant connection.
- Switching the active organization while preserving previous connections.
- Ensuring that only one organization connection is active per tenant.

Merchant connection statuses:

| Status | Meaning |
|---|---|
| `pending` | Connection setup has started but is not yet complete. |
| `active` | Currently selected organization. |
| `inactive` | Previously connected successfully but no longer selected. |
| `revoked` | Connection or authorization has been revoked. |
| `error` | Connection encountered an error. |

The database enforces tenant ownership through foreign keys and constraints. A partial unique index ensures that a tenant cannot have more than one active organization connection.

**Implementation status:** Completed. Live end-to-end verification remains pending.

## Initial MCP Tools

The initial inventory integration is planned around read-only operations.

| Tool | Description | Status |
|---|---|---|
| `yojak_status` | Returns the current application status. | Implemented |
| `list_items` | Retrieves inventory items from Zoho Inventory. | Planned |
| `get_item` | Retrieves details of a specific inventory item. | Planned |
| `list_sales_orders` | Retrieves sales orders from Zoho Inventory. | Planned |
| `get_sales_order` | Retrieves details of a specific sales order. | Planned |

The inventory tools have not yet been implemented.

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
- Composite foreign keys enforce tenant ownership across related records.
- Only one active organization connection is permitted per tenant.
- The initial inventory integration is designed around read-only access.
- Sensitive credentials and tokens must never be committed to version control.

## Project Structure

```text
yojak/
├── app/
│   ├── config.py
│   ├── main.py
│   ├── database.py
│   ├── database_errors.py
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
├── docs/
│   ├── zoho-oauth-lifecycle.md
│   └── end-to-end-testing.md
│
├── .env.example
├── requirements.txt
└── README.md
```

## Getting Started

### Prerequisites

- Python 3.12+
- A Zoho Inventory account and configured OAuth application.
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

Configure the following environment variables:

```env
ZOHO_CLIENT_ID=
ZOHO_CLIENT_SECRET=
ZOHO_REDIRECT_URI=http://localhost:8000/oauth/zoho/callback
ZOHO_ACCOUNTS_URL=https://accounts.zoho.in
ZOHO_API_BASE_URL=https://www.zohoapis.in/inventory/v1

DATABASE_URL=

WORKOS_AUTHKIT_DOMAIN=

ZOHO_TOKEN_ENCRYPTION_KEY=
```

Use the appropriate values for your Zoho OAuth application, WorkOS configuration, and PostgreSQL database.

**Important:** Never commit `.env` files, OAuth credentials, access tokens, refresh tokens, or encryption keys to version control.

### Running the Application

Start the application locally:

```bash
uvicorn app.main:app --reload --port 8000
```

Check application health:

```bash
curl http://localhost:8000/
```

Check database readiness:

```bash
curl http://localhost:8000/health/ready
```

### Running Tests

Run the automated test suite:

```bash
pytest -v
```

The tests cover database operations, tenant isolation, OAuth state handling, token encryption, Zoho API communication, token management, and authorization-related application behaviour.

## End-to-End Verification

The live integration verification covers:

1. WorkOS authentication through an MCP client.
2. Zoho OAuth authorization and callback handling.
3. Secure refresh-token persistence.
4. Zoho access-token retrieval and refresh.
5. Organization discovery.
6. Organization selection and active-connection switching.
7. Database persistence and tenant isolation.

A repeatable verification procedure is maintained in [`docs/end-to-end-testing.md`](docs/end-to-end-testing.md).

**Current status:** Pending live verification against Zoho Inventory and WorkOS.

## Development Roadmap

The next development milestones are:

- [ ] Complete live end-to-end verification of WorkOS authentication and Zoho OAuth.
- [ ] Verify organization discovery and multi-organization selection.
- [ ] Verify active organization switching and persistence.
- [ ] Implement read-only inventory MCP tools.
- [ ] Implement pagination and robust Zoho API error handling.
- [ ] Verify inventory operations through MCP clients.
- [ ] Prepare deployment and operational documentation.

## Current Scope

Yojak is currently focused on establishing a secure foundation for connecting AI agents with Zoho Inventory.

The implementation prioritizes authentication, tenant isolation, authorization lifecycle management, and merchant organization connections before introducing inventory operations.

Additional capabilities will be introduced incrementally.

## Author

**Ishaan Gujaran**

GitHub: [@ishaanpgujaran](https://github.com/ishaanpgujaran)

---

*Yojak — Connecting AI agents with business inventory data.*