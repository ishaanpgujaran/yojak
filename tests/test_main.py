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
