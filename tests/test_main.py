import asyncpg

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app import main


@pytest.fixture
def client(monkeypatch):
    # Mock the database pool
    monkeypatch.setattr(
        main.runtime,
        "database_pool",
        object(),
    )

    # Mock WorkOS token verification
    mock_token = SimpleNamespace(
        subject="workos_user_test_123"
    )

    monkeypatch.setattr(
        main.workos_auth.token_verifier,
        "verify_token",
        AsyncMock(return_value=mock_token),
    )

    return TestClient(app)


def mock_tenant_resolution(monkeypatch):
    monkeypatch.setattr(
        main,
        "get_or_create_tenant",
        AsyncMock(
            return_value={
                "id": "tenant-test-123",
            }
        ),
    )


def mock_existing_authorization(
    monkeypatch,
    status,
    granted_scopes=None,
):
    if granted_scopes is None:
        granted_scopes = [
            "ZohoInventory.items.READ",
            "ZohoInventory.salesorders.READ",
            "ZohoInventory.settings.READ",
        ]

    monkeypatch.setattr(
        main,
        "get_zoho_authorization_for_tenant",
        AsyncMock(
            return_value={
                "id": "authorization-test-123",
                "tenant_id": "tenant-test-123",
                "granted_scopes": granted_scopes,
                "status": status,
            }
        ),
    )


def mock_oauth_initiation(monkeypatch):
    monkeypatch.setattr(
        main,
        "generate_oauth_state",
        lambda: "test-oauth-state",
    )

    monkeypatch.setattr(
        main,
        "create_oauth_state",
        AsyncMock(return_value=None),
    )

    monkeypatch.setattr(
        main,
        "build_authorization_url",
        lambda state: (
            f"https://accounts.zoho.com/oauth/v2/auth?state={state}"
        ),
    )


# ---------------------------------------------------------
# Test 1: Reuse an existing active authorization
# ---------------------------------------------------------

