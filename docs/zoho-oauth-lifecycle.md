# Zoho OAuth Lifecycle — Implementation Tracker

This document tracks the design decisions, implementation progress, and remaining verification work for Zoho OAuth integration in Yojak.

The primary objective is to ensure that Zoho authorization remains reliable across reconnections, token expiration, revoked access, and changes in required OAuth scopes.

It also documents the expected behaviour of authorization records and their relationship with merchant organization connections.

**Current Status:** Core OAuth implementation completed. Regression testing and end-to-end verification pending.

---

## 1. Authorization Reconnection Lifecycle

### 1.1 Design Requirements

Yojak follows these authorization principles:

- One Zoho authorization per Yojak tenant.
- Reauthorization must preserve the existing authorization record ID.
- Existing merchant organization connections must remain associated with the same authorization record.
- Invalid or revoked refresh tokens must be handled correctly.
- Temporary Zoho or network failures must not incorrectly revoke a merchant's authorization.
- Existing authorization should be reused whenever it is valid and has all required scopes.
- New OAuth consent should only be requested when necessary.

### 1.2 Reconnection Scenarios

There are two primary reconnection scenarios.

#### Scenario 1: Reuse an Existing Authorization

This scenario occurs when a user reconnects through another client, browser, or session, or when the existing session expires.

Expected behaviour:

1. Retrieve the existing Zoho authorization for the tenant.
2. Check whether the authorization is active.
3. Verify that all required OAuth scopes have been granted.
4. If the scopes are sufficient, obtain an access token through the token manager.
5. Reuse the existing authorization.
6. Do not unnecessarily initiate another Zoho consent flow.

The token manager handles access-token caching and refreshing when required.

The existing authorization record and its ID should remain unchanged during normal reuse.

#### Scenario 2: Reauthorize Through Zoho Consent

This scenario occurs when:

- The existing refresh token is invalid or revoked.
- The authorization has been marked as revoked.
- Required OAuth scopes are missing.
- The existing authorization is in an error or pending state.
- The user explicitly needs to authorize Zoho again.

Expected behaviour:

1. Initiate a new Zoho OAuth consent flow.
2. Validate the OAuth callback and state.
3. Exchange the authorization code for tokens.
4. Encrypt the refresh token before database storage.
5. Update the existing authorization record rather than creating a duplicate.
6. Preserve the existing authorization ID.
7. Keep existing merchant organization connections associated with that authorization.

**Important:** Reauthorization must not unnecessarily create a new authorization record. Existing merchant connections reference the authorization ID, so preserving that ID maintains the relationship.

---

## 2. Authorization Database Design

The database enforces the following constraints:

| Requirement | Implementation |
|---|---|
| One Zoho authorization per tenant | Unique constraint on `zoho_authorizations.tenant_id` |
| Preserve authorization identity | `INSERT ... ON CONFLICT DO UPDATE` |
| Keep merchant connections associated with their authorization | Foreign key from `merchant_connections.authorization_id` |
| Ensure authorization belongs to the same tenant | Composite foreign key |
| Only one active organization connection per tenant | Partial unique index |
| Ensure active connection belongs to its tenant | Composite foreign key from `tenants` |

### 2.1 Authorization Record Updates

The authorization upsert supports two cases:

**New refresh token provided:**

- Insert a new authorization if one does not exist.
- Update the existing authorization if one already exists.
- Replace the encrypted refresh token.
- Update granted scopes and authorization status.
- Preserve the existing authorization ID.

**Refresh token omitted:**

- Update an existing active authorization's scopes and status.
- Preserve its existing encrypted refresh token.
- Do not insert a new authorization without a refresh token.
- Do not reactivate a revoked authorization without a new refresh token.

This ensures that an authorization cannot become active without a usable refresh token.

---

## 3. Merchant Organization Connection Management

During the reconnection implementation, we identified that organization connections needed consistent handling when switching the active organization.

The `set_active_organization_connection()` repository function was updated to handle this transactionally.

### 3.1 Expected Transaction Sequence

When a tenant selects an organization:

1. Lock the tenant row.
2. Verify that the requested merchant connection belongs to the tenant.
3. Verify that its associated Zoho authorization is active.
4. Retrieve the tenant's currently active connection, excluding the requested connection.
5. Mark the previous active connection as `inactive`, if one exists.
6. Mark the requested connection as `active`.
7. Update the tenant's active organization connection pointer.
8. Commit the transaction.

If any operation fails, the transaction must roll back.

### 3.2 Connection Statuses

