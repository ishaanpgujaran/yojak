# Yojak — Zoho Inventory MCP Connector

**Yojak** is an MCP-powered connector that enables AI agents to securely access merchant data stored in Zoho Inventory.

It acts as a bridge between MCP-compatible AI clients and the Zoho Inventory API, providing a standardized interface for authentication, organization management, and inventory operations.

Yojak is being built with a focus on secure authentication, tenant isolation, reliable API communication, and a modular connector architecture.

> **Project Status:** Core authentication, Zoho OAuth, organization discovery, and organization selection are implemented and covered by automated tests. Live end-to-end verification is the current milestone. Read-only inventory MCP tools are planned next.

---

## Overview

Businesses rely on inventory management systems such as Zoho Inventory to manage their products, customers, sales orders, and other operational information.

Making this information accessible to AI agents requires an integration layer that securely handles authentication, authorization, tenant isolation, and communication with the underlying platform.

Yojak provides this integration through the **Model Context Protocol (MCP)**.

The intended outcome is to allow AI agents to interact with merchant inventory information through structured MCP tools without needing to understand the underlying Zoho API implementation.

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
                      Yojak Service Layer
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

- **MCP Server:** Exposes Yojak functionality through structured MCP tools using FastMCP.
- **Authentication:** Uses WorkOS AuthKit to authenticate MCP clients.
- **Tenant Isolation:** Associates authenticated users with their respective Yojak tenants.
- **Zoho OAuth:** Handles authorization initiation, callback validation, and secure refresh-token storage.
- **Token Management:** Handles access-token retrieval, caching, expiry, refresh, and concurrency control.
- **Organization Management:** Discovers accessible Zoho organizations and manages tenant-specific merchant connections.
- **Service Layer:** Separates business logic from transport-specific interfaces, allowing services to be reused by REST and MCP endpoints.
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

---

## Implemented Features

The following components have been implemented:

### Application and Authentication

- [x] FastAPI application foundation.
- [x] MCP server using FastMCP.
- [x] WorkOS AuthKit integration.
- [x] Authenticated tenant identification.
- [x] PostgreSQL database integration and migrations.
- [x] Database availability checks and readiness handling.

### Zoho OAuth and Token Management

- [x] Zoho OAuth authorization initiation.
- [x] OAuth callback handling.
- [x] Cryptographically secure OAuth state generation.
- [x] Hashed OAuth state storage and one-time validation.
- [x] OAuth state expiration handling.
- [x] Secure refresh-token encryption using Fernet.
- [x] Access-token retrieval and refresh.
- [x] Access-token caching and concurrency control.
- [x] Handling of invalid and revoked refresh tokens.
- [x] OAuth scope validation and reauthorization handling.
- [x] Reuse and preservation of existing Zoho authorizations.

### Organization Management

- [x] Zoho organization discovery.
- [x] Organization accessibility validation.
- [x] Merchant organization connection creation and reuse.
- [x] Organization selection.
- [x] Active organization switching.
- [x] Tenant-specific organization connection management.
- [x] Database constraints enforcing tenant ownership.
- [x] Single active organization connection per tenant.

### MCP Tools

- [x] `yojak_status`
- [x] `yojak_connect_zoho`
- [x] `yojak_discover_zoho_organizations`
- [x] `yojak_select_zoho_organization`

### Testing

- [x] Automated authentication tests.
- [x] Database operation tests.
- [x] OAuth state validation tests.
- [x] Token encryption tests.
- [x] Token management tests.
- [x] Zoho API communication tests.
- [x] Organization discovery tests.
- [x] Organization selection tests.
- [x] Error handling tests.

**Note:** Implementation and automated test coverage do not imply that the complete live integration has been verified. End-to-end verification against WorkOS and Zoho Inventory is the current milestone.

---

## Organization Connection Management

A Yojak tenant can authorize a Zoho account and access the organizations available through that authorization.

Yojak maintains a separate merchant connection for each accessible Zoho organization.

The organization management implementation supports:

- Discovering organizations accessible through the authorized Zoho account.
- Automatically activating an organization when only one is available.
- Returning available organizations when multiple organizations are found.
- Validating a selected organization against Zoho's actual organization list.
- Creating or reusing the corresponding merchant connection.
- Switching the active organization while preserving previous connections.
- Ensuring that only one organization connection is active per tenant.

### Merchant Connection Statuses

| Status | Meaning |
|---|---|
| `pending` | Connection setup has started but is not yet complete. |
| `active` | Currently selected organization. |
| `inactive` | Previously connected successfully but no longer selected. |
| `revoked` | Connection or authorization has been revoked. |
| `error` | Connection encountered an error. |

The database enforces tenant ownership through foreign keys and constraints. A partial unique index ensures that a tenant cannot have more than one active organization connection.

**Implementation status:** Completed. Live end-to-end verification remains pending.

---

## Initial Inventory MCP Tools

Once authentication and organization management have been verified end to end, the next milestone is to implement read-only inventory operations.

The initial inventory integration is planned around the following tools:

| Tool | Description | Status |
|---|---|---|
| `list_items` | Retrieves inventory items from Zoho Inventory. | Planned |
| `get_item` | Retrieves details of a specific inventory item. | Planned |
| `list_sales_orders` | Retrieves sales orders from Zoho Inventory. | Planned |
| `get_sales_order` | Retrieves details of a specific sales order. | Planned |

These operations will use the active merchant connection associated with the authenticated tenant.

The initial inventory integration will remain read-only.

---

## Database Design

Yojak uses PostgreSQL to manage tenant information, Zoho authorizations, and merchant connections.

The primary database entities include:

