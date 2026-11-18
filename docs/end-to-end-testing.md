# Yojak — End-to-End Testing Guide

This document describes the procedure for verifying Yojak's integration with WorkOS AuthKit and Zoho Inventory.

The objective is to verify the complete authentication and organization-connection lifecycle using real external services, rather than relying exclusively on mocked application tests.

**Current Status:** Pending live end-to-end verification.

---

## 1. Testing Objectives

The end-to-end verification covers the following areas:

1. Application startup and database readiness.
2. WorkOS authentication through an MCP client.
3. Zoho OAuth authorization and callback processing.
4. Secure refresh-token persistence.
5. Zoho access-token retrieval and refresh.
6. Organization discovery through the Zoho Inventory API.
7. Multiple-organization selection.
8. Active organization switching.
9. Database persistence and tenant isolation.

The initial verification is limited to authentication and organization management. Inventory MCP operations are outside the scope of this milestone.

## 2. Test Environment

### 2.1 Required Services

| Service | Purpose |
|---|---|
| Yojak | Local application under test |
| WorkOS AuthKit | MCP client authentication |
| Zoho Inventory | External merchant inventory platform |
| Supabase PostgreSQL | Persistent application database |
| Codex | MCP client and testing assistant |

### 2.2 Test Organizations

The Zoho account contains the following organizations:

| Organization | Organization ID |
|---|---|
| Ishaan Demo Store | `60090589249` |
| Ishaan Demo Store 2 | `60096804481` |

Both organizations must be accessible through the same Zoho account used during OAuth consent.

These organizations are test fixtures. Their availability through Yojak must be confirmed during live organization discovery.

### 2.3 Required OAuth Scopes

Yojak currently requests:

```text
ZohoInventory.items.READ
ZohoInventory.salesorders.READ
ZohoInventory.settings.READ
```

The Zoho OAuth application must be configured with the callback URI:

```text
http://localhost:8000/oauth/zoho/callback
```

The WorkOS resource indicator configured in Yojak is:

```text
http://localhost:8000/mcp
```

The MCP server URL registered in Codex is:

```text
http://localhost:8000/mcp/
```

The resource indicator and MCP server URL serve different purposes and must not be treated as interchangeable configuration values.

## 3. Pre-flight Checks

Before starting the E2E tests:

- [ ] Verify that the Zoho OAuth application is configured correctly.
- [ ] Verify the callback URI.
- [ ] Verify that the required OAuth scopes are available.
- [ ] Verify the WorkOS AuthKit staging configuration.
- [ ] Verify that the WorkOS resource indicator matches Yojak's configuration.
- [ ] Verify that all required environment variables are configured in `.env`.
- [ ] Confirm that `.env` is excluded from Git.
- [ ] Confirm that the Supabase database is reachable.

Do not place credentials, refresh tokens, access tokens, or encryption keys in test reports or source control.

## 4. Start the Application

Navigate to the project directory:

```bash
cd ~/Ishaan-Workspace/Projects/yojak
```

Activate the virtual environment:

```bash
source .venv/bin/activate
```

Run the automated test suite:

```bash
pytest -v
```

Start the application:

```bash
uvicorn app.main:app --reload --port 8000
```

Keep the application running during the tests.

### 4.1 Application Health Check

Request:

```http
GET http://localhost:8000/
```

Expected response:

```json
{
  "status": "OK",
  "application": "Yojak"
}
```

### 4.2 Database Readiness Check

Request:

```http
GET http://localhost:8000/health/ready
```

Expected response:

```json
{
  "status": "ready",
  "database": "connected"
}
```

**Expected result:** The application is running and its shared database connection pool is available.

If either check fails, resolve the issue before continuing.

## 5. WorkOS Authentication and MCP Verification

Register Yojak with Codex if it is not already registered:

```bash
codex mcp add yojak --url http://localhost:8000/mcp/
```

Verify the configured MCP servers:

```bash
codex mcp list
```

Complete the WorkOS AuthKit login when prompted.

Call the diagnostic MCP tool:

```text
yojak_status
```

Expected response:

```json
{
  "application": "Yojak",
  "status": "OK"
}
```

**Expected result:** Codex successfully authenticates with WorkOS and invokes the Yojak MCP diagnostic tool.

This verifies the MCP authentication path. It does not, by itself, verify the Zoho REST endpoints.

## 6. Authenticated REST Endpoint Testing

The Zoho OAuth and organization-management operations are currently implemented as FastAPI HTTP endpoints. They are not yet exposed as MCP tools.

The protected endpoints require a valid WorkOS bearer token.