| Status | Meaning |
|---|---|
| `pending` | Connection setup has started but is not yet completed successfully. |
| `active` | Currently selected organization connection. |
| `inactive` | Previously connected successfully but is no longer selected. |
| `revoked` | Connection or authorization has been revoked. |
| `error` | Connection encountered an error. |

### 3.3 Database Constraint

A partial unique index ensures that a tenant cannot have multiple active organization connections.

```sql
CREATE UNIQUE INDEX one_active_connection_per_tenant
ON merchant_connections (tenant_id)
WHERE status = 'active';
```

**Implementation Status:** Completed.

---

## 4. Handling Invalid or Revoked Refresh Tokens

### 4.1 Problem

An authorization may become invalid even when the database still marks it as active.

For example:

1. A user successfully connects Zoho.
2. Yojak stores the encrypted refresh token.
3. The authorization status is `active`.
4. The user later revokes Yojak's access from their Zoho account.
5. The database still contains the previous active status.

The application cannot reliably determine whether the refresh token has been revoked simply by checking the database.

It must attempt to use the refresh token with Zoho to discover whether it is still valid.

### 4.2 Error Classification

We must distinguish between definitive authorization failures and temporary integration failures.

| Failure | Expected Behaviour |
|---|---|
| Zoho definitively rejects an invalid or revoked refresh token | Mark authorization as `revoked`. |
| Network timeout or connection error | Preserve existing authorization status. |
| Temporary Zoho server failure | Preserve existing authorization status. |
| Invalid client credentials or configuration | Report an integration/configuration error. Do not revoke merchant authorization. |
| Unexpected Zoho response | Raise an appropriate error without incorrectly changing authorization status. |

### 4.3 Implementation Sequence

| Step | Implementation | Status |
|---|---|---|
| 1 | Introduce a dedicated exception for definitive refresh-token rejection. | Completed |
| 2 | Preserve Zoho's actual error code for classification. | Completed |
| 3 | Add a repository function to update authorization status. | Completed |
| 4 | Handle definitive token rejection in `get_access_token()`. | Completed |
| 5 | Invalidate cached access tokens when authorization becomes unusable. | Completed |
| 6 | Add tests for revoked tokens and temporary failures. | Completed |

### 4.4 Expected Token Manager Behaviour

```text
get_access_token()
       |
       v
Check cached access token
       |
       +-----------------------------+
       |                             |
       v                             v
Valid cached token             Cache unavailable
       |                             |
       v                             v
Return cached token           Refresh using Zoho
                                     |
                                     v
                              Classify response
                                     |
                    +----------------+----------------+
                    |                |                |
                    v                v                v
              Invalid token    Temporary error   Configuration
                    |                |                |
                    v                v                v
             Mark revoked      Preserve status   Preserve status
                    |
                    v
             Invalidate cache
                    |
                    v
              Raise exception
```

**Implementation Status:** Core handling completed. Application-level regression verification remains part of the testing work.

---

## 5. Reusing Existing Authorization in `/oauth/zoho/connect`

### 5.1 Intended Behaviour

The connect endpoint must decide whether to reuse an existing authorization or initiate a new Zoho consent flow.

| Existing Authorization | Scope Check | Expected Action |
|---|---|---|
| No authorization | Not applicable | Initiate OAuth consent |
| Active | All required scopes available | Validate token and reuse authorization |
| Active | Required scopes missing | Initiate OAuth consent |
| Revoked | Not applicable | Initiate fresh OAuth consent |
| Error | Not applicable | Initiate fresh OAuth consent |
| Pending | Not applicable | Initiate fresh OAuth consent |

### 5.2 Why Token Validation Is Necessary

Checking only whether the database status is `active` is insufficient.

An authorization may have been revoked externally while the database still contains an active status.

For an active authorization with sufficient scopes:

1. Call `get_access_token()`.
2. If a valid cached token exists, reuse it.
3. Otherwise, attempt to refresh the access token through Zoho.
4. If successful, reuse the existing authorization.
5. If Zoho definitively rejects the refresh token, the token manager marks the authorization as revoked.
6. Initiate fresh Zoho consent.
7. If a temporary or configuration error occurs, return an appropriate error instead of treating the authorization as revoked.

### 5.3 Token Validation and Caching

Calling `get_access_token()` does not necessarily result in a network request.

| Token State | Behaviour |
|---|---|
| Valid cached access token | Reuse cached token |
| Cache expired or unavailable | Refresh through Zoho |
| Refresh token revoked | Mark authorization as revoked |
| Invalid client credentials | Raise configuration/integration error |