- **tenants:** Stores Yojak tenant information and the active organization connection.
- **zoho_authorizations:** Stores encrypted Zoho refresh tokens, granted scopes, and authorization status.
- **merchant_connections:** Maintains the relationship between a tenant and its Zoho Inventory organizations.
- **oauth_states:** Stores hashed OAuth state values for secure authorization callback validation.

The database design supports multiple tenants while enforcing organization ownership and connection isolation.

### Tenant Isolation

Tenant isolation is enforced through:

- Authenticated user identity derived from verified WorkOS access tokens.
- Tenant-specific authorization records.
- Tenant-specific merchant connections.
- Composite foreign keys enforcing ownership across related records.
- Database constraints preventing multiple active organization connections for a tenant.

---

## Security Considerations

Security is a core consideration in Yojak's architecture.

The implementation incorporates the following measures:

- Authenticated tenant identity is derived from verified WorkOS access tokens.
- OAuth state validation protects the authorization callback flow against CSRF attacks.
- OAuth state values are generated using cryptographically secure randomness.
- OAuth state values are hashed before database storage and are single-use.
- Zoho refresh tokens are encrypted before database storage.
- Access tokens are managed through a dedicated token management layer.
- Merchant connections are associated with their owning tenant.
- Composite foreign keys enforce tenant ownership.
- Only one active organization connection is permitted per tenant.
- The initial inventory integration is designed around read-only access.
- Sensitive credentials and tokens must never be committed to version control.

---

## Project Structure

```text
yojak/
│
├── app/
│   ├── config.py
│   ├── main.py
│   ├── database.py
│   ├── database_errors.py
│   ├── dependencies.py
│   ├── repositories.py
│   ├── runtime.py
│   └── services/
│       ├── oauth_services
│       └── organization_services
│
├── zoho/
│   ├── auth.py
│   ├── client.py
│   ├── crypto.py
│   └── token_manager.py
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

---

## Getting Started

### Prerequisites

- Python 3.12+
- A Zoho Inventory account and configured OAuth application.
- A WorkOS AuthKit application.
- A Supabase PostgreSQL database.

### 1. Clone the Repository

```bash
git clone https://github.com/ishaanpgujaran/yojak.git

cd yojak
```

### 2. Create a Virtual Environment

```bash
python -m venv .venv
```

Activate it:

```bash
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create a `.env` file using `.env.example` as a reference.

Configure the following variables:

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

### 5. Run Database Migrations

Apply the SQL migrations in the `sql/` directory to your configured PostgreSQL database in the intended migration order.

### 6. Run the Application

Start the application locally:

```bash
uvicorn app.main:app --reload --port 8000
```

### 7. Verify Application Health

Check application health:

```bash
curl http://localhost:8000/
```

Check database readiness:

```bash
curl http://localhost:8000/health/ready
```

---

## Running Tests

Run the complete automated test suite:

```bash
pytest -v
```

Run a specific test module:

```bash
pytest tests/test_yojak_mcp_server.py -v
```

The automated tests cover authentication, database operations, tenant isolation, OAuth state handling, token encryption, token management, Zoho API communication, and organization management.

---

## End-to-End Verification

The live integration verification covers the complete connection lifecycle:

1. Authenticate through WorkOS using an MCP client.
2. Resolve the authenticated user to the corresponding Yojak tenant.
3. Initiate Zoho OAuth authorization.
4. Complete the Zoho authorization callback.
5. Verify secure refresh-token persistence.
6. Retrieve a valid Zoho access token.
7. Discover accessible Zoho organizations.
8. Select an organization.
9. Verify merchant connection creation and activation.
10. Verify the final connection status and tenant isolation.

A repeatable verification procedure is maintained in [`docs/end-to-end-testing.md`](docs/end-to-end-testing.md).

**Current status:** Live end-to-end verification is pending.

---

## Development Roadmap

Yojak is being developed incrementally, prioritizing a secure foundation before exposing merchant inventory data.

### Phase 1 — Authentication and Connection Foundation

- [x] Establish FastAPI and MCP application foundations.
- [x] Integrate WorkOS AuthKit.
- [x] Implement tenant identification and isolation.
- [x] Implement Zoho OAuth authorization.
- [x] Implement secure token storage and management.
- [x] Implement organization discovery.
- [x] Implement organization selection and switching.
- [ ] Complete live end-to-end verification.

### Phase 2 — Read-Only Inventory Integration

- [ ] Implement the Zoho API connector operations for inventory access.
- [ ] Implement `list_items`.
- [ ] Implement `get_item`.
- [ ] Implement `list_sales_orders`.
- [ ] Implement `get_sales_order`.
- [ ] Implement pagination and filtering.
- [ ] Implement robust API error handling.
- [ ] Verify inventory operations through MCP clients.

### Phase 3 — Reliability and Expansion

- [ ] Improve retry and rate-limit handling.
- [ ] Expand automated integration testing.
- [ ] Improve operational logging and observability.
- [ ] Prepare deployment and operational documentation.
- [ ] Evaluate additional read-only Zoho Inventory capabilities.

---

## Current Scope

Yojak is currently focused on establishing a secure foundation for connecting AI agents with Zoho Inventory.

The implementation prioritizes:

- Authentication and authorization lifecycle management.
- Tenant isolation.
- Secure credential storage.
- Zoho organization discovery and selection.
- Reliable merchant connection management.

Inventory operations will be introduced incrementally after the connection lifecycle has been verified.

The initial scope is intentionally read-only.

---

## Author

**Ishaan Gujaran**

GitHub: [@ishaanpgujaran](https://github.com/ishaanpgujaran)

Repository: [github.com/ishaanpgujaran/yojak](https://github.com/ishaanpgujaran/yojak)

---

*Yojak — Connecting AI agents with business inventory data.*