Use an authenticated HTTP test client that obtains a WorkOS access token for the configured Yojak resource indicator.

Do not assume that a token used for a different audience is valid for these endpoints. Do not extract or expose credentials from Codex's internal storage.

For the following requests, use:

```http
Authorization: Bearer <WORKOS_ACCESS_TOKEN>
```

The access token must remain private and must not be committed to the repository.

## 7. Zoho OAuth Authorization

### 7.1 Initiate the Connection

Request:

```http
GET http://localhost:8000/oauth/zoho/connect
```

Include the WorkOS bearer token.

Two outcomes are possible.

**Outcome A — New authorization required**

Expected HTTP status:

```text
302 Found
```

Yojak redirects the user to Zoho's OAuth consent page.

Open the returned authorization URL in a browser and complete the Zoho consent flow.

**Outcome B — Existing authorization can be reused**

Expected response:

```json
{
  "status": "authorization_reused",
  "provider": "zoho_inventory",
  "message": "An existing Zoho authorization was found. You can now discover your organizations.",
  "authorization_id": "<authorization-id>"
}
```

An existing authorization should be reused when it is active, has all required scopes, and can successfully obtain an access token.

### 7.2 Complete Zoho Consent

When new consent is required:

1. Sign in to the Zoho account containing both test organizations.
2. Review the requested permissions.
3. Grant the required permissions.
4. Allow Zoho to redirect to Yojak's configured callback URI.

### 7.3 Verify the OAuth Callback

Expected callback:

```text
GET /oauth/zoho/callback
```

The callback should:

1. Validate and consume the OAuth state.
2. Exchange the authorization code with Zoho.
3. Validate the token response.
4. Encrypt the refresh token.
5. Parse and persist the granted scopes.
6. Create or update the tenant's Zoho authorization.

Expected successful response:

```json
{
  "status": "connected",
  "provider": "zoho_inventory",
  "message": "Zoho authorization completed successfully.You can now discover your organizations.",
  "authorization_id": "<authorization-id>"
}
```

**Expected result:** A valid Zoho authorization is persisted for the authenticated Yojak tenant.

Never manually construct a successful callback or reuse an old authorization code. Verify this step through a real Zoho redirect.

## 8. Zoho Organization Discovery

Request:

```http
GET http://localhost:8000/oauth/zoho/organizations
```

Include the WorkOS bearer token.

Yojak should:

1. Verify the WorkOS user.
2. Resolve the corresponding tenant.
3. Retrieve the active Zoho authorization.
4. Obtain an access token through the token manager.
5. Request organizations from Zoho Inventory.
6. Return the organizations accessible through the authorization.

### 8.1 Expected Multiple-Organization Response

Since the test Zoho account contains two organizations, the expected response is:

```json
{
  "status": "selection_required",
  "selection_required": true,
  "message": "Multiple Zoho organizations were found. Please select one.",
  "organizations": [
    {
      "organization_id": "60090589249",
      "name": "Ishaan Demo Store"
    },
    {
      "organization_id": "60096804481",
      "name": "Ishaan Demo Store 2"
    }
  ]
}
```

The order of organizations in the response is not guaranteed.

Verify that both organization IDs are present and their names correspond to the expected organizations.

**Expected result:** Yojak returns both accessible organizations and does not automatically activate either one through the multiple-organization discovery branch.

If only one organization is returned, first verify that both organizations are accessible through the same Zoho account and that the OAuth authorization belongs to that account.

## 9. Organization Selection

The user must explicitly select one of the organizations returned by discovery.

### 9.1 Select Ishaan Demo Store

Request:

```http
POST http://localhost:8000/oauth/zoho/organizations/select
```

Body:

```json
{
  "organization_id": "60090589249"
}
```

Expected response:

```json
{
  "status": "connected",
  "connection": {
    "id": "<connection-id-1>",
    "organization_id": "60090589249",
    "organization_name": "Ishaan Demo Store"
  }
}
```

Verify that the selected connection is marked as active.

### 9.2 Select Ishaan Demo Store 2

Repeat the same request with:

```json
{
  "organization_id": "60096804481"
}
```

Expected response:

```json
{
  "status": "connected",
  "connection": {
    "id": "<connection-id-2>",
    "organization_id": "60096804481",
    "organization_name": "Ishaan Demo Store 2"
  }
}
```

Verify the following:

- A separate merchant connection exists for the second organization.
- The second connection is now active.
- The first connection is now inactive.
- The tenant's active organization pointer references the second connection.

### 9.3 Switch Back to Ishaan Demo Store