**Implementation Status:** Completed.

---

## 6. Missing Scopes and Reauthorization

### 6.1 Problem

The required OAuth scopes may change as Yojak introduces additional Zoho Inventory capabilities.

An existing authorization may be valid but insufficient for the currently required operations.

Therefore, before reusing an existing authorization, Yojak must compare its granted scopes against the required scopes.

### 6.2 Implementation

The following changes were made:

| Step | Implementation | Status |
|---|---|---|
| 6.1 | Create a scope comparison helper. | Completed |
| 6.2 | Integrate scope validation into `/oauth/zoho/connect`. | Completed |
| 6.3 | Preserve an existing refresh token during reauthorization when a new token is omitted. | Completed |

### 6.3 Scope Validation Behaviour

```text
Existing authorization
        |
        v
Compare granted scopes
with required scopes
        |
        +---------------------------+
        |                           |
        v                           v
All scopes available         Scopes missing
        |                           |
        v                           v
Validate existing token      Initiate Zoho consent
        |
        v
Reuse authorization
```

Scope validation happens before token validation because there is no benefit in validating an authorization that already lacks required permissions.

### 6.4 Refresh Token Preservation

Zoho authorization responses must not be assumed to contain a new refresh token in every situation.

The repository supports the following behaviour:

| Situation | Expected Behaviour |
|---|---|
| New refresh token provided | Encrypt and store the new token |
| Existing authorization with a new refresh token | Replace the old encrypted token |
| Existing active authorization with no new refresh token | Preserve the existing token and update scopes |
| Existing revoked authorization with no new refresh token | Return `None`; keep authorization revoked |
| No existing authorization and no refresh token | Return `None`; do not create an invalid authorization |

Two separate database operations handle these cases:

1. When a refresh token is provided, use `INSERT ... ON CONFLICT` to insert or update the authorization.
2. When the refresh token is `None`, update only an existing active authorization. Do not attempt an insert.

This prevents a revoked authorization from being reactivated without a new refresh token.

**Implementation Status:** Completed.

---

## 7. OAuth Regression Testing

The core OAuth implementation and its automated regression coverage have been completed.

The test suite includes coverage for:

- Existing authorization reuse.
- OAuth state creation, validation, and single-use consumption.
- Authorization code exchange and refresh-token handling.
- Refresh-token encryption and decryption.
- Access-token caching and concurrency control.
- Invalid and revoked refresh-token handling.
- Temporary Zoho failures and authorization status preservation.
- Missing OAuth scopes and reauthorization behaviour.
- Authorization persistence and identity preservation.
- Database availability failures.
- Organization discovery and selection.
- Merchant connection creation, reuse, and active-connection switching.

Relevant test modules include:

- `tests/test_zoho_client.py`
- `tests/test_token_manager.py`
- `tests/test_repositories.py`
- `tests/test_main.py`
- `tests/test_zoho_organization_endpoints.py`
- `tests/test_database_errors.py`

Run the complete test suite using:

```bash
pytest -v
```

These tests primarily verify application behaviour using controlled dependencies and mocks. They must not be treated as proof of a successful live integration with WorkOS, Zoho Inventory, and Supabase.

**Status:** Automated regression coverage implemented. Live end-to-end verification remains pending.

---

## 8. Zoho Organization Discovery and Connection Management

The organization discovery and selection implementation has been completed.

### 8.1 Organization Discovery

The endpoint:

```http
GET /oauth/zoho/organizations
```

uses the authenticated tenant's active Zoho authorization to retrieve organizations from Zoho Inventory.

It supports the following outcomes:

| Scenario | Expected behaviour |
|---|---|
| No active Zoho authorization | Return HTTP 404 |
| No accessible organizations | Return `no_organizations_found` |
| One accessible organization | Create or reuse its connection and activate it |
| Multiple accessible organizations | Return `selection_required` and the available organizations |

### 8.2 Organization Selection

The endpoint:

```http
POST /oauth/zoho/organizations/select
```

accepts an organization ID and verifies that the organization is accessible through the current Zoho authorization.

The endpoint then creates or reuses the merchant connection and activates it.

The organization ID supplied by the caller is never trusted without verification against Zoho's organization list.

### 8.3 Active Organization Switching

The repository function `set_active_organization_connection()` manages active organization switching transactionally.

When a different organization is selected:

1. Lock the tenant row.
2. Verify that the selected connection belongs to the tenant.
3. Verify that its linked authorization is active.
4. Mark the previously active connection as `inactive`.
5. Mark the selected connection as `active`.
6. Update the tenant's active organization pointer.
7. Commit the transaction.

