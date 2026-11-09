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


def mock_existing_authorization(monkeypatch, status):
    monkeypatch.setattr(
        main,
        "get_zoho_authorization_for_tenant",
        AsyncMock(
            return_value={
                "id": "authorization-test-123",
                "tenant_id": "tenant-test-123",
                "granted_scopes": [
                    "ZohoInventory.items.READ",
                    "ZohoInventory.salesorders.READ",
                    "ZohoInventory.settings.READ",
                ],
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