Repeat the selection request with:

```json
{
  "organization_id": "60090589249"
}
```

Expected behaviour:

- The existing first connection is reused.
- No duplicate connection is created.
- The first connection becomes active.
- The second connection becomes inactive.
- The tenant's active organization pointer is updated.

**Expected result:** Organization switching works in both directions while preserving existing merchant connection records.

## 10. Organization Selection Validation

Verify that Yojak does not trust an organization ID supplied by the caller.

Submit an organization ID that is not accessible through the current Zoho authorization.

Expected response:

```text
HTTP 404 Not Found
```

Expected error detail:

```text
The selected organization is not accessible through this Zoho authorization.
```

Verify that the existing active organization connection remains unchanged after the rejected selection.

## 11. Database Verification

After organization discovery and selection, execute the following read-only query in the Supabase SQL Editor:

```sql
SELECT
    t.id AS tenant_id,
    t.workos_user_id,
    t.active_organization_connection_id,

    za.id AS authorization_id,
    za.status AS authorization_status,
    za.granted_scopes,

    mc.id AS connection_id,
    mc.zoho_organization_id,
    mc.status AS connection_status,
    mc.provider

FROM tenants t

JOIN zoho_authorizations za
    ON za.tenant_id = t.id

JOIN merchant_connections mc
    ON mc.tenant_id = t.id
   AND mc.authorization_id = za.id

WHERE mc.zoho_organization_id IN (
    '60090589249',
    '60096804481'
)

ORDER BY mc.zoho_organization_id;
```

Expected database state after selecting Ishaan Demo Store:

| Organization | Connection status |
|---|---|
| Ishaan Demo Store | `active` |
| Ishaan Demo Store 2 | `inactive` |

The tenant's `active_organization_connection_id` must match the connection ID for Ishaan Demo Store.

After switching to Ishaan Demo Store 2, the expected states must reverse.

Verify that:

- Both connections belong to the same tenant.
- Both connections reference the same Zoho authorization.
- The authorization status is `active`.
- Exactly one connection is active.
- The tenant's active connection pointer matches the active connection.

Do not select or display `refresh_token_encrypted` in verification queries.

## 12. Additional Verification Scenarios

The following scenarios can be verified after the primary flow succeeds:

| Scenario | Expected behaviour |
|---|---|
| Missing WorkOS bearer token | HTTP 401 |
| Invalid or expired WorkOS token | HTTP 401 |
| Organization discovery without Zoho authorization | HTTP 404 |
| Invalid organization selection | HTTP 404 |
| Missing organization ID in selection body | HTTP 422 |
| Invalid or expired OAuth state | HTTP 400 |
| Reusing an already-consumed OAuth state | HTTP 400 |
| Database unavailable | HTTP 503 |
| Valid existing Zoho authorization | Existing authorization reused |

These scenarios should be performed without deleting or manually modifying production-like database records.

## 13. Testing Results

Record the results only after executing the corresponding live tests.

| Test | Expected result | Actual result |
|---|---|---|
| Application health | HTTP 200 | Pending |
| Database readiness | HTTP 200 | Pending |
| WorkOS authentication | Successful | Pending |
| MCP diagnostic tool | `yojak_status` returns OK | Pending |
| Zoho OAuth callback | Authorization persisted | Pending |
| Access-token retrieval | Successful | Pending |
| Organization discovery | Both organizations returned | Pending |
| First organization selection | First connection active | Pending |
| Second organization selection | Second connection active | Pending |
| Switch back to first organization | First connection active | Pending |
| Invalid organization selection | HTTP 404 | Pending |
| Database verification | Records and active pointer consistent | Pending |

Update the actual results and status after each test. Do not mark a test as passed based only on mocked unit tests.

## 14. Completion Criteria

The OAuth and organization-management E2E milestone is considered verified when:

- WorkOS authentication succeeds through an MCP client.
- Zoho OAuth authorization and callback processing succeed.
- The refresh token is securely persisted.
- Yojak successfully obtains an access token.
- Both test organizations are discovered through Zoho's API.
- Multiple-organization selection works.
- Existing organization connections are reused.
- Active organization switching works in both directions.
- Invalid organization selection is rejected.
- Database records correctly reflect the active organization.
- No cross-tenant access is observed.

After this milestone, development can proceed to the initial read-only inventory MCP tools:

- `list_items`
- `get_item`
- `list_sales_orders`
- `get_sales_order`

---

*This document is the repeatable end-to-end verification reference for Yojak's WorkOS and Zoho Inventory integration.*