The database's partial unique index ensures that a tenant cannot have more than one active merchant connection.

Existing connections are reused when an organization is selected again.

**Status:** Implementation and automated endpoint coverage completed. Live multi-organization verification remains pending.

---

## 9. Live End-to-End Verification

Automated tests are necessary but do not establish that the complete integration works with the actual external services.

The next verification milestone covers the following:

### 9.1 WorkOS Authentication

- [ ] Start the local Yojak application.
- [ ] Verify application health and database readiness.
- [ ] Authenticate through WorkOS using an MCP client.
- [ ] Invoke `yojak_status` successfully.
- [ ] Verify authenticated access to the protected REST endpoints.

### 9.2 Zoho OAuth

- [ ] Initiate Zoho authorization.
- [ ] Complete the real Zoho consent flow.
- [ ] Verify callback state validation and consumption.
- [ ] Verify authorization code exchange.
- [ ] Verify refresh-token encryption and persistence.
- [ ] Verify access-token retrieval through the token manager.
- [ ] Verify existing authorization reuse when applicable.

### 9.3 Multiple-Organization Discovery

The current test Zoho account contains two organizations:

| Organization | Organization ID |
|---|---|
| Ishaan Demo Store | `60090589249` |
| Ishaan Demo Store 2 | `60096804481` |

The live test must verify that both organizations are returned by Zoho's organization discovery API through the same authorization.

Expected behaviour:

- [ ] Both organizations are discovered.
- [ ] The response indicates that organization selection is required.
- [ ] Neither organization is automatically activated by the multiple-organization discovery branch.

### 9.4 Organization Selection and Switching

- [ ] Select Ishaan Demo Store.
- [ ] Verify that its connection becomes active.
- [ ] Select Ishaan Demo Store 2.
- [ ] Verify that the second connection becomes active.
- [ ] Verify that the first connection becomes inactive.
- [ ] Select Ishaan Demo Store again.
- [ ] Verify that the existing connection is reused.
- [ ] Verify that the active connection pointer is updated correctly.
- [ ] Verify that an inaccessible organization ID is rejected.

### 9.5 Database Verification

- [ ] Verify that both organization connections belong to the same tenant.
- [ ] Verify that both connections reference the same Zoho authorization.
- [ ] Verify that exactly one merchant connection is active.
- [ ] Verify that the tenant's active connection pointer references that active connection.
- [ ] Verify that the refresh token is not exposed through application responses or logs.

**Status:** Pending live end-to-end verification.

The repeatable test procedure is documented in [`end-to-end-testing.md`](end-to-end-testing.md).

---

## 10. Next Development Milestone

Once live verification of WorkOS authentication, Zoho OAuth, and organization connection management is complete, development will move to the initial read-only inventory MCP tools.

| Tool | Responsibility |
|---|---|
| `list_items` | Retrieve inventory items from the selected Zoho organization. |
| `get_item` | Retrieve details of a specific inventory item. |
| `list_sales_orders` | Retrieve sales orders from the selected Zoho organization. |
| `get_sales_order` | Retrieve details of a specific sales order. |

The implementation will build on the existing authentication, tenant resolution, token management, and organization connection architecture.

Additional capabilities will include pagination, API error handling, and appropriate response normalization.

The initial inventory integration will remain read-only.

---

## 11. Current Progress Summary

| Area | Status |
|---|---|
| One Zoho authorization per tenant | Implemented |
| Authorization create-or-update behaviour | Implemented |
| Authorization ID preservation | Implemented |
| Merchant connection authorization references | Implemented |
| Organization connection switching | Implemented |
| Inactive connection status | Implemented |
| One active organization connection per tenant | Implemented |
| Invalid/revoked refresh-token handling | Implemented |
| Temporary failure classification | Implemented |
| Access-token cache invalidation | Implemented |
| Existing authorization reuse | Implemented |
| Missing-scope detection | Implemented |
| Reauthorization flow | Implemented |
| Refresh-token preservation | Implemented |
| Automated OAuth regression coverage | Implemented |
| Automated organization endpoint coverage | Implemented |
| Live WorkOS authentication verification | Pending |
| Live Zoho OAuth verification | Pending |
| Live token-management verification | Pending |
| Live organization discovery verification | Pending |
| Live multi-organization selection and switching | Pending |
| Initial read-only inventory MCP tools | Planned |

---

*This document tracks the implementation and verification status of Yojak's Zoho OAuth lifecycle and merchant organization connection management.*