def test_connect_zoho_reuses_active_authorization(
    client,
    monkeypatch,
):
    mock_tenant_resolution(monkeypatch)
    mock_existing_authorization(monkeypatch, "active")

    mock_get_access_token = AsyncMock(
        return_value="test-access-token"
    )

    monkeypatch.setattr(
        main,
        "get_access_token",
        mock_get_access_token,
    )

    mock_create_state = AsyncMock()

    monkeypatch.setattr(
        main,
        "create_oauth_state",
        mock_create_state,
    )

    response = client.get(
        "/oauth/zoho/connect",
        headers={
            "Authorization": "Bearer test-workos-token"
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "authorization_reused"
    assert data["provider"] == "zoho_inventory"
    assert data["authorization_id"] == "authorization-test-123"

    mock_get_access_token.assert_awaited_once_with(
        main.runtime.database_pool,
        "tenant-test-123",
        "authorization-test-123",
    )

    # Existing authorization should not initiate new OAuth state
    mock_create_state.assert_not_awaited()


# ---------------------------------------------------------
# Test 2: Start OAuth when no authorization exists
# ---------------------------------------------------------

def test_connect_zoho_starts_oauth_without_existing_authorization(
    client,
    monkeypatch,
):
    mock_tenant_resolution(monkeypatch)

    monkeypatch.setattr(
        main,
        "get_zoho_authorization_for_tenant",
        AsyncMock(return_value=None),
    )

    mock_oauth_initiation(monkeypatch)

    response = client.get(
        "/oauth/zoho/connect",
        headers={
            "Authorization": "Bearer test-workos-token"
        },
        follow_redirects=False,
    )

    assert response.status_code == 302

    assert response.headers["location"] == (
        "https://accounts.zoho.com/oauth/v2/auth"
        "?state=test-oauth-state"
    )

    main.create_oauth_state.assert_awaited_once_with(
        main.runtime.database_pool,
        "test-oauth-state",
        "tenant-test-123",
    )


# ---------------------------------------------------------
# Test 3: Start OAuth for revoked authorization
# ---------------------------------------------------------

def test_connect_zoho_starts_oauth_for_revoked_authorization(
    client,
    monkeypatch,
):
    mock_tenant_resolution(monkeypatch)
    mock_existing_authorization(monkeypatch, "revoked")
    mock_oauth_initiation(monkeypatch)

    response = client.get(
        "/oauth/zoho/connect",
        headers={
            "Authorization": "Bearer test-workos-token"
        },
        follow_redirects=False,
    )

    assert response.status_code == 302

    assert response.headers["location"] == (
        "https://accounts.zoho.com/oauth/v2/auth"
        "?state=test-oauth-state"
    )

    main.create_oauth_state.assert_awaited_once()


# ---------------------------------------------------------
# Test 4: Start OAuth for error authorization
# ---------------------------------------------------------

def test_connect_zoho_starts_oauth_for_error_authorization(
    client,
    monkeypatch,
):
    mock_tenant_resolution(monkeypatch)
    mock_existing_authorization(monkeypatch, "error")
    mock_oauth_initiation(monkeypatch)

    response = client.get(
        "/oauth/zoho/connect",
        headers={
            "Authorization": "Bearer test-workos-token"
        },
        follow_redirects=False,
    )

    assert response.status_code == 302

    main.create_oauth_state.assert_awaited_once()


# ---------------------------------------------------------
# Test 5: Start OAuth for pending authorization
# ---------------------------------------------------------

def test_connect_zoho_starts_oauth_for_pending_authorization(
    client,
    monkeypatch,
):
    mock_tenant_resolution(monkeypatch)
    mock_existing_authorization(monkeypatch, "pending")
    mock_oauth_initiation(monkeypatch)

    response = client.get(
        "/oauth/zoho/connect",
        headers={
            "Authorization": "Bearer test-workos-token"
        },
        follow_redirects=False,
    )

    assert response.status_code == 302

    main.create_oauth_state.assert_awaited_once()


# ---------------------------------------------------------
# Test 6: Reject request without bearer token
# ---------------------------------------------------------

def test_connect_zoho_rejects_missing_bearer_token(client):
    response = client.get("/oauth/zoho/connect")

    assert response.status_code == 401

    assert response.json()["detail"] == (
        "A valid bearer token is required."
    )


# ---------------------------------------------------------
# Test 7: Reject invalid WorkOS token
# ---------------------------------------------------------

def test_connect_zoho_rejects_invalid_workos_token(
    client,
    monkeypatch,
):
    monkeypatch.setattr(
        main.workos_auth.token_verifier,
        "verify_token",
        AsyncMock(side_effect=Exception("Invalid token")),
    )

    response = client.get(
        "/oauth/zoho/connect",
        headers={
            "Authorization": "Bearer invalid-token"
        },
    )

    assert response.status_code == 401

    assert response.json()["detail"] == (
        "Invalid or Expired access token."
    )



# ---------------------------------------------------------
# Test 8: Start OAuth when required scopes are missing
# ---------------------------------------------------------

def test_connect_zoho_starts_oauth_when_scopes_are_missing(
    client,
    monkeypatch,
):
    mock_tenant_resolution(monkeypatch)

    mock_existing_authorization(
        monkeypatch,
        "active",
        granted_scopes=[
            "ZohoInventory.items.READ",
            "ZohoInventory.salesorders.READ",
        ],
    )

    mock_oauth_initiation(monkeypatch)

    mock_get_access_token = AsyncMock()

    monkeypatch.setattr(
        main,
        "get_access_token",
        mock_get_access_token,
    )

    response = client.get(
        "/oauth/zoho/connect",
        headers={
            "Authorization": "Bearer test-workos-token"
        },
        follow_redirects=False,
    )

    assert response.status_code == 302

    assert response.headers["location"] == (
        "https://accounts.zoho.com/oauth/v2/auth"
        "?state=test-oauth-state"
    )

    main.create_oauth_state.assert_awaited_once()

    # Token validation should not happen when scopes are missing
    mock_get_access_token.assert_not_awaited()


# ---------------------------------------------------------
# Test 9: Start OAuth when the existing refresh token is invalid
# ---------------------------------------------------------

def test_connect_zoho_starts_oauth_for_invalid_refresh_token(
    client,
    monkeypatch,
):
    mock_tenant_resolution(monkeypatch)
    mock_existing_authorization(monkeypatch, "active")
    mock_oauth_initiation(monkeypatch)

    mock_get_access_token = AsyncMock(
        side_effect=main.ZohoRefreshTokenError(
            error_code = "invalid_code"
        )
    )

    monkeypatch.setattr(
        main,
        "get_access_token",
        mock_get_access_token,
    )

    response = client.get(
        "/oauth/zoho/connect",
        headers={
            "Authorization": "Bearer test-workos-token"
        },
        follow_redirects=False,
    )

    assert response.status_code == 302

    assert response.headers["location"] == (
        "https://accounts.zoho.com/oauth/v2/auth"
        "?state=test-oauth-state"
    )

    mock_get_access_token.assert_awaited_once_with(
        main.runtime.database_pool,
        "tenant-test-123",
        "authorization-test-123",
    )

    main.create_oauth_state.assert_awaited_once()


# ---------------------------------------------------------
# Test 10: Do not initiate OAuth for other refresh token errors
# ---------------------------------------------------------

def test_connect_zoho_returns_error_for_non_revocation_refresh_failure(
    client,
    monkeypatch,
):
    mock_tenant_resolution(monkeypatch)
    mock_existing_authorization(monkeypatch, "active")

    mock_create_state = AsyncMock()

    monkeypatch.setattr(
        main,
        "create_oauth_state",
        mock_create_state,
    )

    mock_get_access_token = AsyncMock(
        side_effect=main.ZohoRefreshTokenError(
            error_code = "invalid_client_secret"
            
        )
    )

    monkeypatch.setattr(
        main,
        "get_access_token",
        mock_get_access_token,
    )

    response = client.get(
        "/oauth/zoho/connect",
        headers={
            "Authorization": "Bearer test-workos-token"
        },
        follow_redirects=False,
    )

    assert response.status_code == 502

    assert response.json()["detail"] == (
        "Unable to validate the existing Zoho authorization."
    )

    # No new OAuth state should be created
    mock_create_state.assert_not_awaited()



# ---------------------------------------------------------
# OAuth Callback Tests
# ---------------------------------------------------------


# Test 11: Reject callback when OAuth state is missing

def test_zoho_callback_rejects_missing_state(client, monkeypatch):

    mock_consume_state = AsyncMock()

    monkeypatch.setattr(
        main,
        "consume_oauth_state",
        mock_consume_state,
    )

    response = client.get("/oauth/zoho/callback")

    assert response.status_code == 400

    assert response.json()["detail"] == (
        "OAuth state is missing."
    )

    # State validation should not be attempted
    mock_consume_state.assert_not_awaited()


# Test 12: Reject invalid, expired, or already-used OAuth state

def test_zoho_callback_rejects_invalid_state(client, monkeypatch):

    mock_consume_state = AsyncMock(return_value=None)

    mock_exchange_code = AsyncMock()

    monkeypatch.setattr(
        main,
        "consume_oauth_state",
        mock_consume_state,
    )

    monkeypatch.setattr(
        main,
        "exchange_authorization_code",
        mock_exchange_code,
    )

    response = client.get(
        "/oauth/zoho/callback",
        params={"state": "invalid-oauth-state"},
    )

    assert response.status_code == 400

    assert response.json()["detail"] == (
        "OAuth state is invalid, expired, or already used."
    )

    mock_consume_state.assert_awaited_once_with(
        main.runtime.database_pool,
        "invalid-oauth-state",
    )

    # Token exchange must never happen for an invalid state
    mock_exchange_code.assert_not_awaited()


# Test 13: Handle OAuth state validation database failure

def test_zoho_callback_handles_state_validation_failure(
    client,
    monkeypatch,
):

    mock_consume_state = AsyncMock(
        side_effect=Exception("Database error")
    )

    mock_exchange_code = AsyncMock()

    monkeypatch.setattr(
        main,
        "consume_oauth_state",
        mock_consume_state,
    )

    monkeypatch.setattr(
        main,
        "exchange_authorization_code",
        mock_exchange_code,
    )

    response = client.get(
        "/oauth/zoho/callback",
        params={"state": "test-oauth-state"},
    )

    assert response.status_code == 500

    assert response.json()["detail"] == (
        "Unable to validate OAuth state."
    )

    mock_consume_state.assert_awaited_once()

    # Token exchange must not happen if state validation fails
    mock_exchange_code.assert_not_awaited()



# ---------------------------------------------------------
# OAuth Callback Error Handling Tests
# ---------------------------------------------------------


# Test 14: Handle authorization denial by the user

def test_zoho_callback_handles_authorization_denial(
    client,
    monkeypatch,
):
    mock_consume_state = AsyncMock(
        return_value="tenant-test-123"
    )

    mock_exchange_code = AsyncMock()

    monkeypatch.setattr(
        main,
        "consume_oauth_state",
        mock_consume_state,
    )

    monkeypatch.setattr(
        main,
        "exchange_authorization_code",
        mock_exchange_code,
    )

    response = client.get(
        "/oauth/zoho/callback",
        params={
            "state": "test-oauth-state",
            "error": "access_denied",
        },
    )

    assert response.status_code == 400

    assert response.json()["detail"] == (
        "Zoho authorization was denied or failed."
    )

    mock_consume_state.assert_awaited_once_with(
        main.runtime.database_pool,
        "test-oauth-state",
    )

    # Authorization code exchange must not happen
    mock_exchange_code.assert_not_awaited()


# Test 15: Reject callback when authorization code is missing

def test_zoho_callback_rejects_missing_authorization_code(
    client,
    monkeypatch,
):
    mock_consume_state = AsyncMock(
        return_value="tenant-test-123"
    )

    mock_exchange_code = AsyncMock()

    monkeypatch.setattr(
        main,
        "consume_oauth_state",
        mock_consume_state,
    )

    monkeypatch.setattr(
        main,
        "exchange_authorization_code",
        mock_exchange_code,
    )

    response = client.get(
        "/oauth/zoho/callback",
        params={
            "state": "test-oauth-state",
        },
    )

    assert response.status_code == 400

    assert response.json()["detail"] == (
        "Authorization code is missing."
    )

    mock_consume_state.assert_awaited_once()

    # No authorization code means no token exchange
    mock_exchange_code.assert_not_awaited()


# Test 16: Handle authorization code exchange failure

def test_zoho_callback_handles_token_exchange_failure(
    client,
    monkeypatch,
):
    mock_consume_state = AsyncMock(
        return_value="tenant-test-123"
    )

    mock_exchange_code = AsyncMock(
        side_effect=Exception("Zoho token exchange failed")
    )

    monkeypatch.setattr(
        main,
        "consume_oauth_state",
        mock_consume_state,
    )

    monkeypatch.setattr(
        main,
        "exchange_authorization_code",
        mock_exchange_code,
    )

    response = client.get(
        "/oauth/zoho/callback",
        params={
            "state": "test-oauth-state",
            "code": "test-authorization-code",
        },
    )

    assert response.status_code == 502

    assert response.json()["detail"] == (
        "Unable to exchange the Zoho authorization code."
    )

    mock_consume_state.assert_awaited_once()

    mock_exchange_code.assert_awaited_once_with(
        "test-authorization-code"
    )


# Test 17: Test Successful OAuth callback

def test_zoho_callback_successfully_persists_authorization(
    client,
    monkeypatch,
):
    mock_consume_state = AsyncMock(
        return_value="tenant-test-123"
    )

    mock_exchange_code = AsyncMock(
        return_value={
            "access_token": "test-access-token",
            "refresh_token": "test-refresh-token",
            "scope": (
                "ZohoInventory.items.READ,"
                "ZohoInventory.salesorders.READ,"
                "ZohoInventory.settings.READ"
            ),
        }
    )

    mock_encrypt_token = lambda token: b"encrypted-refresh-token"

    monkeypatch.setattr(
        main,
        "encrypt_refresh_token",
        mock_encrypt_token,
    )

    mock_create_authorization = AsyncMock(
        return_value={
            "id": "authorization-test-123",
            "tenant_id": "tenant-test-123",
            "granted_scopes": [
                "ZohoInventory.items.READ",
                "ZohoInventory.salesorders.READ",
                "ZohoInventory.settings.READ",
            ],
            "status": "active",
        }
    )

    monkeypatch.setattr(
        main,
        "consume_oauth_state",
        mock_consume_state,
    )

    monkeypatch.setattr(
        main,
        "exchange_authorization_code",
        mock_exchange_code,
    )

    monkeypatch.setattr(
        main,
        "create_zoho_authorization",
        mock_create_authorization,
    )

    response = client.get(
        "/oauth/zoho/callback",
        params={
            "state": "test-oauth-state",
            "code": "test-authorization-code",
        },
    )

    assert response.status_code == 200

    assert response.json() == {
        "status": "connected",
        "provider": "zoho_inventory",
        "message": (
            "Zoho authorization completed successfully."
            "You can now discover your organizations."
        ),
        "authorization_id": "authorization-test-123",
    }

    mock_consume_state.assert_awaited_once_with(
        main.runtime.database_pool,
        "test-oauth-state",
    )

    mock_exchange_code.assert_awaited_once_with(
        "test-authorization-code"
    )

    mock_create_authorization.assert_awaited_once_with(
        pool=main.runtime.database_pool,
        tenant_id="tenant-test-123",
        refresh_token_encrypted=b"encrypted-refresh-token",
        granted_scopes=[
            "ZohoInventory.items.READ",
            "ZohoInventory.salesorders.READ",
            "ZohoInventory.settings.READ",
        ],
    )


# Test 18: Reject an invalid scope format

def test_zoho_callback_rejects_invalid_scope_format(
    client,
    monkeypatch,
):
    mock_consume_state = AsyncMock(
        return_value="tenant-test-123"
    )

    mock_exchange_code = AsyncMock(
        return_value={
            "access_token": "test-access-token",
            "refresh_token": "test-refresh-token",
            "scope": {"unexpected": "format"},
        }
    )

    mock_create_authorization = AsyncMock()

    monkeypatch.setattr(
        main,
        "consume_oauth_state",
        mock_consume_state,
    )

    monkeypatch.setattr(
        main,
        "exchange_authorization_code",
        mock_exchange_code,
    )

    monkeypatch.setattr(
        main,
        "encrypt_refresh_token",
        lambda token: b"encrypted-refresh-token",
    )

    monkeypatch.setattr(
        main,
        "create_zoho_authorization",
        mock_create_authorization,
    )

    response = client.get(
        "/oauth/zoho/callback",
        params={
            "state": "test-oauth-state",
            "code": "test-authorization-code",
        },
    )

    assert response.status_code == 502

    assert response.json()["detail"] == (
        "Zoho returned an invalid scope format."
    )

    mock_create_authorization.assert_not_awaited()


# Test 19: Reauthorization preserves the existing authorization ID

def test_zoho_callback_reauthorization_preserves_authorization_id(
    client,
    monkeypatch,
):
    existing_authorization_id = "authorization-existing-123"

    mock_consume_state = AsyncMock(
        return_value="tenant-test-123"
    )

    mock_exchange_code = AsyncMock(
        return_value={
            "access_token": "new-access-token",
            "refresh_token": "new-refresh-token",
            "scope": (
                "ZohoInventory.items.READ,"
                "ZohoInventory.salesorders.READ,"
                "ZohoInventory.settings.READ"
            ),
        }
    )

    mock_create_authorization = AsyncMock(
        return_value={
            "id": existing_authorization_id,
            "tenant_id": "tenant-test-123",
            "status": "active",
        }
    )

    monkeypatch.setattr(
        main,
        "consume_oauth_state",
        mock_consume_state,
    )

    monkeypatch.setattr(
        main,
        "exchange_authorization_code",
        mock_exchange_code,
    )

    monkeypatch.setattr(
        main,
        "encrypt_refresh_token",
        lambda token: b"encrypted-new-refresh-token",
    )

    monkeypatch.setattr(
        main,
        "create_zoho_authorization",
        mock_create_authorization,
    )

    response = client.get(
        "/oauth/zoho/callback",
        params={
            "state": "test-oauth-state",
            "code": "new-authorization-code",
        },
    )

    assert response.status_code == 200

    assert response.json()["status"] == "connected"

    assert response.json()["authorization_id"] == (
        existing_authorization_id
    )

    mock_create_authorization.assert_awaited_once_with(
        pool=main.runtime.database_pool,
        tenant_id="tenant-test-123",
        refresh_token_encrypted=b"encrypted-new-refresh-token",
        granted_scopes=[
            "ZohoInventory.items.READ",
            "ZohoInventory.salesorders.READ",
            "ZohoInventory.settings.READ",
        ],
    )


# Test 20: Handle a None persistence result

def test_zoho_callback_handles_failed_authorization_persistence(
    client,
    monkeypatch,
):
    mock_consume_state = AsyncMock(
        return_value="tenant-test-123"
    )

    mock_exchange_code = AsyncMock(
        return_value={
            "access_token": "test-access-token",
            "refresh_token": "test-refresh-token",
            "scope": (
                "ZohoInventory.items.READ,"
                "ZohoInventory.salesorders.READ,"
                "ZohoInventory.settings.READ"
            ),
        }
    )

    mock_create_authorization = AsyncMock(
        return_value=None
    )

    monkeypatch.setattr(
        main,
        "consume_oauth_state",
        mock_consume_state,
    )

    monkeypatch.setattr(
        main,
        "exchange_authorization_code",
        mock_exchange_code,
    )

    monkeypatch.setattr(
        main,
        "encrypt_refresh_token",
        lambda token: b"encrypted-refresh-token",
    )

    monkeypatch.setattr(
        main,
        "create_zoho_authorization",
        mock_create_authorization,
    )

    response = client.get(
        "/oauth/zoho/callback",
        params={
            "state": "test-oauth-state",
            "code": "test-authorization-code",
        },
    )

    assert response.status_code == 500

    assert response.json()["detail"] == (
        "Unable to save the Zoho Authorization."
    )

    mock_create_authorization.assert_awaited_once()



# ---------------------------------------------------------
# Database Availability Regression Tests
# ---------------------------------------------------------


# Test 21: Database failure while retrieving existing authorization

def test_connect_zoho_returns_503_when_authorization_retrieval_fails(
    client,
    monkeypatch,
):
    mock_tenant_resolution(monkeypatch)

    mock_get_authorization = AsyncMock(
        side_effect=asyncpg.PostgresConnectionError(
            "Simulated database failure"
        )
    )

    monkeypatch.setattr(
        main,
        "get_zoho_authorization_for_tenant",
        mock_get_authorization,
    )

    response = client.get(
        "/oauth/zoho/connect",
        headers={
            "Authorization": "Bearer test-workos-token"
        },
    )

    assert response.status_code == 503
    assert response.json() == {
        "status": "service_unavailable",
        "message": (
            "Database service is temporarily unavailable. "
            "Please try again later."
        ),
    }

    mock_get_authorization.assert_awaited_once()


# Test 22: Database failure while validating existing authorization

def test_connect_zoho_returns_503_when_access_token_validation_fails(
    client,
    monkeypatch,
):
    mock_tenant_resolution(monkeypatch)
    mock_existing_authorization(monkeypatch, "active")

    mock_get_access_token = AsyncMock(
        side_effect=asyncpg.PostgresConnectionError(
            "Simulated database failure"
        )
    )

    monkeypatch.setattr(
        main,
        "get_access_token",
        mock_get_access_token,
    )

    response = client.get(
        "/oauth/zoho/connect",
        headers={
            "Authorization": "Bearer test-workos-token"
        },
    )

    assert response.status_code == 503
    assert response.json()["status"] == "service_unavailable"

    mock_get_access_token.assert_awaited_once_with(
        main.runtime.database_pool,
        "tenant-test-123",
        "authorization-test-123",
    )


# Test 23: Database failure while creating OAuth state

def test_connect_zoho_returns_503_when_oauth_state_creation_fails(
    client,
    monkeypatch,
):
    mock_tenant_resolution(monkeypatch)

    monkeypatch.setattr(
        main,
        "get_zoho_authorization_for_tenant",
        AsyncMock(return_value=None),
    )

    mock_create_state = AsyncMock(
        side_effect=asyncpg.PostgresConnectionError(
            "Simulated database failure"
        )
    )

    monkeypatch.setattr(
        main,
        "generate_oauth_state",
        lambda: "test-oauth-state",
    )

    monkeypatch.setattr(
        main,
        "create_oauth_state",
        mock_create_state,
    )

    response = client.get(
        "/oauth/zoho/connect",
        headers={
            "Authorization": "Bearer test-workos-token"
        },
    )

    assert response.status_code == 503
    assert response.json()["status"] == "service_unavailable"

    mock_create_state.assert_awaited_once_with(
        main.runtime.database_pool,
        "test-oauth-state",
        "tenant-test-123",
    )


# Test 24: Database failure while consuming OAuth state

def test_zoho_callback_returns_503_when_state_consumption_fails(
    client,
    monkeypatch,
):
    mock_consume_state = AsyncMock(
        side_effect=asyncpg.PostgresConnectionError(
            "Simulated database failure"
        )
    )

    monkeypatch.setattr(
        main,
        "consume_oauth_state",
        mock_consume_state,
    )

    response = client.get(
        "/oauth/zoho/callback",
        params={
            "state": "test-oauth-state",
        },
    )

    assert response.status_code == 503
    assert response.json()["status"] == "service_unavailable"

    mock_consume_state.assert_awaited_once_with(
        main.runtime.database_pool,
        "test-oauth-state",
    )


# Test 25: Database failure while persisting Zoho authorization

def test_zoho_callback_returns_503_when_authorization_persistence_fails(
    client,
    monkeypatch,
):
    mock_consume_state = AsyncMock(
        return_value="tenant-test-123"
    )

    mock_exchange_code = AsyncMock(
        return_value={
            "access_token": "test-access-token",
            "refresh_token": "test-refresh-token",
            "scope": (
                "ZohoInventory.items.READ,"
                "ZohoInventory.salesorders.READ,"
                "ZohoInventory.settings.READ"
            ),
        }
    )

    mock_create_authorization = AsyncMock(
        side_effect=asyncpg.PostgresConnectionError(
            "Simulated database failure"
        )
    )

    monkeypatch.setattr(
        main,
        "consume_oauth_state",
        mock_consume_state,
    )

    monkeypatch.setattr(
        main,
        "exchange_authorization_code",
        mock_exchange_code,
    )

    monkeypatch.setattr(
        main,
        "encrypt_refresh_token",
        lambda token: b"encrypted-refresh-token",
    )

    monkeypatch.setattr(
        main,
        "create_zoho_authorization",
        mock_create_authorization,
    )

    response = client.get(
        "/oauth/zoho/callback",
        params={
            "state": "test-oauth-state",
            "code": "test-authorization-code",
        },
    )

    assert response.status_code == 503
    assert response.json()["status"] == "service_unavailable"

    mock_consume_state.assert_awaited_once()
    mock_exchange_code.assert_awaited_once_with(
        "test-authorization-code"
    )

    mock_create_authorization.assert_awaited_once_with(
        pool=main.runtime.database_pool,
        tenant_id="tenant-test-123",
        refresh_token_encrypted=b"encrypted-refresh-token",
        granted_scopes=[
            "ZohoInventory.items.READ",
            "ZohoInventory.salesorders.READ",
            "ZohoInventory.settings.READ",
        ],
    )



# ---------------------------------------------------------
# Database Readiness Tests
# ---------------------------------------------------------

class MockDatabaseConnection:
    async def fetchval(self, query):
        assert query == "SELECT 1"
        return 1


class MockDatabasePool:
    def __init__(self, connection):
        self.connection = connection

    def acquire(self):
        return self

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, exc_type, exc_value, traceback):
        return False


class FailingDatabaseConnection:
    async def fetchval(self, query):
        raise RuntimeError("Sensitive database connection details")


# Test 1: Database is available

def test_readiness_check_when_database_is_available(
    client,
    monkeypatch,
):
    mock_pool = MockDatabasePool(
        MockDatabaseConnection()
    )

    monkeypatch.setattr(
        main.runtime,
        "database_pool",
        mock_pool,
    )

    response = client.get("/health/ready")

    assert response.status_code == 200

    assert response.json() == {
        "status": "ready",
        "database": "connected",
    }


# Test 2: Database pool is unavailable

def test_readiness_check_when_database_pool_is_missing(
    client,
    monkeypatch,
):
    monkeypatch.setattr(
        main.runtime,
        "database_pool",
        None,
    )

    response = client.get("/health/ready")

    assert response.status_code == 503

    assert response.json() == {
        "status": "not_ready",
        "database": "unavailable",
    }


# Test 3: Database query fails

def test_readiness_check_when_database_query_fails(
    client,
    monkeypatch,
    caplog,
):
    mock_pool = MockDatabasePool(
        FailingDatabaseConnection()
    )

    monkeypatch.setattr(
        main.runtime,
        "database_pool",
        mock_pool,
    )

    with caplog.at_level("ERROR"):
        response = client.get("/health/ready")

    assert response.status_code == 503

    assert response.json() == {
        "status": "not_ready",
        "database": "unavailable",
    }

    # Technical failure should be logged internally
    assert "Database readiness check failed" in caplog.text

    # Technical details should not be exposed in the API response
    assert "Sensitive database connection details" not in response.text

